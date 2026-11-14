#!/usr/bin/env python3
"""gSSURGO / gNATSGO soil properties per field (USDA NRCS, 30 m map units) - replaces SoilGrids (250 m, modelled) in the US for
m7 (available water), M2 confounders (soil AWC, drainage) and m13 (infiltration potential).

Two steps, one command:
  1. field centroid -> map unit key (mukey)
       --mukey-raster gNATSGO_mukey.tif   : sample a local gNATSGO / gSSURGO mukey GeoTIFF (any CRS) - fast, recommended for a whole state
       (no raster)                        : Soil Data Access (SDA) web service, SDA_Get_Mukey_from_intersection_with_WktWgs84, points are
                                            snapped to a --snap-deg grid and sent in batches of --batch (UNION ALL; falls back to 1 per call).
  2. unique mukeys -> attributes from SDA tables muaggatt (map-unit aggregates) and component/chorizon (surface horizon, comppct-weighted)

Input : --attrs <work>/attrs (batch_*.parquet: CSBID, STATEFIPS, CNTYFIPS, CSBACRES, centroid_lon, centroid_lat); --state all | 19 | 19,20
        Raster mode processes one attrs batch at a time (resumable, parts in <out>/ssurgo_mukey_parts) - suitable for all states with the CONUS gNATSGO raster.
        SDA mode is for trials / small areas only (point-by-point web queries, limit --sda-max-fields).
Output: <out>/ssurgo_field.parquet        CSBID, mukey, ssurgo_* (see below)
        <out>/ssurgo_county.parquet       acre-weighted county means of the numeric columns (+ ssurgo_n_fields)
        <out>/ssurgo_mukey_attrs.parquet  one row per mukey (cache; reused on re-run)
Columns: ssurgo_aws_0_100_mm, ssurgo_aws_0_150_mm (available water storage, mm = cm x 10), ssurgo_slope_pct, ssurgo_drainage_class,
         ssurgo_hyd_group (A..D, A/D...), ssurgo_nirr_capability_class (non-irrigated land capability 1-8), ssurgo_wt_depth_min_cm,
         ssurgo_bedrock_depth_min_cm, ssurgo_flood_freq, ssurgo_pond_freq, and surface-horizon values ssurgo_om_pct, ssurgo_clay_pct,
         ssurgo_sand_pct, ssurgo_ksat_mm_h (um/s x 3.6), ssurgo_ph.
Caveats: map-unit values are component-percent weighted aggregates (not point measurements); mukey 0/NULL (water, urban, no survey) -> NULL.
         SDA table/column names are the documented ones but were not tested against the live service from the author's environment;
         a failing query prints the SDA message.

Example: python ext_soil_ssurgo.py --attrs ./csb_work/attrs --state 19 --out ./ext --mukey-raster D:/data/gNATSGO_IA_mukey.tif
         python ext_soil_ssurgo.py --attrs ./csb_work/attrs --state 19 --out ./ext --max-fields 20000   # SDA only, quick trial
Deps: pip install duckdb pandas pyarrow numpy requests ; raster mode also rasterio pyproj
"""
import argparse, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd

SDA = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"

MU_COLS = {"aws0100wta": "ssurgo_aws_0_100_mm", "aws0150wta": "ssurgo_aws_0_150_mm", "slopegraddcp": "ssurgo_slope_pct",
           "drclassdcd": "ssurgo_drainage_class", "hydgrpdcd": "ssurgo_hyd_group", "niccdcd": "ssurgo_nirr_capability_class",
           "wtdepannmin": "ssurgo_wt_depth_min_cm", "brockdepmin": "ssurgo_bedrock_depth_min_cm", "flodfreqdcd": "ssurgo_flood_freq",
           "pondfreqprs": "ssurgo_pond_freq"}
CM = 10.0                                                      # SSURGO aws is in cm of water -> mm
HZ = {"om_r": "ssurgo_om_pct", "claytotal_r": "ssurgo_clay_pct", "sandtotal_r": "ssurgo_sand_pct", "ksat_r": "ssurgo_ksat_mm_h", "ph1to1h2o_r": "ssurgo_ph"}
TEXT_COLS = {"ssurgo_drainage_class", "ssurgo_hyd_group", "ssurgo_flood_freq", "ssurgo_pond_freq"}


_STYLE = {"i": None}          # request style that worked (remembered across calls)
STYLES = [("json", lambda q: {"json": {"query": q, "format": "JSON+COLUMNNAME"}}),
          ("form", lambda q: {"data": {"query": q, "format": "JSON+COLUMNNAME"}}),
          ("json-upper", lambda q: {"json": {"QUERY": q, "FORMAT": "JSON+COLUMNNAME"}}),
          ("form-upper", lambda q: {"data": {"QUERY": q, "FORMAT": "JSON+COLUMNNAME"}})]


def _short(txt, n=700):
    import re
    t = re.sub(r"<[^>]+>", " ", txt); t = re.sub(r"\s+", " ", t).strip()
    return t[:n]


def sda(query, url=SDA, retries=4):
    """POST one query to Soil Data Access. Tries JSON then form-encoded bodies (the service has accepted both); the style that works is remembered."""
    import requests
    order = [_STYLE["i"]] + [i for i in range(len(STYLES)) if i != _STYLE["i"]] if _STYLE["i"] is not None else list(range(len(STYLES)))
    last = ""
    for i in order:
        name, mk = STYLES[i]
        for t in range(retries):
            try:
                r = requests.post(url, headers={"User-Agent": "ext_soil_ssurgo/1.0"}, timeout=180, **mk(query))
            except Exception as e:
                if t == retries - 1: raise RuntimeError(f"SDA unreachable: {type(e).__name__}: {str(e)[:150]}")
                time.sleep(2 * (t + 1)); continue
            if r.status_code == 200 and ("{" in r.text[:5] or r.text.lstrip().startswith("{")):
                _STYLE["i"] = i
                tab = r.json().get("Table")
                return pd.DataFrame(tab[1:], columns=tab[0]) if tab else pd.DataFrame()
            last = f"[{name}] HTTP {r.status_code}: {_short(r.text)}"
            if r.status_code in (400, 404, 415, 200): break           # a different body style may be accepted; 5xx / rate limits are retried
            time.sleep(2 * (t + 1))
    raise RuntimeError(f"SDA rejected the query ({last}). Query was: {query[:200]}")


def sda_test(url):
    """--sda-test: print what the service answers to a trivial query in each request style"""
    import requests
    q = "SELECT TOP 1 mukey FROM mapunit"
    print("URL:", url, "\nQuery:", q)
    for name, mk in STYLES:
        try:
            r = requests.post(url, headers={"User-Agent": "ext_soil_ssurgo/1.0"}, timeout=60, **mk(q))
            print(f"  {name:11s} -> HTTP {r.status_code} {r.headers.get('Content-Type', '')} | {_short(r.text, 300)}")
        except Exception as e:
            print(f"  {name:11s} -> {type(e).__name__}: {str(e)[:150]}")
    try:
        q2 = "SELECT mukey FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT(-93.62 42.03)')"
        r = requests.post(url, json={"query": q2, "format": "JSON+COLUMNNAME"}, timeout=60)
        print(f"  spatial function -> HTTP {r.status_code} | {_short(r.text, 300)}")
    except Exception as e:
        print("  spatial function ->", type(e).__name__, str(e)[:150])


def state_sql(state, col="STATEFIPS"):
    """--state: 'all', one FIPS ('19') or a comma list ('19,20')"""
    st = str(state).strip().lower()
    if st in ("all", "*", ""):
        return "TRUE"
    return f"{col} IN (" + ",".join(f"'{x.strip().zfill(2)}'" for x in st.split(",")) + ")"


def batches(a):
    """one attrs batch file at a time (CSBID, county_fips = 5-digit state+county, acres, lon, lat): never all ~16 M fields at once"""
    import duckdb
    files = sorted(Path(a.attrs).glob("batch_*.parquet"))
    if not files: sys.exit("no batch_*.parquet in --attrs")
    con = duckdb.connect()
    for i, f in enumerate(files):
        df = con.execute(f"SELECT CSBID, lpad(STATEFIPS, 2, '0') || lpad(right(CAST(CNTYFIPS AS VARCHAR), 3), 3, '0') AS county_fips, CSBACRES AS acres, centroid_lon AS lon, centroid_lat AS lat "
                         f"FROM read_parquet('{f.as_posix()}') WHERE {state_sql(a.state)} AND isfinite(centroid_lon) AND isfinite(centroid_lat) AND centroid_lon BETWEEN -180 AND 180 AND centroid_lat BETWEEN -90 AND 90").df()
        if len(df): yield i, df


# ---- step 1a: raster
def mukeys_raster(a, df):
    import rasterio
    from pyproj import Transformer
    with rasterio.open(a.mukey_raster) as ds:
        tr = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
        x, y = tr.transform(df["lon"].to_numpy(), df["lat"].to_numpy())
        out = np.full(len(df), 0, dtype="int64"); nod = ds.nodata
        for i in range(0, len(df), 200_000):
            pts = list(zip(x[i:i + 200_000], y[i:i + 200_000]))
            out[i:i + len(pts)] = np.fromiter((v[0] for v in ds.sample(pts, indexes=1, masked=False)), dtype="int64", count=len(pts))
        if nod is not None: out[out == nod] = 0
    return out


# ---- step 1b: SDA points
def sda_mukeys(points, batch, url):
    """points: list of (lon, lat) -> list of mukey (0 = none). UNION ALL batches, falls back to single calls on error."""
    def one(lon, lat):
        try:
            d = sda(f"SELECT mukey FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({lon:.6f} {lat:.6f})')", url)
        except RuntimeError as e:
            if "unreachable" in str(e): raise
            if not _STYLE.get("warned"):
                _STYLE["warned"] = True; print(f"  point ({lon:.5f}, {lat:.5f}) rejected, treated as no map unit: {str(e)[:300]}", file=sys.stderr)
            return 0
        return int(d.iloc[0, 0]) if len(d) else 0
    out = []
    for i in range(0, len(points), batch):
        chunk = points[i:i + batch]
        q = " UNION ALL ".join(f"SELECT {k} AS i, mukey FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({lo:.6f} {la:.6f})')"
                               for k, (lo, la) in enumerate(chunk))
        try:
            d = sda(q, url); m = {int(r.i): int(r.mukey) for r in d.itertuples()} if len(d) else {}
            out += [m.get(k, 0) for k in range(len(chunk))]
        except RuntimeError as e:
            if "unreachable" in str(e): raise
            out += [one(lo, la) for lo, la in chunk]
    return out


def mukeys_sda(a, df):
    snap = a.snap_deg
    key = pd.DataFrame({"gx": np.round(df["lon"] / snap).astype("int64"), "gy": np.round(df["lat"] / snap).astype("int64")})
    uniq = key.drop_duplicates().reset_index(drop=True)
    cache = Path(a.out) / "ssurgo_sda_points.parquet"
    done = pd.read_parquet(cache) if cache.exists() else pd.DataFrame(columns=["gx", "gy", "mukey"])
    todo = uniq.merge(done, on=["gx", "gy"], how="left"); todo = todo[todo["mukey"].isna()][["gx", "gy"]]
    print(f"SDA points: {len(uniq):,} unique cells of {snap} deg, {len(todo):,} to query", flush=True)
    chunks = [todo.iloc[i:i + a.batch * 20] for i in range(0, len(todo), a.batch * 20)]
    def work(c):
        pts = list(zip(c["gx"] * snap, c["gy"] * snap))
        return c.assign(mukey=sda_mukeys(pts, a.batch, a.sda_url))
    new = [done]
    with ThreadPoolExecutor(a.workers) as ex:
        for k, r in enumerate(ex.map(work, chunks), 1):
            new.append(r)
            if k % 5 == 0 or k == len(chunks):
                pd.concat(new, ignore_index=True).to_parquet(cache, index=False); print(f"  {k}/{len(chunks)} chunks", flush=True)
    allp = pd.concat(new, ignore_index=True).drop_duplicates(["gx", "gy"])
    allp.to_parquet(cache, index=False)
    return key.merge(allp, on=["gx", "gy"], how="left")["mukey"].fillna(0).astype("int64").to_numpy()


# ---- step 2: attributes
def mukey_attrs(keys, a):
    cache = Path(a.out) / "ssurgo_mukey_attrs.parquet"
    have = pd.read_parquet(cache) if cache.exists() else pd.DataFrame({"mukey": pd.Series(dtype="int64")})
    need = sorted(set(int(k) for k in keys if k) - set(have["mukey"].astype("int64")))
    print(f"mukeys: {len(set(keys)) - (0 in set(keys))} unique, {len(need)} to fetch", flush=True)
    parts = [have]
    for i in range(0, len(need), 400):
        ids = ",".join(str(k) for k in need[i:i + 400])
        mu = sda(f"SELECT mukey, {', '.join(MU_COLS)} FROM muaggatt WHERE mukey IN ({ids})", a.sda_url)
        if mu.empty:
            mu = pd.DataFrame({"mukey": need[i:i + 400]})
        mu["mukey"] = mu["mukey"].astype("int64")
        hz = sda(f"""SELECT c.mukey, {', '.join(f"SUM(c.comppct_r * h.{k}) / SUM(CASE WHEN h.{k} IS NULL THEN 0 ELSE c.comppct_r END) AS {k}" for k in HZ)}
                     FROM component c JOIN chorizon h ON h.cokey = c.cokey
                     WHERE c.mukey IN ({ids}) AND h.hzdept_r = 0 AND c.comppct_r IS NOT NULL GROUP BY c.mukey""", a.sda_url)
        if len(hz):
            hz["mukey"] = hz["mukey"].astype("int64"); mu = mu.merge(hz, on="mukey", how="left")
        parts.append(mu); print(f"  attributes {min(i + 400, len(need)):,}/{len(need):,}", flush=True)
    t = pd.concat(parts, ignore_index=True).drop_duplicates("mukey", keep="last")
    t = t.rename(columns={**MU_COLS, **HZ})
    for c in t.columns:
        if c == "mukey": continue
        if c in TEXT_COLS: t[c] = t[c].astype("string")
        else: t[c] = pd.to_numeric(t[c], errors="coerce")
    t.to_parquet(cache, index=False)
    return t


def to_mm(t):
    """aws*wta in cm -> mm; done once on the merged table, never on the cached one (cache keeps source units)"""
    t = t.copy()
    for c in ("ssurgo_aws_0_100_mm", "ssurgo_aws_0_150_mm"):
        if c in t: t[c] = t[c] * CM
    if "ssurgo_ksat_mm_h" in t: t["ssurgo_ksat_mm_h"] = t["ssurgo_ksat_mm_h"] * 3.6
    return t


def main():
    import duckdb, shutil
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--attrs"); p.add_argument("--state", default="all", help="all | FIPS | FIPS,FIPS"); p.add_argument("--out")
    p.add_argument("--mukey-raster"); p.add_argument("--max-fields", type=int, help="random subset (trial runs; SDA mode)")
    p.add_argument("--sda-max-fields", type=int, default=16_000_000, help="SDA mode refuses more fields than this: use --mukey-raster for large areas")
    p.add_argument("--snap-deg", type=float, default=0.002, help="SDA mode: points are snapped to this grid (~200 m) before querying")
    p.add_argument("--batch", type=int, default=40, help="SDA mode: points per request"); p.add_argument("--workers", type=int, default=4)
    p.add_argument("--sda-url", default=SDA); p.add_argument("--memory", default="2GB")
    p.add_argument("--sda-test", action="store_true", help="only probe the SDA endpoint (prints each request style's answer) and exit")
    a = p.parse_args()
    if a.sda_test:
        sda_test(a.sda_url); return
    if not (a.attrs and a.out): sys.exit("--attrs and --out are required")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    parts = out / "ssurgo_mukey_parts"; parts.mkdir(exist_ok=True)
    if a.mukey_raster:
        for i, df in batches(a):                                          # resumable: one part per attrs batch
            pf = parts / f"mk_{i:06d}.parquet"
            if pf.exists(): continue
            df["mukey"] = mukeys_raster(a, df)
            tmp = Path(str(pf) + ".tmp"); df[["CSBID", "county_fips", "acres", "mukey"]].to_parquet(tmp, compression="zstd", index=False); tmp.replace(pf)
            print(f"  batch {i}: {len(df):,} fields, {int((df['mukey'] > 0).sum()):,} with a map unit", flush=True)
    else:
        frames = [df for _, df in batches(a)]
        df = pd.concat(frames, ignore_index=True); del frames
        if a.max_fields and len(df) > a.max_fields:
            df = df.sample(a.max_fields, random_state=1).reset_index(drop=True)
        if len(df) > a.sda_max_fields:
            sys.exit(f"{len(df):,} fields is too many for point-by-point SDA queries (limit --sda-max-fields {a.sda_max_fields:,}). "
                     "Download the gNATSGO mukey raster and pass --mukey-raster, or restrict --state / --max-fields.")
        print(f"{len(df):,} fields (SDA mode)", flush=True)
        df["mukey"] = mukeys_sda(a, df)
        shutil.rmtree(parts, ignore_errors=True); parts.mkdir()
        df[["CSBID", "county_fips", "acres", "mukey"]].to_parquet(parts / "mk_000000.parquet", compression="zstd", index=False)
    con = duckdb.connect(); con.execute(f"PRAGMA memory_limit='{a.memory}'"); con.execute(f"PRAGMA temp_directory='{(out / '_duckdb_spill').as_posix()}'")
    src = f"read_parquet('{(parts / '*.parquet').as_posix()}')"
    keys = [r[0] for r in con.execute(f"SELECT DISTINCT mukey FROM {src}").fetchall()]
    t = to_mm(mukey_attrs(keys, a))
    ta = out / "ssurgo_mukey_attrs_out.parquet"; t.to_parquet(ta, index=False)
    ff = out / "ssurgo_field.parquet"
    con.execute(f"COPY (SELECT p.CSBID, p.mukey, t.* EXCLUDE (mukey) FROM {src} p LEFT JOIN read_parquet('{ta.as_posix()}') t ON t.mukey = p.mukey AND p.mukey > 0) "
                f"TO '{ff.as_posix()}.tmp' (FORMAT PARQUET, COMPRESSION ZSTD)")
    Path(str(ff) + ".tmp").replace(ff)
    num = [c for c in t.columns if c != "mukey" and c not in TEXT_COLS]
    agg = ", ".join(f"sum(p.acres * t.{c}) / NULLIF(sum(CASE WHEN t.{c} IS NOT NULL THEN p.acres END), 0) AS {c}" for c in num)
    con.execute(f"COPY (SELECT p.county_fips, count(*) FILTER (WHERE p.mukey > 0) AS ssurgo_n_fields, {agg} FROM {src} p "
                f"LEFT JOIN read_parquet('{ta.as_posix()}') t ON t.mukey = p.mukey AND p.mukey > 0 GROUP BY 1 ORDER BY 1) "
                f"TO '{(out / 'ssurgo_county.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    n, w = con.execute(f"SELECT count(*), count(*) FILTER (WHERE mukey > 0) FROM {src}").fetchone()
    print(f"wrote {ff} ({n:,} fields, {w:,} with a map unit) and ssurgo_county.parquet")


if __name__ == "__main__":
    main()