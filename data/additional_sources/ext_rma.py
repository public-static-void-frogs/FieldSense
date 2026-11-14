#!/usr/bin/env python3
"""USDA RMA Cause of Loss (Summary of Business with Month of Loss, 'colsom') -> county x year x crop indemnities by cause.

Why: an independent, insured-loss record of drought / heat / excess-moisture years per county. Use it (a) to validate the drought seasons that
M2 derives from USDM/SMAP/POWER, (b) as the source behind the 'crop-insurance rules' risk item, (c) as a county-level stress label in Proof Bench.

Input : yearly colsom zips (pipe-delimited, no header) downloaded from --url-template or read from --local-dir (colsom_<year>.zip, or .txt/.csv)
Output: <out>/rma_col_county_year.parquet  one row per county x crop x year:
          county_fips (5 digits), year, crop, rma_<group>_indemnity_usd, rma_<group>_indemnified_acres (groups: drought, heat, excess_moisture,
          hail, freeze, wind, disease_pest, other), rma_total_indemnity_usd, rma_drought_share (drought / total), rma_drought_flag
        <out>/rma_col_county_year_all_crops.parquet  same but all crops of --crops summed (for a county-level drought-year label)
Groups come from the cause-of-loss DESCRIPTION text (keyword match; see GROUPS) - edit it if you need other splits.
Flag: rma_drought_flag = drought share >= --drought-share and total indemnity >= --min-usd (defaults 0.5 and 100000).

CAVEAT: the colsom column layout is the published 30-column one, but it was NOT checked against the live files by the author. The script
verifies the column count and refuses to guess: if it differs, it prints the first row; pass --columns name1,name2,... (must include
year, state_code, county_code, crop, cause, indemnified_acres, indemnity_usd) to map it yourself. Same for the URL.

Example: python ext_rma.py --state all --years 2018 2019 2020 2021 2022 2023 2024 --out ./ext
         python ext_rma.py --state 19 --years 2018 2019 --local-dir D:/data/rma --out ./ext
Deps: pip install pandas pyarrow requests
"""
import argparse, io, re, sys, zipfile
from pathlib import Path
import pandas as pd

URL = "https://pubfs-rma.fpac.usda.gov/pub/Web_Data_Files/Summary_of_Business/cause_of_loss/colsom_{year}.zip"
COLS = ["year", "state_code", "state_abbr", "county_code", "county_name", "crop_code", "crop", "plan_code", "plan", "coverage_category",
        "stage_code", "cause_code", "cause", "month_code", "month", "year_of_loss", "policies_earning_premium", "policies_indemnified",
        "net_planted_qty", "net_endorsed_acres", "liability", "total_premium", "producer_premium", "subsidy", "state_private_subsidy",
        "additional_subsidy", "efa_discount", "indemnified_acres", "indemnity_usd", "loss_ratio"]
GROUPS = [("drought", r"DROUGHT"), ("heat", r"HEAT|HOT WIND|FAILURE OF IRRIGATION|IRRIGATION SUPPLY"),
          ("excess_moisture", r"EXCESS MOISTURE|PRECIPITATION|RAIN|FLOOD|WET|STANDING WATER|MOISTURE"),
          ("hail", r"HAIL"), ("freeze", r"FREEZE|FROST|COLD|SNOW|ICE"), ("wind", r"WIND|TORNADO|HURRICANE|CYCLONE"),
          ("disease_pest", r"DISEASE|INSECT|PLANT DISEASE|WILDLIFE|FUNGUS")]


def group_of(cause):
    c = str(cause).upper()
    for g, pat in GROUPS:
        if re.search(pat, c):
            return g
    return "other"


def get_year(a, y, cols):
    import requests
    name = f"colsom_{y}"
    local = None
    if a.local_dir:
        for ext in (".zip", ".txt", ".csv"):
            if (Path(a.local_dir) / (name + ext)).exists(): local = Path(a.local_dir) / (name + ext); break
    if local is None:
        cache = Path(a.cache) / f"{name}.zip"
        if not cache.exists():
            url = a.url_template.format(year=y)
            r = requests.get(url, timeout=300)
            if r.status_code != 200:
                print(f"  {y}: HTTP {r.status_code} for {url}", file=sys.stderr); return None
            cache.parent.mkdir(parents=True, exist_ok=True); cache.write_bytes(r.content)
        local = cache
    raw = local.read_bytes()
    if local.suffix == ".zip":
        z = zipfile.ZipFile(io.BytesIO(raw)); raw = z.read(z.namelist()[0])
    txt = raw.decode("latin-1")
    first = txt.split("\n", 1)[0]
    n = first.count("|") + 1
    if n != len(cols):
        sys.exit(f"{y}: file has {n} columns, expected {len(cols)}. First row:\n{first[:300]}\nPass --columns with the right names.")
    df = pd.read_csv(io.StringIO(txt), sep="|", header=None, names=cols, dtype=str, engine="c", on_bad_lines="skip")
    return df


def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", default="all", help="all | FIPS | FIPS,FIPS (RMA state code = FIPS)"); p.add_argument("--years", type=int, nargs="+", required=True); p.add_argument("--out", required=True)
    p.add_argument("--crops", nargs="+", default=["CORN", "SOYBEANS", "WHEAT", "SORGHUM", "OATS", "ALFALFA"])
    p.add_argument("--url-template", default=URL); p.add_argument("--local-dir"); p.add_argument("--cache", default="./ext_cache")
    p.add_argument("--columns", help="comma-separated names replacing the default 30-column layout")
    p.add_argument("--drought-share", type=float, default=0.5); p.add_argument("--min-usd", type=float, default=100000)
    a = p.parse_args()
    cols = a.columns.split(",") if a.columns else COLS
    need = {"year", "state_code", "county_code", "crop", "cause", "indemnified_acres", "indemnity_usd"}
    if need - set(cols): sys.exit(f"--columns must contain {sorted(need)}")
    sel = None if str(a.state).strip().lower() in ("all", "*", "") else {x.strip().zfill(2) for x in str(a.state).split(",")}
    parts = []
    for y in a.years:
        df = get_year(a, y, cols)
        if df is None: continue
        df["state_code"] = df["state_code"].astype(str).str.strip().str.zfill(2)
        df = (df[df["state_code"].isin(sel)] if sel else df).copy()
        df["crop"] = df["crop"].astype(str).str.strip().str.upper()
        df = df[df["crop"].isin([c.upper() for c in a.crops])]
        df["county_fips"] = df["state_code"] + df["county_code"].astype(str).str.strip().str.zfill(3)
        df["year"] = num(df["year"]).astype("Int64")
        df["g"] = df["cause"].map(group_of)
        df["ind"] = num(df["indemnity_usd"]).fillna(0); df["ac"] = num(df["indemnified_acres"]).fillna(0)
        parts.append(df[["county_fips", "year", "crop", "g", "ind", "ac"]]); print(f"  {y}: {len(df):,} rows kept", flush=True)
    if not parts: sys.exit("no data read")
    d = pd.concat(parts, ignore_index=True)

    def wide(d, by):
        w = d.groupby(by + ["g"]).agg(ind=("ind", "sum"), ac=("ac", "sum")).reset_index()
        i = w.pivot_table(index=by, columns="g", values="ind", aggfunc="sum", fill_value=0.0)
        c = w.pivot_table(index=by, columns="g", values="ac", aggfunc="sum", fill_value=0.0)
        i.columns = [f"rma_{k}_indemnity_usd" for k in i.columns]; c.columns = [f"rma_{k}_indemnified_acres" for k in c.columns]
        r = i.join(c).reset_index()
        for g, _ in GROUPS + [("other", "")]:
            for pre in ("indemnity_usd", "indemnified_acres"):
                if f"rma_{g}_{pre}" not in r.columns: r[f"rma_{g}_{pre}"] = 0.0
        r["rma_total_indemnity_usd"] = r[[f"rma_{g}_indemnity_usd" for g, _ in GROUPS + [("other", "")]]].sum(axis=1)
        r["rma_drought_share"] = (r["rma_drought_indemnity_usd"] / r["rma_total_indemnity_usd"]).where(r["rma_total_indemnity_usd"] > 0)
        r["rma_drought_flag"] = ((r["rma_drought_share"] >= a.drought_share) & (r["rma_total_indemnity_usd"] >= a.min_usd)).astype("int8")
        return r
    Path(a.out).mkdir(parents=True, exist_ok=True)
    w1 = wide(d, ["county_fips", "year", "crop"]); w2 = wide(d, ["county_fips", "year"])
    w1.to_parquet(Path(a.out) / "rma_col_county_year.parquet", index=False); w2.to_parquet(Path(a.out) / "rma_col_county_year_all_crops.parquet", index=False)
    print(f"wrote rma_col_county_year.parquet ({len(w1):,} rows) and rma_col_county_year_all_crops.parquet ({len(w2):,} rows)")


if __name__ == "__main__":
    main()
