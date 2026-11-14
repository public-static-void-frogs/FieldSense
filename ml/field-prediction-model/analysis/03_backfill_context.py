"""County context for every year: April drought (USDM) and crop shares (CDL via CropScape).

field_dataset has its April drought snapshot from 2018 and neighbour shares not at all. This script
builds both per county and year from keyless public services, so earlier years can be used:

- USDM county statistics, categorical percent area, the first weekly map dated on or after 7 April
  (the same rule that reproduces the dataset's drought_valid_date for 2018-2025). From 2000.
- CDL county acreage from CropScape (Iowa CDL starts in 2000). Shares are taken over agricultural
  classes, so they compare with the CSB-based shares (CSB polygons cover cropland and pasture).

Usage: python 03_backfill_context.py --dataset path/to/field_dataset --cache ctx_cache --out county_context.csv
"""
import argparse
import io
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
import duckdb
import pandas as pd

CTX = ssl.create_default_context(cafile=certifi.where())
CDL_YEARS = range(2000, 2025)
USDM_URL = ("https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent"
            "?aoi={fips}&startdate=1/1/2000&enddate=12/31/2025&statisticsType=2")
CDL_CACHE_URL = "https://nassgeodata.gmu.edu/webservice/nass_data_cache/byfips/CDL_{year}_{fips}.csv"
CDL_SERVICE_URL = "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLStat?year={year}&fips={fips}&format=csv"
NON_AG = {111, 121, 122, 123, 124, 131, 141, 142, 143, 152, 190, 195}
HAY_PASTURE = {36, 37, 62, 176}


def get(url, accept=None):
    headers = {"User-Agent": "field-shift-research"}
    if accept:
        headers["Accept"] = accept
    for attempt in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=180, context=CTX).read().decode()
        except Exception as e:
            err = e
            if getattr(e, "code", None) == 404:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{url}: {err}")


def cached(path, fetch):
    if path.exists():
        return path.read_text()
    text = fetch()
    path.write_text(text)
    return text


def usdm_county(fips, cache):
    text = cached(cache / f"usdm_{fips}.csv", lambda: get(USDM_URL.format(fips=fips), accept="text/csv"))
    df = pd.read_csv(io.StringIO(text))
    df["date"] = pd.to_datetime(df.MapDate.astype(str), format="%Y%m%d")
    df = df[(df.date.dt.month > 4) | ((df.date.dt.month == 4) & (df.date.dt.day >= 7))]
    first = df.sort_values("date").groupby(df.date.dt.year).head(1)
    out = pd.DataFrame({
        "county_fips": str(fips), "year": first.date.dt.year, "usdm_date": first.date.dt.date,
        # categorical percent area: class -1 = none, 0 = D0 ... 4 = D4
        "usdm_class_april": (-1 * first["None"] + sum(k * first[f"D{k}"] for k in range(5))) / 100,
        "usdm_d1plus_share_april": sum(first[f"D{k}"] for k in range(1, 5)) / 100})
    return out


def cdl_county_year(fips, year, cache):
    def fetch():
        try:
            return get(CDL_CACHE_URL.format(year=year, fips=fips))
        except Exception:
            xml = get(CDL_SERVICE_URL.format(year=year, fips=fips))
            if "<returnURL>" not in xml:
                raise RuntimeError(f"CDL {year} {fips}: {xml[:200]}")
            return get(xml.split("<returnURL>")[1].split("</returnURL>")[0])
    text = cached(cache / f"cdl_{year}_{fips}.csv", fetch)
    df = pd.read_csv(io.StringIO(text), skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    ag = df[~df.Value.isin(NON_AG)]
    total = ag.Acreage.sum()
    acres = lambda codes: ag[ag.Value.isin(codes)].Acreage.sum()
    corn, soy = acres({1}), acres({5})
    nan = float("nan")
    # Iowa county CDLs have at most 10-17 classes in 2000-2005 against 30-47 in 2024, and 3 county files of
    # 2000 are empty, so shares of "all agricultural land" drift between years. corn / (corn + soy) is stable.
    return {"county_fips": str(fips), "cdl_year": year, "cdl_n_classes": len(df), "cdl_ag_acres": total,
            "cdl_corn_frac": corn / (corn + soy) if corn + soy else nan,
            "cdl_corn_share": corn / total if total else nan, "cdl_soy_share": soy / total if total else nan,
            "cdl_hay_pasture_share": acres(HAY_PASTURE) / total if total else nan}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True, help="output CSV: one row per county x target year")
    args = ap.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"CREATE VIEW fd AS SELECT * EXCLUDE (drought_dm) FROM read_parquet('{args.dataset}/year=*/part.parquet', union_by_name = true)")
    counties = [r[0] for r in con.execute("SELECT DISTINCT county_fips FROM fd ORDER BY 1").fetchall()]

    with ThreadPoolExecutor(max_workers=6) as ex:
        usdm = pd.concat(ex.map(lambda f: usdm_county(f, cache), counties), ignore_index=True)
        jobs = [(f, y) for f in counties for y in CDL_YEARS]
        cdl = pd.DataFrame(ex.map(lambda j: cdl_county_year(j[0], j[1], cache), jobs))
    print(f"USDM: {len(usdm)} county-years {usdm.year.min()}-{usdm.year.max()}; CDL: {len(cdl)} county-years")

    # target year t uses the CDL of t-1 (as the dataset's *_prev1 features do) and the April map of t
    cdl["year"] = cdl.cdl_year + 1
    ctx = usdm.merge(cdl.drop(columns="cdl_year"), on=["county_fips", "year"], how="outer")
    ctx.sort_values(["county_fips", "year"]).to_csv(args.out, index=False)
    print(f"wrote {len(ctx)} county-years")


if __name__ == "__main__":
    main()
