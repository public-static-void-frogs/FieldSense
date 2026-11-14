#!/usr/bin/env python3
"""NASS Quick Stats extras for the rule engine: weekly Crop Progress / Condition (state or district) and Census of Agriculture practices (county).

  progress : weekly % planted / emerged / silking / mature / harvested ... and crop condition (% good+excellent) per state x year
             -> raw weekly table + derived day-of-year at which each stage reaches 10 / 50 / 90 % (linear interpolation between weeks)
             Use: validate the M3 sowing / flowering windows and M1 phenology against what farmers reported; stress check for drought years.
  census   : county values from the Census of Agriculture (2012/2017/2022): cover-crop acres, no-till acres, irrigated acres, cropland ...
             -> tidy long table + a wide table (one row per county x year). Use: reference cover-crop share for m4 / m13 (OpTIS check),
                irrigation share for the farmer-irrigation check.

Key: --api-key or env NASS_API_KEY (https://quickstats.nass.usda.gov/api), same key as yield_nass.py.
Output: <out>/nass_progress_weekly.parquet   state_alpha, year, commodity, unit, week_ending, doy, value
        <out>/nass_progress_dates.parquet    state_alpha, year, commodity, stage, p10_doy, p50_doy, p90_doy
        <out>/nass_census_long.parquet       county_fips, year, short_desc, value, unit
        <out>/nass_census_wide.parquet       county_fips, year, census_<slug> ...
Values '(D)', '(Z)', '(NA)' -> missing. Parameter names follow the Quick Stats API (statisticcat_desc, unit_desc, ...); the --like patterns
for the census use the API's short_desc__LIKE operator. Not tested against the live API from the author's environment.

Example: python ext_nass_extra.py progress --state ALL --years 2018 2019 2020 2021 2022 2023 2024 2025 --out ./ext
         python ext_nass_extra.py census   --state ALL --years 2012 2017 2022 --out ./ext
Deps: pip install pandas pyarrow requests
"""
import argparse, json, os, re, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

URL = "https://quickstats.nass.usda.gov/api/api_GET/"
STATES = "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()


def state_list(a):
    """--state: ALL, one state alpha (IA) or a comma list (IA,KS)"""
    s = str(a.state).strip().upper()
    return STATES if s in ("ALL", "*", "") else [x.strip() for x in s.split(",")]
PROGRESS_COMMODITIES = ["CORN", "SOYBEANS", "WHEAT, WINTER", "SORGHUM", "OATS", "ALFALFA"]
CENSUS_LIKE = ["COVER CROP", "NO-TILL", "CONSERVATION TILLAGE", "IRRIGATED", "CROPLAND, HARVESTED - ACRES", "CORN, GRAIN - ACRES HARVESTED",
               "SOYBEANS - ACRES HARVESTED"]


def query(a, params):
    import requests
    params = {**params, "key": a.api_key, "format": "JSON"}
    for k in range(5):
        try:
            r = requests.get(a.url, params=params, timeout=120)
        except Exception as e:
            time.sleep(2 ** k); continue
        if r.status_code == 200:
            return r.json().get("data", [])
        if r.status_code == 400:
            if "exceeds" in r.text.lower(): sys.exit(f"more than 50,000 rows for {params}; narrow --years / --like")
            return []                                         # NASS answers 400 when nothing matches
        time.sleep(2 ** k)
    sys.exit(f"Quick Stats failed: HTTP {r.status_code} {r.text[:200]}")


def val(s):
    s = str(s).strip().replace(",", "")
    return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else np.nan


def doy_cross(doys, vals, level):
    """first day at which the cumulative curve reaches `level` (linear interpolation between observations), NaN if never"""
    o = np.argsort(doys); d = np.asarray(doys)[o]; v = np.asarray(vals)[o]
    ok = ~np.isnan(v); d, v = d[ok], v[ok]
    if len(v) == 0 or v.max() < level: return np.nan
    i = int(np.argmax(v >= level))
    if i == 0 or v[i] == level: return float(d[i])
    return float(d[i - 1] + (level - v[i - 1]) * (d[i] - d[i - 1]) / (v[i] - v[i - 1]))


def cmd_progress(a):
    rows = []
    for y in a.years:
        for crop, stat, st in ((c, s_, st_) for c in a.commodities for s_ in (["PROGRESS"] + (["CONDITION"] if a.condition else [])) for st_ in ([None] if str(a.state).strip().upper() in ("ALL", "*", "") else state_list(a))):
            if True:
                p = {"source_desc": "SURVEY", "sector_desc": "CROPS", "commodity_desc": crop, "statisticcat_desc": stat, "agg_level_desc": a.agg_level,
                     "freq_desc": "WEEKLY", "year": y}
                if st: p["state_alpha"] = st                     # ALL = no state filter: one request per commodity/stat/year
                for r in query(a, p):
                    rows.append({"state_alpha": r.get("state_alpha"), "year": int(r["year"]), "commodity": r["commodity_desc"],
                                 "unit": r.get("unit_desc"), "short_desc": r.get("short_desc"), "week_ending": r.get("week_ending"), "value": val(r.get("Value")),
                                 "district": r.get("asd_desc") if a.agg_level != "STATE" else None})
        print(f"  {y}: {len(rows):,} rows so far", flush=True)
    if not rows: sys.exit("no rows returned (check --state, years, key)")
    d = pd.DataFrame(rows); d["week_ending"] = pd.to_datetime(d["week_ending"]); d["doy"] = d["week_ending"].dt.dayofyear
    Path(a.out).mkdir(parents=True, exist_ok=True)
    d.to_parquet(Path(a.out) / "nass_progress_weekly.parquet", index=False)
    der = []
    prog = d[d["unit"].astype(str).str.startswith("PCT ") & ~d["unit"].astype(str).str.contains("EXCELLENT|GOOD|FAIR|POOR|VERY", regex=True)]
    for (st, y, crop, unit, dist), g in prog.groupby(["state_alpha", "year", "commodity", "unit", "district"], dropna=False):
        der.append({"state_alpha": st, "year": y, "commodity": crop, "stage": unit.replace("PCT ", "").lower(), "district": dist,
                    **{f"p{q}_doy": doy_cross(g["doy"].to_numpy(), g["value"].to_numpy(), q) for q in (10, 50, 90)}})
    pd.DataFrame(der).to_parquet(Path(a.out) / "nass_progress_dates.parquet", index=False)
    if a.condition:
        c = d[d["unit"].astype(str).str.contains("EXCELLENT|GOOD")]
        if len(c):
            ge = c.assign(k=c["unit"].str.extract(r"(EXCELLENT|GOOD)")[0]).groupby(["state_alpha", "year", "commodity", "week_ending", "doy", "district"], dropna=False)["value"].sum().reset_index(name="pct_good_excellent")
            ge.to_parquet(Path(a.out) / "nass_condition_ge_weekly.parquet", index=False)
    print(f"wrote nass_progress_weekly.parquet ({len(d):,}) and nass_progress_dates.parquet ({len(der):,})")


def cmd_census(a):
    rows = []
    for y in a.years:
        for like, st in ((l, s_) for l in a.like for s_ in state_list(a)):
            p = {"source_desc": "CENSUS", "agg_level_desc": "COUNTY", "state_alpha": st, "year": y, "short_desc__LIKE": like}
            for r in query(a, p):
                rows.append({"county_fips": str(r["state_fips_code"]).zfill(2) + str(r["county_code"]).zfill(3), "year": int(r["year"]),
                             "short_desc": r["short_desc"], "domain": r.get("domain_desc"), "domaincat": r.get("domaincat_desc"),
                             "value": val(r.get("Value")), "unit": r.get("unit_desc")})
        print(f"  {y}: {len(rows):,} rows so far", flush=True)
    if not rows: sys.exit("no rows returned")
    d = pd.DataFrame(rows).drop_duplicates()
    d = d[(d["domain"].astype(str).str.upper() == "TOTAL") | d["domain"].isna()]           # drop farm-size / other domain breakdowns
    Path(a.out).mkdir(parents=True, exist_ok=True)
    d.to_parquet(Path(a.out) / "nass_census_long.parquet", index=False)
    d["slug"] = "census_" + d["short_desc"].str.lower().str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_").str.slice(0, 60)
    w = d.pivot_table(index=["county_fips", "year"], columns="slug", values="value", aggfunc="first").reset_index()
    w.to_parquet(Path(a.out) / "nass_census_wide.parquet", index=False)
    print(f"wrote nass_census_long.parquet ({len(d):,}) and nass_census_wide.parquet ({len(w):,} county-years, {w.shape[1] - 2} columns)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    for n, fn in (("progress", cmd_progress), ("census", cmd_census)):
        s = sp.add_parser(n); s.set_defaults(fn=fn)
        s.add_argument("--state", default="ALL", help="ALL, a state alpha (IA) or a comma list (IA,KS)"); s.add_argument("--years", type=int, nargs="+", required=True)
        s.add_argument("--out", required=True); s.add_argument("--api-key", default=os.environ.get("NASS_API_KEY")); s.add_argument("--url", default=URL)
        if n == "progress":
            s.add_argument("--commodities", nargs="+", default=PROGRESS_COMMODITIES)
            s.add_argument("--agg-level", default="STATE", help="STATE or AGRICULTURAL DISTRICT"); s.add_argument("--no-condition", dest="condition", action="store_false")
        else:
            s.add_argument("--like", nargs="+", default=CENSUS_LIKE, help="short_desc__LIKE patterns")
    a = p.parse_args()
    if not a.api_key: sys.exit("NASS API key needed: --api-key or env NASS_API_KEY")
    a.fn(a)


if __name__ == "__main__":
    main()
