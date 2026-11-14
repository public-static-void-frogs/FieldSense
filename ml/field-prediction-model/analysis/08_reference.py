"""Reference tables for M3 and the water ledger: NASS Iowa crop progress by district, and county soils.

- NASS weekly Iowa Crop Progress & Condition, by crop reporting district (9 districts + state), as
  gleaned from the weekly PDFs by the Iowa Environmental Mesonet (IEM, Iowa State University):
  days suitable for fieldwork, % planted / emerged / silking / harvested, topsoil and subsoil moisture.
  The workbook has a few unparseable dates and duplicates; both are dropped and counted.
- County -> district from the NASS county list.
- County soils from NRCS SSURGO via Soil Data Access (SQL, no key; Iowa survey areas are counties):
  area-weighted available water storage to 25/50/100/150 cm (muaggatt aws*wta, cm -> mm), Iowa corn
  suitability rating CSR2 (mapunit.iacornsr), and the share of poorly or very poorly drained soils.

Usage: python 08_reference.py --cache reference_cache --out reference/
"""
import argparse
import json
import ssl
import urllib.request
from pathlib import Path

import certifi
import pandas as pd

CTX = ssl.create_default_context(cafile=certifi.where())
IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/nass_iowa.py"
COUNTY_LIST = "https://www.nass.usda.gov/Data_and_Statistics/County_Data_Files/Frequently_Asked_Questions/county_list.txt"
SDA = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
DISTRICTS = {10: "nw", 20: "nc", 30: "ne", 40: "wc", 50: "c", 60: "ec", 70: "sw", 80: "sc", 90: "se"}
SOILS_SQL = """
SELECT l.areasymbol, sum(m.muacres) AS acres,
       {aws},
       sum(m.muacres * CAST(m.iacornsr AS float)) / sum(CASE WHEN m.iacornsr IS NOT NULL THEN m.muacres END) AS csr2,
       sum(CASE WHEN ma.drclassdcd IN ('Poorly drained', 'Very poorly drained') THEN m.muacres ELSE 0 END)
           / CAST(sum(m.muacres) AS float) AS poorly_drained_share
FROM legend l JOIN mapunit m ON m.lkey = l.lkey JOIN muaggatt ma ON ma.mukey = m.mukey
WHERE l.areasymbol LIKE 'IA%' GROUP BY l.areasymbol"""


def get(url, cache, data=None):
    if cache.exists():
        return cache.read_bytes()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "field-shift-research", "Content-Type": "application/json"})
    body = urllib.request.urlopen(req, timeout=300, context=CTX).read()
    cache.write_bytes(body)
    return body


def progress(cache):
    get(IEM, cache / "iem_nass_iowa.xlsx")
    x = pd.read_excel(cache / "iem_nass_iowa.xlsx")
    n0 = len(x)
    x["week_ending"] = pd.to_datetime(x.valid, errors="coerce")
    x = x[x.week_ending.dt.year.between(1970, 2026)]
    x = x.sort_values("load_time").drop_duplicates(["week_ending", "metric"], keep="last")
    long = x.melt(id_vars=["week_ending", "metric"], value_vars=list(DISTRICTS.values()) + ["iowa"],
                  var_name="district", value_name="value").dropna(subset=["value"])
    days = long.metric == "days suitable"
    bad = (days & ~long.value.between(0, 7)) | (~days & ~long.value.between(0, 100))
    print(f"NASS progress: {n0:,} workbook rows, {n0 - len(x):,} dropped (bad date or duplicate), "
          f"{int(bad.sum())} values out of range dropped")
    long = long[~bad]
    # weeks end on Sunday; some reports are also filed under the Monday release date: drop those copies
    key = ["week_ending", "metric", "district"]
    day_after = pd.MultiIndex.from_frame(long[key].assign(week_ending=long.week_ending + pd.Timedelta(days=1)))
    copy = long.week_ending.dt.day_of_week.eq(0) & pd.MultiIndex.from_frame(long[key]).isin(day_after)
    print(f"  {int(copy.sum())} Monday copies of a Sunday week dropped; "
          f"other weekdays kept: {long[~copy].week_ending.dt.day_name().value_counts().drop('Sunday').to_dict()}")
    long = long[~copy]
    # cumulative progress must not fall within a season; count the weeks where it does
    cum = long[long.metric.str.contains("planted|emerged|silking|harvested|mature|dented")].sort_values("week_ending")
    falls = cum.groupby(["metric", "district", cum.week_ending.dt.year]).value.diff().lt(-0.5).sum()
    print(f"  {long.week_ending.dt.year.min()}-{long.week_ending.dt.year.max()}, {long.metric.nunique()} metrics; "
          f"{int(falls)} weekly decreases in cumulative progress (kept)")
    return long.sort_values(["metric", "district", "week_ending"])


def county_districts(cache):
    text = get(COUNTY_LIST, cache / "nass_county_list.txt").decode("latin-1")
    rows = [line.split(None, 3) for line in text.splitlines() if line.startswith("19 ")]
    df = pd.DataFrame([r[:4] for r in rows], columns=["state", "district", "county", "name"])
    df = df[df.county.str.fullmatch(r"\d{3}") & ~df.county.isin(["000", "888", "999"])]
    df["county_fips"] = "19" + df.county
    df["district_code"] = df.district.astype(int)
    df["district"] = df.district_code.map(DISTRICTS)
    df["county_name"] = df.name.str.replace(r"\s+1$", "", regex=True).str.strip()
    assert len(df) == 99 and df.district.notna().all()
    return df[["county_fips", "county_name", "district_code", "district"]]


def soils(cache):
    aws = ",\n       ".join(f"10 * sum(m.muacres * ma.aws{d}wta) / sum(CASE WHEN ma.aws{d}wta IS NOT NULL THEN m.muacres END) AS aws_0_{d.lstrip('0')}cm_mm"
                           for d in ("025", "050", "0100", "0150"))
    body = json.dumps({"query": SOILS_SQL.format(aws=aws), "format": "JSON+COLUMNNAME"}).encode()
    t = json.loads(get(SDA, cache / "sda_county_soils.json", data=body))["Table"]
    df = pd.DataFrame(t[1:], columns=t[0])
    df["county_fips"] = "19" + df.areasymbol.str[2:]
    for c in df.columns.drop(["areasymbol", "county_fips"]):
        df[c] = pd.to_numeric(df[c])
    assert len(df) == 99
    return df.drop(columns="areasymbol")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cache, out = Path(args.cache), Path(args.out)
    cache.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    progress(cache).to_parquet(out / "nass_iowa_progress.parquet", compression="zstd", index=False)
    cd = county_districts(cache)
    cd.to_parquet(out / "iowa_county_district.parquet", index=False)
    print("counties per district:", cd.district.value_counts().sort_index().to_dict())
    s = soils(cache).merge(cd[["county_fips", "county_name"]], on="county_fips", how="left")
    assert s.county_name.notna().all()
    s.to_parquet(out / "county_soils.parquet", index=False)
    print(s.describe().round(2).to_string())


if __name__ == "__main__":
    main()
