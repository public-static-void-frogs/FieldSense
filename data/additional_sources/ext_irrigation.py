#!/usr/bin/env python3
"""Irrigation and groundwater context per field - replaces 'irrigation = what the farmer typed' with checkable evidence (hard rule m7 > irrigation_available, m8).

  raster  : sample irrigated-area GeoTIFF(s) (e.g. USGS MIrAD-US, LANID, AIM-HPA, IrrMapper downloads) at the field centroids
            -> irr_<label> (0/1 at the centroid), irr_share_<label> (share of irrigated pixels in a (2k+1)^2 window, default 3x3), county acre-weighted share
  wells   : USGS NWIS groundwater levels (depth to water below land surface, parameter 72019) for a state -> per-well spring depth and 5-year trend
            -> assigned to a ~2 km grid of the field centroids from the nearest wells within --radius-km:
               gw_depth_spring_m (+ = deeper), gw_trend_5y_m_per_yr (+ = water table falling), gw_n_wells, gw_nearest_km
  pumping : generic reader of a pumping / water-use CSV that YOU export (e.g. Kansas WIMAS: one row per point of diversion and year with
            latitude, longitude, year, acre-feet) -> acre-feet and mm-equivalent pumped within --radius-km of each grid point per year.

Input : --attrs <work>/attrs (batch_*.parquet: CSBID, STATEFIPS, CNTYFIPS, CSBACRES, centroid_lon, centroid_lat); --state all | 20 | 19,20
        (fields are processed one attrs batch at a time / in DuckDB; 'wells' fetches NWIS for every state present)
Output: <out>/irrigation_field.parquet, irrigation_county.parquet                          (raster)
        <out>/gw_grid_year.parquet (grid_id, year, gw_*), <out>/gw_field_grid_map.parquet   (wells; join CSBID -> grid_id -> year)
        <out>/pumping_grid_year.parquet                                                      (pumping)
Raster notes: a raster is read only inside the state's extent (window) and may be in any CRS. --values lists the pixel values that mean
'irrigated' (default: any value > 0, after removing --nodata). Label your rasters by the year they describe: --raster 2017=D:/MIrAD_2017.tif.
Wells notes: levels flagged as pumping/recently pumped are NOT filtered (NWIS status codes vary); trends need >= 3 spring values in the 5-year window.
The NWIS URLs are the documented waterservices endpoints but were not tested against the live service from the author's environment (--levels-url / --sites-url).

Example: python ext_irrigation.py raster  --attrs ./csb_work/attrs --state 20 --raster 2012=D:/mirad2012.tif 2017=D:/mirad2017.tif --out ./ext
         python ext_irrigation.py wells   --attrs ./csb_work/attrs --state 20 --years 2018 2019 2020 2021 2022 2023 2024 2025 --out ./ext
         python ext_irrigation.py pumping --attrs ./csb_work/attrs --state 20 --csv D:/wimas_ks.csv --lat-col LATITUDE --lon-col LONGITUDE --year-col YEAR --af-col AF_USED --out ./ext
Deps: pip install duckdb pandas pyarrow numpy scipy requests ; raster also rasterio pyproj
"""
import argparse, io, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

LEVELS = "https://waterservices.usgs.gov/nwis/gwlevels/?format=rdb&stateCd={st}&startDT={start}&endDT={end}&parameterCd=72019&siteStatus=all"
SITES = "https://waterservices.usgs.gov/nwis/site/?format=rdb&stateCd={st}&siteType=GW&hasDataTypeCd=gw"
FT = 0.3048
FIPS_ALPHA = {"01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA",
              "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD", "25": "MA",
              "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY",
              "37": "NC", "38": "ND", "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX",
              "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY"}


def state_sql(state, col="STATEFIPS"):
    """--state: 'all', one FIPS ('20') or a comma list ('19,20')"""
    st = str(state).strip().lower()
    if st in ("all", "*", ""):
        return "TRUE"
    return f"{col} IN (" + ",".join(f"'{x.strip().zfill(2)}'" for x in st.split(",")) + ")"


def attrs_glob(a):
    return (Path(a.attrs) / "batch_*.parquet").as_posix()


def batches(a):
    """one attrs batch file at a time (CSBID, county_fips = 5-digit state+county, acres, lon, lat): never all ~16 M fields at once"""
    import duckdb
    files = sorted(Path(a.attrs).glob("batch_*.parquet"))
    if not files: sys.exit("no batch_*.parquet in --attrs")
    con = duckdb.connect()
    for i, f in enumerate(files):
        df = con.execute(f"SELECT CSBID, lpad(STATEFIPS, 2, '0') || lpad(right(CAST(CNTYFIPS AS VARCHAR), 3), 3, '0') AS county_fips, CSBACRES AS acres, centroid_lon AS lon, centroid_lat AS lat "
                         f"FROM read_parquet('{f.as_posix()}') WHERE {state_sql(a.state)} AND centroid_lon IS NOT NULL").df()
        if len(df): yield i, df


def grid_tables(a, deg):
    """field -> ~2 km grid cell, all in DuckDB (no big frames): writes gw_field_grid_map.parquet, returns (grid DataFrame grid_id/lon/lat, mean lat, state FIPS list)"""
    import duckdb
    con = duckdb.connect(); con.execute(f"PRAGMA memory_limit='{getattr(a, 'memory', '2GB')}'")
    con.execute(f"PRAGMA temp_directory='{(Path(a.out) / '_duckdb_spill').as_posix()}'")
    src = f"(SELECT CSBID, STATEFIPS, centroid_lon AS lon, centroid_lat AS lat FROM read_parquet('{attrs_glob(a)}') WHERE {state_sql(a.state)} AND centroid_lon IS NOT NULL)"
    gid = f"(CAST(CAST(round(lat / {deg}) AS BIGINT) AS VARCHAR) || '_' || CAST(CAST(round(lon / {deg}) AS BIGINT) AS VARCHAR))"
    fn = Path(a.out) / "gw_field_grid_map.parquet"
    con.execute(f"COPY (SELECT CSBID, {gid} AS grid_id FROM {src}) TO '{fn.as_posix()}.tmp' (FORMAT PARQUET, COMPRESSION ZSTD)")
    Path(str(fn) + ".tmp").replace(fn)
    g = con.execute(f"SELECT DISTINCT {gid} AS grid_id, CAST(round(lon / {deg}) AS BIGINT) * {deg} AS lon, CAST(round(lat / {deg}) AS BIGINT) * {deg} AS lat FROM {src}").df()
    if g.empty: sys.exit("no fields for this state in --attrs")
    lat0, n = con.execute(f"SELECT avg(lat), count(*) FROM {src}").fetchone()
    sts = [r[0] for r in con.execute(f"SELECT DISTINCT STATEFIPS FROM {src} ORDER BY 1").fetchall()]
    print(f"{n:,} fields -> {len(g):,} grid cells of {deg} deg; states: {','.join(sts)}", flush=True)
    return g, float(lat0), sts


def xy_km(lon, lat, lat0):
    return np.column_stack([np.asarray(lon, float) * np.cos(np.radians(lat0)) * 111.32, np.asarray(lat, float) * 110.57])


def write(df, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp"); df.to_parquet(tmp, compression="zstd", index=False); tmp.replace(path)


# ------------------------------------------------------------ raster
def sample_raster(path, lon, lat, k, values, nodata):
    import rasterio
    from pyproj import Transformer
    from rasterio.windows import Window
    with rasterio.open(path) as ds:
        tr = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
        x, y = tr.transform(lon, lat)
        rows, cols = rasterio.transform.rowcol(ds.transform, x, y)
        rows, cols = np.asarray(rows), np.asarray(cols)
        ok = (rows >= 0) & (rows < ds.height) & (cols >= 0) & (cols < ds.width)
        if not ok.any(): raise SystemExit(f"{path}: no field centroid falls inside the raster")
        r0, r1 = max(rows[ok].min() - k, 0), min(rows[ok].max() + k + 1, ds.height)
        c0, c1 = max(cols[ok].min() - k, 0), min(cols[ok].max() + k + 1, ds.width)
        arr = ds.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)); nod = nodata if nodata is not None else ds.nodata
    irr = np.isin(arr, values) if values else (arr > 0)
    valid = np.ones(arr.shape, bool) if nod is None else (arr != nod)
    irr &= valid
    ii = irr.astype("float32"); vv = valid.astype("float32")
    from scipy.ndimage import uniform_filter
    share = uniform_filter(ii, size=2 * k + 1, mode="constant") / np.maximum(uniform_filter(vv, size=2 * k + 1, mode="constant"), 1e-6)
    pt = np.full(len(lon), np.nan, "float32"); sh = np.full(len(lon), np.nan, "float32")
    rr, cc = rows[ok] - r0, cols[ok] - c0
    pt[ok] = np.where(valid[rr, cc], irr[rr, cc], np.nan); sh[ok] = np.where(valid[rr, cc], share[rr, cc], np.nan)
    return pt, sh


def cmd_raster(a):
    import duckdb
    parts = Path(a.out) / "irrigation_parts"; parts.mkdir(parents=True, exist_ok=True); labels = []
    rasters = []
    for item in a.raster:
        label, _, path = item.partition("=") if "=" in item else (Path(item).stem, "", item)
        rasters.append((label, path)); labels.append(label)
    for i, df in batches(a):                                            # resumable: one part per attrs batch
        pf = parts / f"ir_{i:06d}.parquet"
        if pf.exists(): continue
        out = {"CSBID": df["CSBID"].to_numpy(), "county_fips": df["county_fips"].to_numpy(), "acres": df["acres"].to_numpy()}
        for label, path in rasters:
            try:
                pt, sh = sample_raster(path, df["lon"].to_numpy(), df["lat"].to_numpy(), a.window, a.values, a.nodata)
            except SystemExit:
                pt = sh = np.full(len(df), np.nan, "float32")           # batch lies outside this raster
            out[f"irr_{label}"] = pt; out[f"irr_share_{label}"] = sh
        write(pd.DataFrame(out), pf)
        print(f"  batch {i}: {len(df):,} fields; " + ", ".join(f"{l} irrigated {np.nanmean(out[f'irr_{l}']) * 100:.1f}%" if not np.all(np.isnan(out[f'irr_{l}'])) else f"{l} n/a" for l in labels), flush=True)
    if not any(parts.glob("*.parquet")): sys.exit("no batch produced rows")
    con = duckdb.connect(); src = f"read_parquet('{(parts / '*.parquet').as_posix()}')"
    cols = ", ".join(f"irr_{l}, irr_share_{l}" for l in labels)
    ff, cf = Path(a.out) / "irrigation_field.parquet", Path(a.out) / "irrigation_county.parquet"
    con.execute(f"COPY (SELECT CSBID, {cols} FROM {src}) TO '{ff.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    agg = ", ".join(f"sum(acres * irr_{l}) / NULLIF(sum(CASE WHEN irr_{l} IS NOT NULL THEN acres END), 0) AS irr_acre_share_{l}" for l in labels)
    con.execute(f"COPY (SELECT county_fips, {agg} FROM {src} GROUP BY 1 ORDER BY 1) TO '{cf.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    n = con.execute(f"SELECT count(*) FROM {src}").fetchone()[0]
    print(f"wrote irrigation_field.parquet ({n:,}) and irrigation_county.parquet")


# ------------------------------------------------------------ wells
def read_rdb(text):
    lines = [l for l in text.splitlines() if l and not l.startswith("#")]
    if len(lines) < 3: return pd.DataFrame()
    return pd.read_csv(io.StringIO("\n".join([lines[0]] + lines[2:])), sep="\t", dtype=str)


def nwis(url, cache, refresh):
    import requests
    cache = Path(cache)
    if cache.exists() and not refresh: return cache.read_text()
    for k in range(4):
        try:
            r = requests.get(url, timeout=300)
            if r.status_code == 200:
                cache.parent.mkdir(parents=True, exist_ok=True); cache.write_text(r.text); return r.text
            print(f"  HTTP {r.status_code} for {url}", file=sys.stderr)
            if r.status_code in (400, 404): break
        except Exception as e:
            print(f"  {type(e).__name__}: {str(e)[:100]}", file=sys.stderr)
        time.sleep(3 * (k + 1))
    sys.exit(f"could not fetch {url}")


def slope(yrs, vals):
    return float(np.polyfit(yrs, vals, 1)[0]) if len(yrs) >= 3 else np.nan


def load_wells(a, states):
    """NWIS spring depths for every state in `states` (FIPS list) -> DataFrame site_no, year, depth_m, dec_lat_va, dec_long_va"""
    y0, y1 = min(a.years) - 6, max(a.years); parts = []
    for fips in states:
        st = (a.state_alpha if (a.state_alpha and len(states) == 1) else FIPS_ALPHA.get(fips, "")).upper()
        if not st:
            print(f"  state {fips}: no letters known, skipped (pass --state-alpha for a single state)", file=sys.stderr); continue
        lv = read_rdb(nwis(a.levels_url.format(st=st, start=f"{y0}-01-01", end=f"{y1}-12-31"), Path(a.cache) / f"nwis_levels_{st}_{y0}_{y1}.rdb", a.refresh))
        si = read_rdb(nwis(a.sites_url.format(st=st), Path(a.cache) / f"nwis_sites_{st}.rdb", a.refresh))
        if lv.empty or si.empty:
            print(f"  {st}: NWIS returned no levels or no sites", file=sys.stderr); continue
        lv = lv[["site_no", "lev_dt", "lev_va"]].copy(); lv["lev_dt"] = pd.to_datetime(lv["lev_dt"], errors="coerce")
        lv["depth_m"] = pd.to_numeric(lv["lev_va"], errors="coerce") * FT; lv = lv.dropna(subset=["lev_dt", "depth_m"])
        lv = lv[lv["lev_dt"].dt.month.isin(a.spring_months)]
        w = lv.assign(year=lv["lev_dt"].dt.year).groupby(["site_no", "year"])["depth_m"].median().reset_index()
        si = si[["site_no", "dec_lat_va", "dec_long_va"]].apply(lambda s_: pd.to_numeric(s_, errors="coerce") if s_.name != "site_no" else s_).dropna()
        parts.append(w.merge(si, on="site_no")); print(f"  {st}: {parts[-1]['site_no'].nunique():,} wells", flush=True)
    if not parts: sys.exit("NWIS returned no wells for any state")
    return pd.concat(parts, ignore_index=True)


def cmd_wells(a):
    g, lat0, states = grid_tables(a, a.grid_deg)
    w = load_wells(a, states); print(f"{w['site_no'].nunique():,} wells with spring levels, {len(w):,} well-years", flush=True)
    from scipy.spatial import cKDTree
    wells = w.drop_duplicates("site_no").reset_index(drop=True)
    tree = cKDTree(xy_km(wells["dec_long_va"], wells["dec_lat_va"], lat0)); gxy = xy_km(g["lon"], g["lat"], lat0)
    ds, ix = tree.query(gxy, k=min(a.k, len(wells)), distance_upper_bound=a.radius_km)
    ds, ix = np.atleast_2d(ds.T).T if ds.ndim == 1 else ds, np.atleast_2d(ix.T).T if ix.ndim == 1 else ix
    wy = {s_: d.set_index("year")["depth_m"] for s_, d in w.groupby("site_no")}
    rows = []
    for t in a.years:
        yrs = list(range(t - a.trend_years + 1, t + 1))
        well_depth, well_trend = {}, {}
        for s_, ser in wy.items():
            s5 = ser[ser.index.isin(yrs)]
            if len(s5): well_depth[s_] = float(s5.iloc[-1]) if t in s5.index else np.nan
            well_trend[s_] = slope(s5.index.to_numpy(), s5.to_numpy())
        names = wells["site_no"].to_numpy()
        for gi in range(len(g)):
            sel = [(d_, names[i_]) for d_, i_ in zip(ds[gi], ix[gi]) if np.isfinite(d_)]
            if not sel: continue
            dep = [well_depth.get(s_, np.nan) for _, s_ in sel]; tr = [well_trend.get(s_, np.nan) for _, s_ in sel]
            rows.append({"grid_id": g.at[gi, "grid_id"], "year": t, "gw_depth_spring_m": np.nanmedian(dep) if not np.all(np.isnan(dep)) else np.nan,
                         "gw_trend_5y_m_per_yr": np.nanmedian(tr) if not np.all(np.isnan(tr)) else np.nan, "gw_n_wells": len(sel), "gw_nearest_km": float(min(d_ for d_, _ in sel))})
    out = pd.DataFrame(rows); write(out, Path(a.out) / "gw_grid_year.parquet")
    print(f"wrote gw_grid_year.parquet ({len(out):,} rows, {out['grid_id'].nunique():,} of {len(g):,} grid cells have wells within {a.radius_km} km)")


# ------------------------------------------------------------ pumping
def cmd_pumping(a):
    from scipy.spatial import cKDTree
    p = pd.read_csv(a.csv, dtype=str, low_memory=False, encoding="utf-8-sig")
    for c in (a.lat_col, a.lon_col, a.year_col, a.af_col):
        if c not in p.columns: sys.exit(f"column {c!r} not in the CSV; columns: {list(p.columns)}")
    q = pd.DataFrame({"lat": pd.to_numeric(p[a.lat_col], errors="coerce"), "lon": pd.to_numeric(p[a.lon_col], errors="coerce"),
                      "year": pd.to_numeric(p[a.year_col], errors="coerce"), "af": pd.to_numeric(p[a.af_col].str.replace(",", ""), errors="coerce")}).dropna()
    q["year"] = q["year"].astype(int); print(f"{len(q):,} pumping records", flush=True)
    g, lat0, _ = grid_tables(a, a.grid_deg)
    tree = cKDTree(xy_km(q["lon"], q["lat"], lat0))
    near = tree.query_ball_point(xy_km(g["lon"], g["lat"], lat0), r=a.radius_km)
    area_mm = np.pi * (a.radius_km * 1000) ** 2                                  # m2 of the search disc
    rows = []
    for gi, idx in enumerate(near):
        if not idx: continue
        s = q.iloc[idx].groupby("year")["af"].sum()
        for y, af in s.items():
            rows.append({"grid_id": g.at[gi, "grid_id"], "year": int(y), "pump_af_within_radius": float(af), "pump_mm_equiv": float(af * 1233.48 / area_mm * 1000)})
    out = pd.DataFrame(rows); write(out, Path(a.out) / "pumping_grid_year.parquet")
    print(f"wrote pumping_grid_year.parquet ({len(out):,} rows)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    def common(s, fn):
        s.set_defaults(fn=fn); s.add_argument("--attrs", required=True); s.add_argument("--state", default="all", help="all | FIPS | FIPS,FIPS"); s.add_argument("--memory", default="2GB"); s.add_argument("--out", required=True)
    r = sp.add_parser("raster"); common(r, cmd_raster)
    r.add_argument("--raster", nargs="+", required=True, help="[label=]path.tif ..."); r.add_argument("--values", type=float, nargs="+", help="pixel values meaning irrigated (default >0)")
    r.add_argument("--nodata", type=float); r.add_argument("--window", type=int, default=1, help="k: share over a (2k+1)x(2k+1) pixel window")
    w = sp.add_parser("wells"); common(w, cmd_wells)
    w.add_argument("--state-alpha", help="e.g. KS (default: derived from --state FIPS)"); w.add_argument("--years", type=int, nargs="+", required=True); w.add_argument("--cache", default="./ext_cache")
    w.add_argument("--spring-months", type=int, nargs="+", default=[1, 2, 3, 4]); w.add_argument("--trend-years", type=int, default=5)
    w.add_argument("--radius-km", type=float, default=25); w.add_argument("--k", type=int, default=5); w.add_argument("--grid-deg", type=float, default=0.02)
    w.add_argument("--levels-url", default=LEVELS); w.add_argument("--sites-url", default=SITES); w.add_argument("--refresh", action="store_true")
    u = sp.add_parser("pumping"); common(u, cmd_pumping)
    u.add_argument("--csv", required=True); u.add_argument("--lat-col", required=True); u.add_argument("--lon-col", required=True)
    u.add_argument("--year-col", required=True); u.add_argument("--af-col", required=True); u.add_argument("--radius-km", type=float, default=10); u.add_argument("--grid-deg", type=float, default=0.02)
    a = p.parse_args(); Path(a.out).mkdir(parents=True, exist_ok=True); a.fn(a)


if __name__ == "__main__":
    main()
