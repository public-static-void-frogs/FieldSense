#!/usr/bin/env python3
"""Gridded weather / drought / soil-moisture sources for the rule engine (section 4.5 of the proposal), sampled at the cells that hold fields.

  gridmet : gridMET daily (4 km, 1979-now): pr, tmmx, tmmn, pet (grass reference ETo), etr (alfalfa), vpd ...   -> m6 (FAO-56 ETo check), m5, m7
  eddi    : NOAA PSL EDDI (evaporative demand drought index, ~4 km, one map per week)                         -> M2 drought years (physical, not an expert map)
  nldas   : NLDAS-2 Noah soil moisture (0.125 deg, 1979-now) daily snapshot at --hour UTC                     -> M3 Fallow-Zero / m9 with a long history (SMAP L4 only has 2015+)

Same contract as yield_weather.py --level cell: field -> cell via a field_cell_map, one daily table per cell.
Input : --attrs <work>/attrs (batch_*.parquet with CSBID, STATEFIPS, centroid_lon, centroid_lat; from csb_pipeline.py ingest)
        --state all | 19 | 19,20   (default all). 'all' = every state in --attrs; fields are read batch by batch.
        gridmet writes WIDE part files per year and cell chunk into <out>/gridmet_daily/ (all-US = billions of values: use few --vars).
Output: <out>/<src>_field_cell_map.parquet  CSBID, cell_id            (cell_id = "<lat>_<lon>" of the cell centre)
        <out>/<src>_cells.parquet           cell_id, cell_lat, cell_lon
        <out>/gridmet_daily.parquet         cell_id, date, gridmet_<var> ...
        <out>/eddi_weekly.parquet           cell_id, date, eddi_<timescale>
        <out>/nldas_daily.parquet           cell_id, date, nldas_vsm_<layer> (m3/m3), nldas_soilm_<layer> (kg/m2)
Work is split into resumable part files (<out>/<src>_parts/*.parquet) and merged at the end; delete a part to redo it.

Endpoints are defaults taken from the data providers' documented layout and were NOT tested against the live servers from the author's
environment: every URL is a --url-template you can change, and a failure prints the URL it tried and the HTTP status.

Examples
  python ext_gridded.py gridmet --attrs ./csb_work/attrs --state all --years 2018 2019 2020 2021 2022 2023 2024 2025 --out ./ext
  python ext_gridded.py eddi    --attrs ./csb_work/attrs --state 19 --start 2018-01-01 --end 2025-12-31 --timescale 04wk --out ./ext
  python ext_gridded.py nldas   --attrs ./csb_work/attrs --state 19 --start 2018-01-01 --end 2025-12-31 --out ./ext     # needs EARTHDATA_USERNAME/PASSWORD
Deps: pip install duckdb pandas pyarrow numpy xarray netCDF4 requests ; nldas also: earthaccess
"""
import argparse, datetime as dt, os, re, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

GRIDMET_URL = "https://www.northwestknowledge.net/metdata/data/{var}_{year}.nc"
GRIDMET_NAMES = {"pr": "pr_mm", "tmmx": "tmax_c", "tmmn": "tmin_c", "pet": "eto_grass_mm", "etr": "etr_alfalfa_mm", "vpd": "vpd_kpa",
                 "srad": "srad_wm2", "vs": "wind_ms", "rmax": "rhmax_pct", "rmin": "rhmin_pct", "sph": "sph_kgkg"}
EDDI_URL = "https://downloads.psl.noaa.gov/Projects/EDDI/CONUS_archive/data/{year}/EDDI_ETrs_{ts}_{ymd}.asc"
NLDAS_SHORT, NLDAS_VERSION = "NLDAS_NOAH0125_H", "2.0"
NLDAS_VARS = ["SoilM_0_10cm", "SoilM_10_40cm", "SoilM_40_100cm", "SoilM_0_100cm"]
NLDAS_STEP = 0.125


# ------------------------------------------------------------------ helpers
def nearest(axis, vals):
    """index of the nearest axis value for every val (axis may be ascending or descending) and the distance"""
    axis = np.asarray(axis, float); vals = np.asarray(vals, float)
    order = np.argsort(axis); s = axis[order]
    i = np.clip(np.searchsorted(s, vals), 1, len(s) - 1)
    pick = np.where(np.abs(vals - s[i - 1]) <= np.abs(vals - s[i]), i - 1, i)
    return order[pick], np.abs(vals - s[pick])


def cid(lat, lon):
    return np.char.add(np.char.add(np.round(lat, 4).astype(str), "_"), np.round(lon, 4).astype(str))


def state_sql(state, col="STATEFIPS"):
    """--state: 'all', one FIPS ('19') or a comma list ('19,20')"""
    s = str(state).strip().lower()
    if s in ("all", "*", ""):
        return "TRUE"
    return f"{col} IN (" + ",".join(f"'{x.strip().zfill(2)}'" for x in s.split(",")) + ")"


def centroid_batches(a):
    """yield DataFrames (CSBID, lon, lat) one attrs batch file at a time: never all ~16 M fields in memory"""
    import duckdb
    files = sorted(Path(a.attrs).glob("batch_*.parquet"))
    if not files:
        sys.exit("no batch_*.parquet in --attrs")
    con = duckdb.connect()
    for i, f in enumerate(files):
        df = con.execute(f"SELECT CSBID, centroid_lon AS lon, centroid_lat AS lat FROM read_parquet('{f.as_posix()}') "
                         f"WHERE {state_sql(a.state)} AND isfinite(centroid_lon) AND isfinite(centroid_lat) AND centroid_lon BETWEEN -180 AND 180 AND centroid_lat BETWEEN -90 AND 90").df()
        if len(df):
            yield i, df


def build_map(a, name, lat_axis, lon_axis, step):
    """snap field centroids to the grid, batch by batch; write <name>_field_cell_map.parquet and <name>_cells.parquet; return cells DataFrame"""
    import duckdb, shutil
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    cm_f, ce_f = out / f"{name}_field_cell_map.parquet", out / f"{name}_cells.parquet"
    if cm_f.exists() and ce_f.exists() and not a.rebuild_map:
        return pd.read_parquet(ce_f)
    mp = out / f"{name}_map_parts"
    shutil.rmtree(mp, ignore_errors=True)
    lat_axis = np.asarray(lat_axis, float); lon_axis = np.asarray(lon_axis, float)
    cells, n_in, n_out = [], 0, 0
    for i, df in centroid_batches(a):
        iy, dy = nearest(lat_axis, df["lat"].to_numpy()); ix, dx = nearest(lon_axis, df["lon"].to_numpy())
        ok = (dy <= step) & (dx <= step)
        n_in += int(ok.sum()); n_out += int((~ok).sum())
        if not ok.any():
            continue
        lat_c, lon_c = lat_axis[iy][ok], lon_axis[ix][ok]
        ids = cid(lat_c, lon_c)
        write_part(pd.DataFrame({"CSBID": df["CSBID"].to_numpy()[ok], "cell_id": ids}), mp / f"m_{i:06d}.parquet")
        c = pd.DataFrame({"cell_id": ids, "cell_lat": lat_c, "cell_lon": lon_c}).drop_duplicates("cell_id")
        cells.append(c)
        if len(cells) >= 50:
            cells = [pd.concat(cells).drop_duplicates("cell_id")]
    if not n_in:
        sys.exit(f"no field centroid falls on the {name} grid (check --state / grid coverage)")
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM read_parquet('{(mp / '*.parquet').as_posix()}')) TO '{cm_f.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    shutil.rmtree(mp, ignore_errors=True)
    cells = pd.concat(cells).drop_duplicates("cell_id").reset_index(drop=True)
    cells.to_parquet(ce_f, compression="zstd", index=False)
    print(f"{name}: {n_in:,} fields -> {len(cells):,} cells ({n_out:,} fields outside the grid)", flush=True)
    return cells


def get_file(url, dst, retries=4, auth=None):
    """streaming download with resume (.part); returns True when the file is complete"""
    import requests
    dst = Path(dst); part = Path(str(dst) + ".part"); dst.parent.mkdir(parents=True, exist_ok=True)
    for t in range(retries):
        try:
            have = part.stat().st_size if part.exists() else 0
            r = requests.get(url, stream=True, timeout=120, headers={"Range": f"bytes={have}-"} if have else {}, auth=auth)
            if r.status_code == 416:
                part.replace(dst); return True
            if r.status_code not in (200, 206):
                print(f"  HTTP {r.status_code} for {url}", file=sys.stderr)
                if r.status_code in (400, 401, 403, 404): return False
                time.sleep(2 * (t + 1)); continue
            with open(part, "ab" if r.status_code == 206 else "wb") as fh:
                for chunk in r.iter_content(1 << 20): fh.write(chunk)
            part.replace(dst); return True
        except Exception as e:
            print(f"  {type(e).__name__}: {str(e)[:100]} (retry {t + 1})", file=sys.stderr); time.sleep(2 * (t + 1))
    return False


def write_part(df, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp"); df.to_parquet(tmp, compression="zstd", index=False); tmp.replace(path)


def merge(a, name, parts_dir, out_name, wide_sql=None):
    import duckdb
    files = sorted(Path(parts_dir).glob("*.parquet"))
    if not files:
        sys.exit(f"no {name} parts were produced")
    con = duckdb.connect(); con.execute(f"PRAGMA memory_limit='{a.memory}'")
    con.execute(f"PRAGMA temp_directory='{(Path(a.out) / '_duckdb_spill').as_posix()}'")
    src = f"read_parquet('{(Path(parts_dir) / '*.parquet').as_posix()}', union_by_name=true)"
    dst = Path(a.out) / out_name
    q = wide_sql(con, src) if wide_sql else f"SELECT * FROM {src}"
    con.execute(f"COPY ({q} ORDER BY cell_id, date) TO '{dst.as_posix()}.tmp' (FORMAT PARQUET, COMPRESSION ZSTD)")
    Path(str(dst) + ".tmp").replace(dst)
    n = con.execute(f"SELECT count(*) FROM read_parquet('{dst.as_posix()}')").fetchone()[0]
    print(f"wrote {dst} ({n:,} rows)")


# ------------------------------------------------------------------ gridMET
def read_gridmet_nc(path, cells, slab=31):
    """read the cell list from one annual gridMET NetCDF in time slabs (the file is read once, sequentially) -> (days, array[time, cell])"""
    import xarray as xr
    with xr.open_dataset(path) as ds:
        v = next(k for k, x in ds.data_vars.items() if x.ndim == 3)
        da = ds[v]
        latn = next(d for d in da.dims if d.lower().startswith("lat")); lonn = next(d for d in da.dims if d.lower().startswith("lon"))
        tn = next(d for d in da.dims if d not in (latn, lonn))
        iy, _ = nearest(ds[latn].values, cells["cell_lat"].to_numpy()); ix, _ = nearest(ds[lonn].values, cells["cell_lon"].to_numpy())
        da = da.transpose(tn, latn, lonn); n_t = da.sizes[tn]
        arr = np.empty((n_t, len(iy)), dtype="float32")
        for t0 in range(0, n_t, slab):
            blk = da.isel({tn: slice(t0, t0 + slab)}).values.astype("float32")
            arr[t0:t0 + blk.shape[0]] = blk[:, iy, ix]
        units = str(da.attrs.get("units", "")); days = pd.to_datetime(ds[tn].values).normalize()
    if units.strip().upper() in ("K", "KELVIN"):
        arr = arr - 273.15
    return days, arr


def cmd_gridmet(a):
    """per year: download every variable file, then write WIDE part files per cell chunk (<out>/gridmet_daily/gridmet_<year>_c<k>.parquet).
    Wide parts avoid a huge pivot; --merge also writes one sorted gridmet_daily.parquet (only sensible for a few states)."""
    out = Path(a.out); parts = out / "gridmet_daily"
    ce_f = out / "gridmet_cells.parquet"
    cells = pd.read_parquet(ce_f) if (ce_f.exists() and not a.rebuild_map) else None
    nchunks = lambda: -(-len(cells) // a.cell_chunk)
    for y in a.years:
        current = (y == dt.date.today().year)
        if cells is not None and not current and (parts / f"gridmet_{y}_c{nchunks() - 1:04d}.parquet").exists():
            print(f"{y}: done", flush=True); continue
        files = {}
        for v in a.vars:
            nc = Path(a.cache) / f"{v}_{y}.nc"
            if current and nc.exists():
                nc.unlink()                                  # the current-year file grows daily
            url = a.url_template.format(var=v, year=y)
            print(f"{v} {y}: {url}", flush=True)
            if not nc.exists() and not get_file(url, nc):
                print(f"  could not download {v} {y}; skipped", file=sys.stderr); continue
            files[v] = nc
        if not files:
            continue
        if cells is None:
            import xarray as xr
            with xr.open_dataset(next(iter(files.values()))) as ds:
                da = ds[next(k for k, x in ds.data_vars.items() if x.ndim == 3)]
                la = ds[next(d for d in da.dims if d.lower().startswith("lat"))].values
                lo = ds[next(d for d in da.dims if d.lower().startswith("lon"))].values
            cells = build_map(a, "gridmet", la, lo, step=0.05)
        per, grp = a.cell_chunk, a.group
        for kk in range(0, nchunks(), grp):
            ks = list(range(kk, min(kk + grp, nchunks())))
            pfs = {k: parts / f"gridmet_{y}_c{k:04d}.parquet" for k in ks}
            if all(p.exists() for p in pfs.values()) and not current:
                continue
            cs = cells.iloc[ks[0] * per:(ks[-1] + 1) * per].reset_index(drop=True)
            data, days = {}, None
            for v, nc in files.items():
                days, data[v] = read_gridmet_nc(nc, cs)                  # each variable file is read once per group of chunks
            for k in ks:
                lo, hi = (k - ks[0]) * per, min((k - ks[0] + 1) * per, len(cs))
                n_p = hi - lo
                wide = {"cell_id": np.tile(cs["cell_id"].to_numpy()[lo:hi], len(days)), "date": np.repeat(days.values, n_p)}
                for v, arr in data.items():
                    wide[f"gridmet_{GRIDMET_NAMES.get(v, v)}"] = arr[:, lo:hi].reshape(-1)
                write_part(pd.DataFrame(wide), pfs[k])
            print(f"  {y} chunks {ks[0] + 1}-{ks[-1] + 1}/{nchunks()} written", flush=True)
            del data
        if not a.keep_files:
            for nc in files.values(): nc.unlink(missing_ok=True)
    if a.merge:
        merge(a, "gridmet", parts, "gridmet_daily.parquet")
    else:
        print(f"wrote part files in {parts} - read them with read_parquet('{(parts / '*.parquet').as_posix()}'); add --merge for one sorted file")


# ------------------------------------------------------------------ EDDI
def read_asc(path):
    with open(path) as f:
        h = {}
        for _ in range(6):
            k, v = f.readline().split(); h[k.lower()] = float(v)
        arr = np.loadtxt(f, dtype="float32")
    nod = h.get("nodata_value", -9999.0); arr[arr == nod] = np.nan
    n = int(h["nrows"]); cs = h["cellsize"]
    lat = h["yllcorner"] + cs * (n - np.arange(n) - 0.5); lon = h["xllcorner"] + cs * (np.arange(int(h["ncols"])) + 0.5)
    return arr, lat, lon, cs


def cmd_eddi(a):
    parts = Path(a.out) / "eddi_parts"; cells = None
    d0, d1 = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    days = [d0 + dt.timedelta(days=i) for i in range(0, (d1 - d0).days + 1, a.step_days)]
    by_year = {}
    for d in days: by_year.setdefault(d.year, []).append(d)
    miss = 0
    for y, ds_ in by_year.items():
        pf = parts / f"eddi_{a.timescale}_{y}.parquet"
        if pf.exists() and y < dt.date.today().year:
            continue
        rows = []
        for d in ds_:
            url = a.url_template.format(year=d.year, ts=a.timescale, ymd=d.strftime("%Y%m%d"))
            f = Path(a.cache) / f"EDDI_{a.timescale}_{d:%Y%m%d}.asc"
            if not f.exists() and not get_file(url, f):
                miss += 1; continue
            arr, lat, lon, cs = read_asc(f)
            if cells is None:
                cells = build_map(a, "eddi", lat, lon, step=cs * 1.01)
            iy, _ = nearest(lat, cells["cell_lat"].to_numpy()); ix, _ = nearest(lon, cells["cell_lon"].to_numpy())
            rows.append(pd.DataFrame({"cell_id": cells["cell_id"], "date": pd.Timestamp(d), f"eddi_{a.timescale}": arr[iy, ix]}))
            if not a.keep_files: f.unlink(missing_ok=True)
        if rows:
            write_part(pd.concat(rows, ignore_index=True), pf); print(f"eddi {y}: {len(rows)} maps", flush=True)
    if miss:
        print(f"{miss} maps could not be downloaded (check --url-template / dates; EDDI maps can be missing for some dates)", file=sys.stderr)
    merge(a, "eddi", parts, "eddi_weekly.parquet")


# ------------------------------------------------------------------ NLDAS-2
def thickness_mm(name):
    m = re.search(r"_(\d+)_(\d+)cm", name)
    return (int(m.group(2)) - int(m.group(1))) * 10.0 if m else None


def read_nldas_nc(path, cells, want):
    """one hourly NLDAS Noah file -> {cell_id, <var>} DataFrame for the cell list; reports variable names if a wanted one is absent"""
    import xarray as xr
    with xr.open_dataset(path) as ds:
        have = [v for v in want if v in ds.data_vars]
        if not have:
            raise KeyError(f"none of {want} in file; variables present: {sorted(ds.data_vars)}")
        latn = next(d for d in ds.dims if d.lower().startswith("lat")); lonn = next(d for d in ds.dims if d.lower().startswith("lon"))
        iy, _ = nearest(ds[latn].values, cells["cell_lat"].to_numpy()); ix, _ = nearest(ds[lonn].values, cells["cell_lon"].to_numpy())
        out = {"cell_id": cells["cell_id"].to_numpy()}
        for v in have:
            da = ds[v]
            if "time" in da.dims: da = da.isel(time=0)
            arr = da.values.astype("float32"); arr = np.where(arr < -1e3, np.nan, arr)[iy, ix]
            out[f"nldas_soilm_{v.split('SoilM_')[-1].replace('cm', '')}"] = arr
            th = thickness_mm(v)
            if th: out[f"nldas_vsm_{v.split('SoilM_')[-1].replace('cm', '')}"] = arr / th      # kg/m2 over th mm -> m3/m3
    return pd.DataFrame(out)


def clean_download(url, dst, user, pw, auth_host="urs.earthdata.nasa.gov"):
    """Earthdata download; credentials are sent only to the login host (see csb_smap.py)"""
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


def cmd_nldas(a):
    import earthaccess
    user, pw = os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    if not (user and pw):
        sys.exit("set EARTHDATA_USERNAME and EARTHDATA_PASSWORD")
    cells = build_map(a, "nldas", np.arange(25.0625, 52.99, NLDAS_STEP), np.arange(-124.9375, -67.0, NLDAS_STEP), step=NLDAS_STEP * 0.75)
    parts = Path(a.out) / "nldas_parts"
    d0, d1 = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    months = sorted({(d0 + dt.timedelta(days=i)).strftime("%Y-%m") for i in range(0, (d1 - d0).days + 1)})
    earthaccess.login(strategy="environment")
    for ym in months:
        pf = parts / f"nldas_{ym}.parquet"
        if pf.exists() and ym < dt.date.today().strftime("%Y-%m"):
            continue
        y, m = map(int, ym.split("-"))
        m0 = max(dt.date(y, m, 1), d0); m1 = min((dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)), d1)
        res = earthaccess.search_data(short_name=NLDAS_SHORT, version=a.version, temporal=(m0.isoformat(), (m1 + dt.timedelta(days=1)).isoformat()))
        if not res:
            res = earthaccess.search_data(short_name=NLDAS_SHORT, temporal=(m0.isoformat(), (m1 + dt.timedelta(days=1)).isoformat()))
        pat = re.compile(r"\.A(\d{8})\.(\d{2})00\.")
        sel = []
        for g in res:
            try: link = [l for l in g.data_links() if l.endswith(".nc4")][0]
            except Exception: continue
            mt = pat.search(link)
            if mt and int(mt.group(2)) == a.hour: sel.append((mt.group(1), link))
        print(f"{ym}: {len(res)} hourly granules found, {len(sel)} at {a.hour:02d} UTC", flush=True)
        rows = []
        for ymd, link in sel:
            f = Path(a.cache) / link.rsplit("/", 1)[-1]
            if not f.exists() and not clean_download(link, f, user, pw):
                try: earthaccess.download([link], str(a.cache))
                except Exception as e:
                    print(f"  {ymd}: download failed ({type(e).__name__})", file=sys.stderr); continue
            try:
                df = read_nldas_nc(f, cells, a.vars); df.insert(1, "date", pd.Timestamp(f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}")); rows.append(df)
            except KeyError as e:
                sys.exit(str(e))
            if not a.keep_files: f.unlink(missing_ok=True)
        if rows:
            write_part(pd.concat(rows, ignore_index=True), pf)
    merge(a, "nldas", parts, "nldas_daily.parquet")


# ------------------------------------------------------------------ CLI
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    def common(s, fn):
        s.set_defaults(fn=fn)
        s.add_argument("--attrs", required=True); s.add_argument("--state", default="all", help="all | FIPS | FIPS,FIPS"); s.add_argument("--out", required=True)
        s.add_argument("--cache", default="./ext_cache"); s.add_argument("--keep-files", action="store_true", help="keep downloaded source files in --cache")
        s.add_argument("--memory", default="2GB"); s.add_argument("--rebuild-map", action="store_true")

    g = sp.add_parser("gridmet", help="gridMET annual NetCDF files -> daily cell table"); common(g, cmd_gridmet)
    g.add_argument("--years", type=int, nargs="+", required=True)
    g.add_argument("--vars", nargs="+", default=["pr", "tmmx", "tmmn", "pet", "vpd"], help="gridMET variable file names (pr tmmx tmmn pet etr vpd srad vs ...)")
    g.add_argument("--url-template", default=GRIDMET_URL)
    g.add_argument("--cell-chunk", type=int, default=10000, help="cells per part file"); g.add_argument("--group", type=int, default=5, help="part files built from one read of each source file (memory ~ group x chunk x days x vars x 4 B)"); g.add_argument("--merge", action="store_true", help="also write one sorted gridmet_daily.parquet")
    e = sp.add_parser("eddi", help="EDDI weekly maps -> weekly cell table"); common(e, cmd_eddi)
    e.add_argument("--start", required=True); e.add_argument("--end", required=True)
    e.add_argument("--timescale", default="04wk", help="01wk..12wk, 01mn..12mn (default 04wk)"); e.add_argument("--step-days", type=int, default=7)
    e.add_argument("--url-template", default=EDDI_URL)
    n = sp.add_parser("nldas", help="NLDAS-2 Noah soil moisture -> daily cell table"); common(n, cmd_nldas)
    n.add_argument("--start", required=True); n.add_argument("--end", required=True)
    n.add_argument("--hour", type=int, default=12, help="UTC hour of the daily snapshot (default 12)")
    n.add_argument("--vars", nargs="+", default=NLDAS_VARS); n.add_argument("--version", default=NLDAS_VERSION)
    a = p.parse_args(); Path(a.cache).mkdir(parents=True, exist_ok=True); a.fn(a)


if __name__ == "__main__":
    main()