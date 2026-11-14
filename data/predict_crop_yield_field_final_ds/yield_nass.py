#!/usr/bin/env python3
"""Step 1 - target Y and yield-history features from USDA NASS Quick Stats (counties of all states by default; --state-alpha IA | IA,KS, grain corn and soybeans).

Output  <out>/nass_yield.parquet, one row per county x crop x year (including years without a published yield, so that the
        year you want to predict has a row):
  county_fips  county_name  crop  year  yield_bu_acre  target_available
  yield_lag1_bu_acre  yield_mean_prev3_bu_acre  yield_prev3_count

Rules
  * Series: source SURVEY, county level, statisticcat YIELD, unit "BU / ACRE", annual, domain TOTAL, class ALL CLASSES,
    production practice ALL PRODUCTION PRACTICES; CORN only with util_practice GRAIN (grain corn, not silage); SOYBEANS as is.
    Rows that do not belong to one of the two expected series (short_desc) are dropped and counted, so two series never mix.
  * Value "(D)", "(NA)", "(Z)", "" -> missing -> no target row (target_available = False). Commas in numbers are removed.
  * County code 998 / "OTHER (COMBINED) COUNTIES" are not real counties and are dropped.
  * "Previous available years" = published, non-missing yields of the SAME county and crop with year < t (not necessarily
    consecutive). lag1 = the latest of them, mean_prev3 = mean of the latest three (fewer if fewer exist), prev3_count = how many (0-3).
    Nothing from year t or later is used.

Access
  online : python yield_nass.py --api-key KEY --out ./yield_work         (or env NASS_API_KEY; key: https://quickstats.nass.usda.gov/api)
  offline: python yield_nass.py --csv quickstats_export.csv --out ./yield_work   (CSV downloaded from the Quick Stats web UI)
One request per crop and year chunk (--chunk-years) keeps every response far below the API limit of 50,000 rows.
Raw JSON responses are cached in <out>/nass_raw/ and reused (use --refresh to re-download).

Not tested against the live API (blocked in the build sandbox); tested on a synthetic CSV and mocked JSON.
Deps: pip install pandas pyarrow requests
"""
import argparse, datetime as dt, json, os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

URL = "https://quickstats.nass.usda.gov/api/api_GET/"
FIPS_ALPHA_LIST = "AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
SERIES = {"CORN": "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE", "SOYBEANS": "SOYBEANS - YIELD, MEASURED IN BU / ACRE"}


def fetch(a, crop, y0, y1):
    import requests
    f = Path(a.out) / "nass_raw" / f"{crop}_{y0}_{y1}_{str(a.state_alpha).replace(',', '-')}.json"
    if f.exists() and not a.refresh:
        return json.loads(f.read_text())["data"]
    params = {"key": a.api_key, "source_desc": "SURVEY", "agg_level_desc": "COUNTY", "statisticcat_desc": "YIELD", "unit_desc": "BU / ACRE", "commodity_desc": crop, "freq_desc": "ANNUAL",
              "year__GE": y0, "year__LE": y1, "format": "JSON"}
    if str(a.state_alpha).strip().lower() not in ("all", "*", ""):
        params["state_alpha"] = a.state_alpha.strip().upper() if "," not in a.state_alpha else None
    states = [x.strip().upper() for x in str(a.state_alpha).split(",")] if "," in str(a.state_alpha) else [None]
    if len(states) > 1:
        out = []
        for st in states:
            b = argparse.Namespace(**{**vars(a), "state_alpha": st})
            out += fetch(b, crop, y0, y1)
        return out
    for k in range(5):
        r = requests.get(URL, params=params, timeout=120)
        if r.status_code == 200:
            break
        if r.status_code in (400, 413) and "exceeds" in r.text.lower():       # API answers 413 "exceeds limit=50000"
            if y1 > y0:                                                       # split the year range in half and retry
                mid = (y0 + y1) // 2
                print(f"  {crop} {y0}-{y1}: over 50,000 rows, splitting at {mid}", flush=True)
                return fetch(a, crop, y0, mid) + fetch(a, crop, mid + 1, y1)
            if "state_alpha" not in params:                                   # one year still too big: go state by state
                out = []
                for st in sorted(FIPS_ALPHA_LIST):
                    out += fetch(argparse.Namespace(**{**vars(a), "state_alpha": st}), crop, y0, y1)
                return out
            sys.exit(f"{crop} {y0}-{y1} {a.state_alpha}: more than 50,000 rows even for one year and state")
        if r.status_code == 400:
            return []                                    # NASS answers 400 when nothing matches
        time.sleep(2 ** k)
    else:
        sys.exit(f"NASS API failed: HTTP {r.status_code} {r.text[:200]}")
    data = r.json().get("data", [])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"data": data}))
    return data


ALIAS = {"program": "source_desc", "geo_level": "agg_level_desc", "commodity": "commodity_desc", "data_item": "short_desc",
         "domain": "domain_desc", "county": "county_name", "period": "reference_period_desc"}      # web-UI CSV names -> API names


def norm(df):
    df = df.copy()
    df.columns = [ALIAS.get(c, c) for c in (c.strip().lower().replace(" ", "_") for c in df.columns)]
    return df


def clean(df, a):
    df = norm(df)
    need = {"year", "commodity_desc", "value"}
    if need - set(df.columns):
        sys.exit(f"missing columns {need - set(df.columns)}; got {list(df.columns)}")
    n0 = len(df)
    for c, v in (("source_desc", "SURVEY"), ("agg_level_desc", "COUNTY"), ("statisticcat_desc", "YIELD"), ("unit_desc", "BU / ACRE"),
                 ("freq_desc", "ANNUAL"), ("reference_period_desc", "YEAR"), ("domain_desc", "TOTAL"), ("class_desc", "ALL CLASSES"),
                 ("prodn_practice_desc", "ALL PRODUCTION PRACTICES")):
        if c in df.columns:
            df = df[df[c].astype(str).str.upper() == v]
    sa = str(a.state_alpha).strip().lower()
    if "state_alpha" in df.columns and sa not in ("all", "*", ""):
        df = df[df["state_alpha"].astype(str).str.upper().isin([x.strip().upper() for x in sa.split(",")])]
    df["commodity_desc"] = df["commodity_desc"].str.upper()
    df = df[df["commodity_desc"].isin(SERIES)]
    if "util_practice_desc" in df.columns:               # corn: grain only
        bad = (df["commodity_desc"] == "CORN") & (df["util_practice_desc"].astype(str).str.upper() != "GRAIN")
        df = df[~bad]
    if "short_desc" in df.columns:                       # exactly one series per crop
        ok = df.apply(lambda r: str(r["short_desc"]).upper() == SERIES[r["commodity_desc"]], axis=1)
        print(f"  dropped {int((~ok).sum())} rows from other series (short_desc)") if (~ok).any() else None
        df = df[ok]
    st = df["state_fips_code"] if "state_fips_code" in df.columns else df.get("state_ansi")
    cc = df["county_code"] if "county_code" in df.columns else df.get("county_ansi")
    if st is None or cc is None:
        sys.exit("no state/county code columns (state_fips_code/state_ansi, county_code/county_ansi)")
    df["county_fips"] = st.astype(str).str.zfill(2) + cc.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(3)
    df = df[~df["county_fips"].str[2:].isin(["998", "000", "999"])]
    if "county_name" in df.columns:
        df = df[~df["county_name"].astype(str).str.upper().str.contains("OTHER")]
    v = df["value"].astype(str).str.replace(",", "", regex=False).str.strip()
    df["yield_bu_acre"] = pd.to_numeric(v, errors="coerce")          # (D), (NA), (Z) -> NaN
    df["year"] = df["year"].astype(int)
    df["crop"] = df["commodity_desc"]
    df["county_name"] = df["county_name"].astype(str).str.title() if "county_name" in df.columns else ""
    keys = ["county_fips", "crop", "year"]
    dup = df.duplicated(keys, keep=False)
    if dup.any():
        print(f"  WARNING: {int(dup.sum())} rows share county/crop/year; keeping the first. Inspect nass_raw/ if this is not expected.")
        df = df.drop_duplicates(keys)
    print(f"  {n0:,} raw rows -> {len(df):,} county-crop-year rows; missing/suppressed values: {int(df['yield_bu_acre'].isna().sum())}")
    return df[keys + ["county_name", "yield_bu_acre"]]


def add_history(df, last_year):
    """Full grid county x crop x year and strictly-past yield features."""
    counties = df[["county_fips", "county_name"]].drop_duplicates("county_fips")
    years = np.arange(df["year"].min(), last_year + 1)
    grid = (counties.merge(pd.DataFrame({"crop": list(SERIES)}), how="cross")
                    .merge(pd.DataFrame({"year": years}), how="cross"))
    g = grid.merge(df.drop(columns="county_name"), on=["county_fips", "crop", "year"], how="left").sort_values(["county_fips", "crop", "year"])
    out = []
    for _, s in g.groupby(["county_fips", "crop"], sort=False):
        y = s["yield_bu_acre"].to_numpy()
        lag1, m3, c3 = [], [], []
        hist = []
        for v in y:                                       # hist = published values of strictly earlier years
            h = hist[-3:]
            lag1.append(hist[-1] if hist else np.nan)
            m3.append(float(np.mean(h)) if h else np.nan)
            c3.append(len(h))
            if not np.isnan(v):
                hist.append(v)
        s = s.assign(yield_lag1_bu_acre=lag1, yield_mean_prev3_bu_acre=m3, yield_prev3_count=np.array(c3, dtype="int8"))
        out.append(s)
    r = pd.concat(out, ignore_index=True)
    r["target_available"] = r["yield_bu_acre"].notna()
    return r[["county_fips", "county_name", "crop", "year", "yield_bu_acre", "target_available",
              "yield_lag1_bu_acre", "yield_mean_prev3_bu_acre", "yield_prev3_count"]]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True)
    p.add_argument("--api-key", default=os.environ.get("NASS_API_KEY"))
    p.add_argument("--csv", help="Quick Stats CSV export instead of the API")
    p.add_argument("--state-alpha", default="all", help="all | IA | IA,KS (default all)")
    p.add_argument("--start-year", type=int, default=1990)
    p.add_argument("--end-year", type=int, default=dt.date.today().year, help="last year to put in the grid (the year to predict)")
    p.add_argument("--chunk-years", type=int, default=5, help="years per request; all states x one crop x 5 years is ~15k rows, under the 50,000 API limit")
    p.add_argument("--refresh", action="store_true")
    a = p.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    if a.csv:
        raw = pd.read_csv(a.csv, dtype=str, thousands=None)
    else:
        if not a.api_key:
            sys.exit("give --api-key / NASS_API_KEY, or --csv")
        rows = []
        for crop in SERIES:
            for y0 in range(a.start_year, a.end_year + 1, a.chunk_years):
                y1 = min(y0 + a.chunk_years - 1, a.end_year)
                d = fetch(a, crop, y0, y1); rows += d
                print(f"  {crop} {y0}-{y1}: {len(d):,} rows", flush=True)
        raw = pd.DataFrame(rows)
        if raw.empty:
            sys.exit("no rows returned")
    df = clean(raw, a)
    df = df[df["year"] >= a.start_year]
    res = add_history(df, max(a.end_year, int(df["year"].max())))
    fn = Path(a.out) / "nass_yield.parquet"
    res.to_parquet(fn, compression="zstd", index=False)
    lab = res[res["target_available"]]
    print(f"wrote {fn}: {len(res):,} rows, {len(lab):,} with a target, counties {res['county_fips'].nunique()}, "
          f"years with target {int(lab['year'].min())}-{int(lab['year'].max())}")


if __name__ == "__main__":
    main()