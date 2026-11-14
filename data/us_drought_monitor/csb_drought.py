#!/usr/bin/env python3
"""U.S. Drought Monitor (USDM) class for field coordinates, weekly, as Parquet.

USDM is an expert-drawn weekly map of drought regions (D0-D4), NOT a measurement at the field.
Two subcommands:

  weekly   For each selected field/point and each weekly map, find which USDM drought polygon contains the
           centroid. Output = long table, one row per point per week:
               CSBID, valid_date, dm, category, release_date_est
           dm: 0..4 (D0..D4); null = the point is in no drought polygon ("None", i.e. no drought category).
           NOTE: "None" is also what you get for points outside USDM coverage (outside the US/territory maps);
           the script cannot tell them apart. Where several polygons contain a point (if the files nest them),
           the highest DM wins.
  county   County-level statistics from the USDM statistics web service (percent of county area per class)
           for the counties you list, saved as Parquet with the service's own column names (lowercased).

Data location of the weekly maps (UNVERIFIED URL templates, they come from my memory of the site, not from
the docs I could read; change --url-template if the site differs, or download files by hand from
https://droughtmonitor.unl.edu/DmData/GISData.aspx into --cache and the script will use them):
    shapefile zip : https://droughtmonitor.unl.edu/data/shapefiles_m/USDM_{date}_M.zip     ({date}=YYYYMMDD)
    geojson       : https://droughtmonitor.unl.edu/data/json/usdm_{date}.json              (use --format json)
Maps are valid on Tuesdays; the script steps by 7 days from the first Tuesday on/after --start.

Examples
  python csb_drought.py weekly --bounds ./csb_bounds --county 19015 --start 2018-01-01 --end 2025-12-31 \\
        --cache ./usdm_cache --out boone_drought.parquet
  python csb_drought.py weekly --points pts.csv --start 2024-01-01 --end 2024-12-31 --cache ./usdm_cache --out pts_drought.parquet
  python csb_drought.py county --fips 19015 19169 --start 2018-01-01 --end 2025-12-31 --out county_drought.parquet

Standalone: no imports from the other csb_* scripts (field selection code is duplicated on purpose).
Deps: pip install pandas pyarrow numpy requests geopandas pyogrio shapely pyproj
"""
import argparse, datetime as dt, io, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

import pyarrow.parquet as pq

def load_fields(a):
    if a.points:
        p = pd.read_csv(a.points)
        low = {c.lower(): c for c in p.columns}
        pick = lambda *names: next((low[n] for n in names if n in low), None)
        ic, lo, la = pick("id", "csbid"), pick("lon", "longitude", "centroid_lon"), pick("lat", "latitude", "centroid_lat")
        if not (ic and lo and la):
            sys.exit(f"--points CSV needs id, lon, lat columns; found {list(p.columns)}")
        return pd.DataFrame({"CSBID": p[ic].astype(str), "centroid_lon": p[lo].astype(float), "centroid_lat": p[la].astype(float)})
    if not a.bounds:
        sys.exit("give --bounds DIR or --points CSV")
    ids = None
    if a.ids:
        raw = Path(a.ids).read_text().splitlines()
        if raw and "CSBID" in raw[0].split(","):
            col = raw[0].split(",").index("CSBID")
            ids = {ln.split(",")[col].strip() for ln in raw[1:] if ln.strip()}
        else:
            ids = {ln.split(",")[0].strip() for ln in raw if ln.strip()}
    files = sorted(Path(a.bounds).glob("batch_*.parquet"))
    if not files:
        sys.exit(f"no batch_*.parquet in {a.bounds}")
    parts, n = [], 0
    for f in files:
        have = set(pq.read_schema(f).names)
        cols = ["CSBID", "centroid_lon", "centroid_lat"] + [c for c in ("STATEFIPS", "CNTYFIPS") if c in have and (a.state or a.county)]
        df = pd.read_parquet(f, columns=cols)
        if a.state:
            df = df[df["STATEFIPS"] == str(a.state).zfill(2)]
        if a.county:
            df = df[df["CNTYFIPS"] == str(a.county).zfill(5)]
        if ids is not None:
            df = df[df["CSBID"].isin(ids)]
        if a.limit:
            df = df.head(a.limit - n)
        if len(df):
            parts.append(df[["CSBID", "centroid_lon", "centroid_lat"]]); n += len(df)
        if a.limit and n >= a.limit:
            break
    if not parts:
        sys.exit("no fields matched the selection")
    return pd.concat(parts, ignore_index=True)


ZIP_T = "https://droughtmonitor.unl.edu/data/shapefiles_m/USDM_{date}_M.zip"
JSON_T = "https://droughtmonitor.unl.edu/data/json/usdm_{date}.json"
CATS = {0: "D0", 1: "D1", 2: "D2", 3: "D3", 4: "D4"}


def tuesdays(start, end):
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    s += dt.timedelta(days=(1 - s.weekday()) % 7)          # next Tuesday (weekday 1)
    while s <= e:
        yield s
        s += dt.timedelta(days=7)


def get_file(day, a):
    """Return local path of the weekly map, downloading into --cache if missing. None if unavailable."""
    import requests
    ds = day.strftime("%Y%m%d")
    tmpl = a.url_template or (JSON_T if a.format == "json" else ZIP_T)
    name = Path(tmpl.format(date=ds)).name
    dst = Path(a.cache) / name
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    for i in range(4):
        try:
            r = requests.get(tmpl.format(date=ds), timeout=120)
            if r.status_code == 200 and r.content:
                tmp = Path(str(dst) + ".part"); tmp.write_bytes(r.content); tmp.rename(dst)
                return dst
            if r.status_code in (403, 404):
                return None
        except requests.RequestException:
            pass
        time.sleep(2 ** (i + 1))
    return None


def read_polys(path):
    import geopandas as gpd
    src = f"zip://{path}" if str(path).endswith(".zip") else str(path)
    g = gpd.read_file(src, engine="pyogrio")
    col = next((c for c in g.columns if c.upper() == "DM"), None)
    if col is None:
        raise ValueError(f"no DM column in {path}: {list(g.columns)}")
    g = g.rename(columns={col: "DM"})[["DM", "geometry"]]
    if g.crs is None:                                       # shapefile without .prj: GeoJSON is lon/lat, shapefile Albers (assumed)
        g = g.set_crs("EPSG:4326" if str(path).endswith(".json") else "EPSG:5070")
    return g


def cmd_weekly(a):
    import geopandas as gpd
    import pyarrow as pa, pyarrow.parquet as pq
    fields = load_fields(a)[["CSBID", "centroid_lon", "centroid_lat"]].reset_index(drop=True)
    weeks = list(tuesdays(a.start, a.end))
    est = len(fields) * len(weeks)
    print(f"{len(fields):,} points x {len(weeks)} weeks = up to {est:,} rows", flush=True)
    if est > a.max_rows and not a.drop_none:
        sys.exit(f"{est:,} rows exceeds --max-rows {a.max_rows:,}; select fewer points, or use --drop-none to keep only drought rows")
    pts = gpd.GeoDataFrame(fields[["CSBID"]], geometry=gpd.points_from_xy(fields["centroid_lon"], fields["centroid_lat"]), crs="EPSG:4326")
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(out) + ".tmp")
    writer, written, missing = None, 0, []
    cache_crs, pts_proj = None, None
    for i, day in enumerate(weeks, 1):
        f = get_file(day, a)
        if f is None:
            missing.append(day.isoformat()); continue
        try:
            polys = read_polys(f)
        except Exception as e:
            print(f"{day}: unreadable ({e})", file=sys.stderr); missing.append(day.isoformat()); continue
        if cache_crs != polys.crs:                           # reproject points only when the CRS changes
            pts_proj, cache_crs = pts.to_crs(polys.crs), polys.crs
        j = gpd.sjoin(pts_proj, polys, how="left", predicate="within")
        dm = j.groupby(level=0)["DM"].max()                  # highest class if several polygons contain the point
        res = pd.DataFrame({"CSBID": fields["CSBID"].to_numpy(), "valid_date": pd.Timestamp(day),
                            "dm": dm.reindex(fields.index).astype("Int8").to_numpy()})
        res["category"] = res["dm"].map(CATS).fillna("None")
        res["release_date_est"] = pd.Timestamp(day) + pd.Timedelta(days=2)   # estimate: Thursday release after Tuesday valid date
        if a.drop_none:
            res = res[res["dm"].notna()]
        if len(res):
            tb = pa.Table.from_pandas(res, preserve_index=False)
            writer = writer or pq.ParquetWriter(tmp, tb.schema, compression="zstd")
            writer.write_table(tb.cast(writer.schema)); written += len(res)
        if i % 10 == 0 or i == len(weeks):
            print(f"{i}/{len(weeks)} weeks, {written:,} rows", flush=True)
    if writer is None:
        sys.exit("nothing written (no maps found or all points outside drought)")
    writer.close(); tmp.rename(out)
    print(f"wrote {out}: {written:,} rows")
    if missing:
        print(f"WARNING: {len(missing)} weeks had no readable map, e.g. {missing[:5]}")


def cmd_county(a):
    import requests
    stat = {"area": "GetDroughtSeverityStatisticsByArea", "percent": "GetDroughtSeverityStatisticsByAreaPercent",
            "dsci": "GetDSCI"}[a.measure]
    base = f"https://usdmdataservices.unl.edu/api/CountyStatistics/{stat}"
    s0, e0 = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    frames = []
    for fips in a.fips:
        y = s0.year
        while y <= e0.year:                                   # one request per year to keep responses small
            d0, d1 = max(s0, dt.date(y, 1, 1)), min(e0, dt.date(y, 12, 31))
            q = {"aoi": str(fips).zfill(5), "startdate": f"{d0.month}/{d0.day}/{d0.year}",
                 "enddate": f"{d1.month}/{d1.day}/{d1.year}", "statisticsType": a.statistics_type}
            for i in range(4):
                try:
                    r = requests.get(base, params=q, headers={"Accept": "text/csv"}, timeout=120)
                    if r.status_code == 200:
                        if r.text.strip():
                            df = pd.read_csv(io.StringIO(r.text))
                            df.columns = [c.strip().lower() for c in df.columns]
                            frames.append(df)
                        break
                    if r.status_code in (400, 404):
                        print(f"{fips} {y}: HTTP {r.status_code} {r.text[:120]}", file=sys.stderr); break
                except requests.RequestException:
                    pass
                time.sleep(2 ** (i + 1))
            y += 1
    if not frames:
        sys.exit("no statistics returned")
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(a.out, compression="zstd", index=False)
    print(f"wrote {a.out}: {len(df):,} rows, columns {list(df.columns)}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    w = sp.add_parser("weekly")
    w.add_argument("--bounds"); w.add_argument("--points"); w.add_argument("--state"); w.add_argument("--county")
    w.add_argument("--ids"); w.add_argument("--limit", type=int)
    w.add_argument("--start", required=True, help="YYYY-MM-DD"); w.add_argument("--end", required=True, help="YYYY-MM-DD")
    w.add_argument("--cache", default="./usdm_cache"); w.add_argument("--format", choices=["zip", "json"], default="zip")
    w.add_argument("--url-template", help="override, with {date} = YYYYMMDD")
    w.add_argument("--drop-none", action="store_true", help="write only rows where the point is in drought (D0-D4); absent = None")
    w.add_argument("--max-rows", type=int, default=7_000_000_000)
    w.add_argument("--out", required=True); w.set_defaults(fn=cmd_weekly)
    c = sp.add_parser("county")
    c.add_argument("--fips", nargs="+", required=True, help="5-digit county FIPS codes")
    c.add_argument("--start", required=True); c.add_argument("--end", required=True)
    c.add_argument("--measure", choices=["area", "percent", "dsci"], default="percent")
    c.add_argument("--statistics-type", type=int, choices=[1, 2], default=1, help="1 traditional (cumulative), 2 categorical (per the service docs)")
    c.add_argument("--out", required=True); c.set_defaults(fn=cmd_county)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
