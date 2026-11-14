#!/usr/bin/env python3
"""Whole-dataset processing of the NASS Crop Sequence Boundaries (CSB) geodatabase in batches.

Memory stays flat: the gdb is read in fixed-size batches, each batch is reduced and written to an
on-disk Parquet file in a work directory, and all later steps (stats, rotation, export) run
out-of-core with DuckDB over those files. Ingest is resumable: finished batches are skipped.

Steps
  ingest    gdb -> <work>/attrs/batch_000123.parquet   (attributes + centroid lon/lat; optionally polygons)
  stats     crop acreage per year (whole dataset or filtered)
  rotation  most common crop sequences
  export    one row per field per year -> CSV or Parquet (full dataset or filtered)

Examples
  python csb_pipeline.py ingest CSB1623.gdb --work ./csb_work --batch-size 250000
  python csb_pipeline.py ingest CSB1623.gdb --work ./csb_work --keep-geometry   # also store polygons (large)
  python csb_pipeline.py stats    --work ./csb_work --csv national_stats.csv
  python csb_pipeline.py rotation --work ./csb_work --top 30
  python csb_pipeline.py export   --work ./csb_work --out national_long.parquet
  python csb_pipeline.py export   --work ./csb_work --out iowa_corn.csv --state 19 --crops 1

Needs csb_explore.py in the same folder (CDL code names and helpers).
Deps: pip install geopandas pyogrio pandas pyarrow shapely pyproj duckdb
"""
import argparse, sys, time
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from csb_explore import CDL, AC_TO_HA, find_layer, year_cols  # noqa: E402


# ------------------------------------------------------------------ ingest
def cmd_ingest(a):
    import pyogrio, numpy as np, geopandas as gpd
    from pyproj import Transformer
    layer = find_layer(a.gdb, a.layer)
    info = pyogrio.read_info(a.gdb, layer=layer)
    total, fields = info["features"], list(info["fields"])
    ycols = year_cols(fields)
    attr_cols = [c for c in fields if c.upper() not in ("SHAPE_LENGTH", "SHAPE_AREA")]
    work = Path(a.work)
    (work / "attrs").mkdir(parents=True, exist_ok=True)
    if a.keep_geometry:
        (work / "geom").mkdir(exist_ok=True)
    tr = Transformer.from_crs(info["crs"] or "EPSG:5070", "EPSG:4326", always_xy=True)
    nb = (total + a.batch_size - 1) // a.batch_size
    print(f"{total:,} features, {nb} batches of {a.batch_size:,}; years {[c[3:] for c in ycols]}", flush=True)
    t0 = time.time(); done_rows = 0
    for b in range(nb):
        out = work / "attrs" / f"batch_{b:06d}.parquet"
        if out.exists():
            continue                                   # resume: finished earlier
        df = pyogrio.read_dataframe(a.gdb, layer=layer, columns=attr_cols,
                                    skip_features=b * a.batch_size, max_features=a.batch_size)
        if df.empty:
            continue
        c = df.geometry.centroid                        # metres, EPSG:5070
        lon, lat = tr.transform(c.x.to_numpy(), c.y.to_numpy())
        att = pd.DataFrame(df.drop(columns="geometry"))
        att["centroid_lon"] = np.round(lon, 6)
        att["centroid_lat"] = np.round(lat, 6)
        for y in ycols:
            att[y] = att[y].astype("int16")
        if a.keep_geometry:
            g = gpd.GeoDataFrame(df[["CSBID"]], geometry=df.geometry.to_crs(4326))
            gp = work / "geom" / f"batch_{b:06d}.parquet"
            g.to_parquet(str(gp) + ".tmp", compression="zstd")
            Path(str(gp) + ".tmp").rename(gp)
        tmp = Path(str(out) + ".tmp")                   # write then rename => a crash never leaves a half file
        att.to_parquet(tmp, compression="zstd", index=False)
        tmp.rename(out)
        done_rows += len(df)
        el = time.time() - t0
        print(f"batch {b + 1}/{nb}  rows {len(df):,}  {el / 60:.1f} min elapsed", flush=True)
        del df, att, c
    print("ingest complete ->", work / "attrs")


# ------------------------------------------------------------------ duckdb helpers
def connect(a):
    import duckdb
    files = Path(a.work) / "attrs" / "*.parquet"
    if not list((Path(a.work) / "attrs").glob("batch_*.parquet")):
        sys.exit("no batches found; run ingest first")
    con = duckdb.connect()
    con.execute(f"PRAGMA temp_directory='{Path(a.work) / 'duckdb_tmp'}'")      # spill to disk
    con.execute(f"PRAGMA memory_limit='{a.memory}'")
    con.execute(f"CREATE VIEW csb AS SELECT * FROM read_parquet('{files}')")
    con.register("cdl_names", pd.DataFrame({"cdl_code": list(CDL), "crop": list(CDL.values())}))
    return con


def years(con):
    return sorted(int(c[3:]) for c in [r[0] for r in con.execute("DESCRIBE csb").fetchall()]
                  if c.startswith("CDL") and c[3:].isdigit())


def where(a):
    w = []
    if getattr(a, "state", None): w.append(f"STATEFIPS = '{str(a.state).zfill(2)}'")
    if getattr(a, "county", None): w.append(f"CNTYFIPS = '{str(a.county).zfill(5)}'")
    return ("WHERE " + " AND ".join(w)) if w else ""


def long_sql(con, a):
    """UNION of one SELECT per year -> long format, optional crop filter."""
    ys = years(con)
    crops = ""
    if getattr(a, "crops", None):
        crops = " AND cdl_code IN (" + ",".join(str(int(c)) for c in a.crops) + ")"
    parts = [f"SELECT CSBID, STATEFIPS, CNTYFIPS, CNTY, CSBACRES, centroid_lat, centroid_lon, "
             f"{y} AS year, CDL{y} AS cdl_code FROM csb {where(a)}" for y in ys]
    u = " UNION ALL ".join(parts)
    return (f"SELECT l.*, n.crop FROM ({u}) l LEFT JOIN cdl_names n USING (cdl_code) "
            f"WHERE 1=1 {crops}")


def cmd_stats(a):
    con = connect(a)
    q = (f"SELECT year, cdl_code, coalesce(crop,'code_'||cdl_code) AS crop, "
         f"round(sum(CSBACRES),1) AS acres, round(sum(CSBACRES)*{AC_TO_HA},1) AS hectares, count(*) AS polygons "
         f"FROM ({long_sql(con, a)}) GROUP BY ALL ORDER BY year, acres DESC")
    df = con.execute(q).df()
    for y, g in df.groupby("year"):
        print(f"\n== {y}: top {a.top} ==")
        print(g.head(a.top).drop(columns="year").to_string(index=False))
    if a.csv:
        df.to_csv(a.csv, index=False); print("\nwrote", a.csv)


def cmd_rotation(a):
    con = connect(a)
    ys = years(con)
    seq = " || '>' || ".join(f"CDL{y}::VARCHAR" for y in ys)
    df = con.execute(
        f"SELECT {seq} AS sequence, round(sum(CSBACRES)) AS acres, count(*) AS polygons FROM csb {where(a)} "
        f"GROUP BY 1 ORDER BY acres DESC LIMIT {int(a.top)}").df()
    tot = con.execute(f"SELECT sum(CSBACRES) FROM csb {where(a)}").fetchone()[0]
    df["share_%"] = (100 * df["acres"] / tot).round(2)
    df["named"] = df["sequence"].map(lambda s: ">".join(CDL.get(int(x), f"code_{x}") for x in s.split(">")))
    print("year order:", ys)
    print(df.to_string(index=False))
    if a.csv:
        df.to_csv(a.csv, index=False); print("wrote", a.csv)


def cmd_export(a):
    con = connect(a)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fmt = "PARQUET, COMPRESSION zstd" if out.suffix == ".parquet" else "CSV, HEADER"
    con.execute(f"COPY ({long_sql(con, a)} ORDER BY CSBID, year) TO '{out}' (FORMAT {fmt})")
    print("wrote", out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("ingest")
    i.add_argument("gdb"); i.add_argument("--layer"); i.add_argument("--work", required=True)
    i.add_argument("--batch-size", type=int, default=250_000)
    i.add_argument("--keep-geometry", action="store_true", help="also write polygons (EPSG:4326 GeoParquet, large)")
    i.set_defaults(fn=cmd_ingest)

    def q(s):
        s.add_argument("--work", required=True)
        s.add_argument("--state"); s.add_argument("--county")
        s.add_argument("--memory", default="4GB", help="DuckDB memory limit; excess spills to <work>/duckdb_tmp")
    s = sp.add_parser("stats"); q(s); s.add_argument("--crops", type=int, nargs="*")
    s.add_argument("--top", type=int, default=10); s.add_argument("--csv"); s.set_defaults(fn=cmd_stats)
    r = sp.add_parser("rotation"); q(r); r.add_argument("--top", type=int, default=20); r.add_argument("--csv"); r.set_defaults(fn=cmd_rotation)
    e = sp.add_parser("export"); q(e); e.add_argument("--out", required=True, help=".csv or .parquet")
    e.add_argument("--crops", type=int, nargs="*", help="keep only these CDL codes (per field-year row)")
    e.set_defaults(fn=cmd_export)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
