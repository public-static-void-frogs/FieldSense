#!/usr/bin/env python3
"""NASA MSLSP30NA (HLS-based Land Surface Phenology, 30 m, North America, MEaSUREs) sampled at the field centroids.

Why: ready-made phenometrics (green-up onset / midpoint, maturity, peak, senescence, dormancy; up to 2 cycles per year) from the same HLS data that
crop_ts uses - an independent check of the M1 phenology extraction (green-up, peak, senescence dates) and a source of dates for the field calendar.

Two ways to get the tiles:
  online : --years ... : CMR search by the state's bounding box (earthaccess) and download of the matching tile files into --cache
           (needs EARTHDATA_USERNAME / EARTHDATA_PASSWORD; credentials only go to urs.earthdata.nasa.gov, like csb_smap.py)
  local  : --local-dir D:/mslsp  : use tile files you already have (.nc, or .tif named like <layer>_<tile>_<year>.tif)

Input : --attrs <work>/attrs (batch_*.parquet: CSBID, STATEFIPS, centroid_lon, centroid_lat); --state all | 19 | 19,20
        (tile by tile: a tile only touches the fields inside its lon/lat box; online mode searches the bbox of the selected fields)
Output: <out>/mslsp_field_year.parquet  CSBID, year, mslsp_<metric>_c1, mslsp_<metric>_c2 ... = day of year relative to 1 Jan of `year`
        (negative = the previous calendar year; >365 = next year; NaN = no cycle / no data), plus mslsp_ncycles when present.
Metrics (matched case-insensitively on the layer name): OGI greenup onset, 50PCGI greenup midpoint, OGMX maturity onset, PEAK, OGD senescence
onset, 50PCGD senescence midpoint, OGMN dormancy onset.  Layer values are days since 1970-01-01 in the product; if your files differ,
the script prints the layer names it found and what it assumed.
Caveats: MSLSP is tuned for vegetation in general, not crop calendars - treat it as a cross-check of M1, not as ground truth. Cropland with
two peaks per year (double crop) is represented by its two cycles. Layer names/units and the CMR short name (MSLSP30NA) are from the product guide
and were NOT tested against the live files by the author.

Example: python ext_mslsp.py --attrs ./csb_work/attrs --state 19 --years 2018 2019 2020 2021 2022 --out ./ext
         python ext_mslsp.py --attrs ./csb_work/attrs --state 19 --local-dir D:/mslsp --out ./ext
Deps: pip install duckdb pandas pyarrow numpy rasterio pyproj ; online also earthaccess requests
"""
import argparse, datetime as dt, os, re, sys
from pathlib import Path
import numpy as np
import pandas as pd

SHORT_NAME = "MSLSP30NA"
KEYS = [("50PCGI", "greenup_mid"), ("50PCGD", "senescence_mid"), ("OGI", "greenup_onset"), ("OGMX", "maturity_onset"), ("PEAK", "peak"),
        ("OGD", "senescence_onset"), ("OGMN", "dormancy_onset"), ("NUMCYCLES", "ncycles")]
EPOCH = dt.date(1970, 1, 1)


def state_sql(state, col="STATEFIPS"):
    """--state: 'all', one FIPS ('19') or a comma list ('19,20')"""
    st = str(state).strip().lower()
    if st in ("all", "*", ""):
        return "TRUE"
    return f"{col} IN (" + ",".join(f"'{x.strip().zfill(2)}'" for x in st.split(",")) + ")"


def fields(a):
    """CSBID (Arrow string, compact), lon, lat for the selected states; all ~16 M fields fit in a few hundred MB this way"""
    import duckdb, pyarrow as pa
    rel = duckdb.connect().execute(
        f"SELECT CSBID, centroid_lon AS lon, centroid_lat AS lat FROM read_parquet('{(Path(a.attrs) / 'batch_*.parquet').as_posix()}') "
        f"WHERE {state_sql(a.state)} AND isfinite(centroid_lon) AND isfinite(centroid_lat) AND centroid_lon BETWEEN -180 AND 180 AND centroid_lat BETWEEN -90 AND 90")
    for meth in ("to_arrow_table", "fetch_arrow_table", "arrow"):          # method name differs between DuckDB versions
        if hasattr(rel, meth):
            t = getattr(rel, meth)(); break
    df = t.to_pandas(types_mapper={pa.string(): pd.ArrowDtype(pa.string()), pa.large_string(): pd.ArrowDtype(pa.large_string())}.get)
    if df.empty: sys.exit("no fields for this state in --attrs")
    return df


def layer_key(name):
    n = re.sub(r"[^A-Z0-9]", "", name.upper())
    for k, label in KEYS:
        if n.startswith(k): return label
    return None


def year_of(path):
    m = re.findall(r"(20\d\d)", Path(path).name)
    return int(m[-1]) if m else None


def layers_of(path):
    """list of (label, raster path) in one tile file"""
    import rasterio
    p = str(path)
    if p.lower().endswith((".tif", ".tiff")):
        lab = layer_key(Path(p).name)
        return [(lab or Path(p).stem.lower(), p)]
    with rasterio.open(p) as ds:
        subs = list(ds.subdatasets)
    if not subs:
        return [(layer_key(Path(p).name) or Path(p).stem, p)]
    out = []
    for s in subs:
        var = s.split(":")[-1]; lab = layer_key(var)
        if lab: out.append((f"{lab}" if layer_key(var) not in [o[0] for o in out] else f"{lab}_{var.lower()}", s))
    if not out:
        print(f"  {Path(p).name}: no known layer among {[s.split(':')[-1] for s in subs]}", file=sys.stderr)
    return out


def sample_tile(path, year, df):
    """sample every layer of one tile at the fields inside it -> DataFrame (CSBID + columns) or None"""
    import rasterio
    from pyproj import Transformer
    cols = {}; idx = None
    lay = layers_of(path)
    if not lay: return None
    with rasterio.open(lay[0][1]) as d0:                                       # keep only the fields inside this tile (cheap box test first)
        if d0.crs is None: return None
        from rasterio.warp import transform_bounds
        w, s_, e, n = transform_bounds(d0.crs, "EPSG:4326", *d0.bounds)
    df = df[(df["lon"] >= w) & (df["lon"] <= e) & (df["lat"] >= s_) & (df["lat"] <= n)]
    if df.empty: return None
    for label, src in lay:
        with rasterio.open(src) as ds:
            if ds.crs is None:
                print(f"  {Path(str(src).split(':')[1] if str(src).lower().startswith('netcdf') else str(src)).name}: layer {label} has no CRS; skipped", file=sys.stderr); continue
            tr = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
            x, y = tr.transform(df["lon"].to_numpy(), df["lat"].to_numpy())
            rows, cols_ = rasterio.transform.rowcol(ds.transform, x, y); rows, cols_ = np.asarray(rows), np.asarray(cols_)
            ok = (rows >= 0) & (rows < ds.height) & (cols_ >= 0) & (cols_ < ds.width)
            if not ok.any(): return None
            if idx is None: idx = np.where(ok)[0]
            r0, r1, c0, c1 = rows[ok].min(), rows[ok].max() + 1, cols_[ok].min(), cols_[ok].max() + 1
            arr = ds.read(window=rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)).astype("float64"); nod = ds.nodata
        for b in range(arr.shape[0]):
            v = arr[b]
            if nod is not None: v[v == nod] = np.nan
            v[(v >= 32767) | (v <= 0)] = np.nan
            vals = np.full(len(df), np.nan); vals[ok] = v[rows[ok] - r0, cols_[ok] - c0]
            if label != "ncycles":
                # days since 1970-01-01 -> day of year relative to 1 Jan of `year`
                vals = vals - (dt.date(year, 1, 1) - EPOCH).days
            cols[f"mslsp_{label}" + (f"_c{b + 1}" if label != "ncycles" else "")] = vals
    if not cols: return None
    out = pd.DataFrame(cols); out.insert(0, "CSBID", df["CSBID"].to_numpy()); out.insert(1, "year", year)
    return out[out.drop(columns=["CSBID", "year"]).notna().any(axis=1)]


def clean_download(url, dst, user, pw, auth_host="urs.earthdata.nasa.gov"):
    import requests
    from urllib.parse import urljoin, urlparse
    s = requests.Session(); cur = url
    for _ in range(15):
        kw = {"auth": (user, pw)} if urlparse(cur).netloc == auth_host else {}
        r = s.get(cur, allow_redirects=False, stream=True, timeout=300, **kw)
        if r.status_code in (301, 302, 303, 307, 308):
            cur = urljoin(cur, r.headers["Location"]); r.close(); continue
        if r.status_code != 200:
            r.close(); return False
        part = Path(str(dst) + ".part"); part.parent.mkdir(parents=True, exist_ok=True)
        with open(part, "wb") as fh:
            for ch in r.iter_content(1 << 20): fh.write(ch)
        part.replace(dst); return True
    return False


def online_files(a, df):
    import earthaccess
    user, pw = os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    if not (user and pw): sys.exit("set EARTHDATA_USERNAME and EARTHDATA_PASSWORD (or use --local-dir)")
    earthaccess.login(strategy="environment")
    bb = (float(df["lon"].min()), float(df["lat"].min()), float(df["lon"].max()), float(df["lat"].max()))
    seen = set()
    for y in a.years:
        res = earthaccess.search_data(short_name=SHORT_NAME, bounding_box=bb, temporal=(f"{y}-01-01", f"{y}-12-31"))
        print(f"{y}: {len(res)} granules for bbox {tuple(round(v, 2) for v in bb)}", flush=True)
        for g in res:
            links = [l for l in g.data_links() if l.lower().endswith((".nc", ".nc4", ".tif"))]
            for l in links:
                name = l.rsplit("/", 1)[-1]
                if name in seen: continue
                seen.add(name); f = Path(a.cache) / name
                if not f.exists() and not clean_download(l, f, user, pw):
                    try: earthaccess.download([l], str(a.cache))
                    except Exception as e: print(f"  {name}: download failed ({type(e).__name__})", file=sys.stderr); continue
                yield f, (year_of(name) or y)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--attrs", required=True); p.add_argument("--state", default="all", help="all | FIPS | FIPS,FIPS"); p.add_argument("--out", required=True)
    p.add_argument("--years", type=int, nargs="+"); p.add_argument("--local-dir"); p.add_argument("--cache", default="./ext_cache")
    p.add_argument("--keep-files", action="store_true")
    a = p.parse_args(); Path(a.out).mkdir(parents=True, exist_ok=True); Path(a.cache).mkdir(parents=True, exist_ok=True)
    df = fields(a); print(f"{len(df):,} fields", flush=True)
    if a.local_dir:
        files = [(f, year_of(f)) for f in sorted(Path(a.local_dir).glob("*")) if f.suffix.lower() in (".nc", ".nc4", ".tif", ".tiff")]
        if a.years: files = [(f, y) for f, y in files if y in a.years]
        if not files: sys.exit("no tile files (.nc/.tif) for the requested years in --local-dir")
        src = iter(files)
    else:
        if not a.years: sys.exit("--years is required in online mode")
        src = online_files(a, df)
    parts = []
    for f, y in src:
        if y is None: print(f"  {Path(f).name}: cannot read the year from the file name; skipped", file=sys.stderr); continue
        r = sample_tile(f, y, df)
        print(f"  {Path(f).name}: {0 if r is None else len(r):,} fields with phenology", flush=True)
        if r is not None: parts.append(r)
        if not a.local_dir and not a.keep_files: Path(f).unlink(missing_ok=True)
    if not parts: sys.exit("no field fell on any tile / no layer matched (see messages above)")
    d = pd.concat(parts, ignore_index=True)
    d = d.groupby(["CSBID", "year"], as_index=False).first()                 # a field on two overlapping tiles keeps the first non-null value
    fn = Path(a.out) / "mslsp_field_year.parquet"; d.to_parquet(fn, compression="zstd", index=False)
    print(f"wrote {fn} ({len(d):,} field-years, columns: {[c for c in d.columns if c.startswith('mslsp_')]})")


if __name__ == "__main__":
    main()