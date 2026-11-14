#!/usr/bin/env python3
"""Per-field NDVI / EVI / NDWI time series for crop classification (LightGBM/XGBoost tables and TempCNN tensors).

Imagery: NASA HLS v2.0 (HLSS30 Sentinel-2 + HLSL30 Landsat, 30 m, harmonized surface reflectance, Cloud-Optimized GeoTIFF, LP DAAC).
Labels : USDA CDL class of the field for the chosen year, taken from the CSB ingest (CDL<year> column of csb_pipeline.py ingest).

  sample   stratified sample of fields: --n-per-class fields for each crop class (default 2000)    -> <out>/fields.parquet, classes.json
  extract  for every HLS granule that overlaps the fields, read the pixels inside each field, mask clouds with Fmask, write the
           field mean of NDVI, EVI, NDWI per date                                                   -> <out>/obs/<granule>.parquet
  compose  T equal time steps (default 16) over the season, per-step median, linear interpolation of gaps (no NaN left),
           tabular + tensor output                                                                  -> <out>/dataset/

Example (Iowa, 2023, five classes, a few counties to keep the download small)
  python crop_ts.py sample  --attrs ./csb_work/attrs --year 2023 --state 19 --counties 19015 19169 19153 --classes 1 5 36 176 --n-per-class 2000 --out ./ts_2023
  python crop_ts.py extract --out ./ts_2023 --year 2023 --workers 4                      # needs EARTHDATA_TOKEN (see below)
  python crop_ts.py compose --out ./ts_2023 --year 2023 --steps 16 --pt

Definitions (all configurable)
  NDVI = (NIR - Red) / (NIR + Red)
  EVI  = 2.5 (NIR - Red) / (NIR + 6 Red - 7.5 Blue + 1), clipped to [-1, 1]
  NDWI = (NIR - SWIR1) / (NIR + SWIR1)  (Gao, vegetation water content; default)   |  --ndwi mcfeeters: (Green - NIR) / (Green + NIR) (open water)
  Bands: S30 Blue B02, Green B03, Red B04, NIR B8A, SWIR1 B11 ; L30 Blue B02, Green B03, Red B04, NIR B05, SWIR1 B06 ; quality band Fmask.
  Scale factor 0.0001, nodata -9999. A pixel is used when Fmask bits 1-4 (cloud, adjacent to cloud/shadow, cloud shadow, snow/ice) are 0.
  A field-date is kept when it has at least max(3, --min-valid-frac x pixels) valid pixels.
Field footprint: the polygon shrunk by --inner-buffer-m if you pass --polygons (GeoJSON files of csb_geometry.py), otherwise a square of the
  field's CSBACRES area scaled by --shrink (default 0.7) around the centroid (an approximation, like csb_bounds).

Time axis: --start/--end (default 04-01..10-31) are cut into --steps equal intervals; each interval is the median of all valid observations
(Sentinel and Landsat together). Empty intervals are filled by linear interpolation in time, the ends by the nearest value. A field needs at least
--min-steps observed intervals in each channel, else it is dropped (reported). `n_observed_steps` keeps the number of really observed steps.

Output (compose), folder <out>/dataset/
  tabular.parquet  CSBID, crop_id, cdl_code, crop_name, year, county_fips, centroid_lon, centroid_lat, area_acres, split, n_observed_steps,
                   ndvi_d1..ndvi_d16, evi_d1..evi_d16, ndwi_d1..ndwi_d16   (float32, no NaN; "d" = time step, not day)
  X.npy            float32 (N, 3, T), channels [ndvi, evi, ndwi], values in [-1, 1]      (X.pt with --pt if torch is installed)
  y.npy            int64 (N,), crop_id           meta.parquet  same rows/order as X (all non-feature columns)
  classes.json     crop_id -> CDL code, name, counts
  split: train/val/test, by COUNTY (hash) when the sample has >= 5 counties, else by field; fractions --val-frac/--test-frac.

Access (extract)
  Default --auth session: earthaccess logs in with EARTHDATA_USERNAME / EARTHDATA_PASSWORD (or EARTHDATA_TOKEN) and the files are read through its
  authenticated session (works with the Earthdata redirect). The LP DAAC application must be authorised in your Earthdata profile.
  --auth token: GDAL /vsicurl with "Authorization: Bearer $EARTHDATA_TOKEN" (token: https://urs.earthdata.nasa.gov > Generate Token). Granules are found in NASA CMR (via earthaccess)
  and read window by window straight from the COGs (no full download). Alternatively download granules yourself and use --local DIR
  (any folder tree containing HLS.[SL]30.Txxxxx.YYYYDDDThhmmss.v2.0.<band>.tif files).
  Volume: one HLS tile-year has ~100-150 granules; a few counties => tens of MB per granule read, in 5-km blocks. Use few counties, --max-cloud and --workers.

Not tested against the live services (blocked in the build sandbox); the pixel logic and the composition were tested on synthetic GeoTIFFs.
Deps: pip install numpy pandas pyarrow duckdb rasterio pyproj shapely earthaccess [geopandas for --polygons] [torch for --pt]
"""
import argparse, datetime as dt, glob, json, os, re, sys, warnings
warnings.filterwarnings("ignore", message="Dataset has no geotransform")
from pathlib import Path
import numpy as np
import pandas as pd

CDL = {
    0: 'Background',
    1: 'Corn',
    2: 'Cotton',
    3: 'Rice',
    4: 'Sorghum',
    5: 'Soybeans',
    6: 'Sunflower',
    10: 'Peanuts',
    11: 'Tobacco',
    12: 'Sweet Corn',
    13: 'Pop or Orn Corn',
    14: 'Mint',
    21: 'Barley',
    22: 'Durum Wheat',
    23: 'Spring Wheat',
    24: 'Winter Wheat',
    25: 'Other Small Grains',
    26: 'Dbl Crop WinWht/Soybeans',
    27: 'Rye',
    28: 'Oats',
    29: 'Millet',
    30: 'Speltz',
    31: 'Canola',
    32: 'Flaxseed',
    33: 'Safflower',
    34: 'Rape Seed',
    35: 'Mustard',
    36: 'Alfalfa',
    37: 'Other Hay/Non Alfalfa',
    38: 'Camelina',
    39: 'Buckwheat',
    41: 'Sugarbeets',
    42: 'Dry Beans',
    43: 'Potatoes',
    44: 'Other Crops',
    45: 'Sugarcane',
    46: 'Sweet Potatoes',
    47: 'Misc Vegs & Fruits',
    48: 'Watermelons',
    49: 'Onions',
    50: 'Cucumbers',
    51: 'Chick Peas',
    52: 'Lentils',
    53: 'Peas',
    54: 'Tomatoes',
    55: 'Caneberries',
    56: 'Hops',
    57: 'Herbs',
    58: 'Clover/Wildflowers',
    59: 'Sod/Grass Seed',
    60: 'Switchgrass',
    61: 'Fallow/Idle Cropland',
    62: 'Pasture/Grass',
    63: 'Forest',
    64: 'Shrubland',
    65: 'Barren',
    66: 'Cherries',
    67: 'Peaches',
    68: 'Apples',
    69: 'Grapes',
    70: 'Christmas Trees',
    71: 'Other Tree Crops',
    72: 'Citrus',
    74: 'Pecans',
    75: 'Almonds',
    76: 'Walnuts',
    77: 'Pears',
    81: 'Clouds/No Data',
    82: 'Developed',
    83: 'Water',
    87: 'Wetlands',
    88: 'Nonag/Undefined',
    92: 'Aquaculture',
    111: 'Open Water',
    112: 'Perennial Ice/Snow',
    121: 'Developed/Open Space',
    122: 'Developed/Low Intensity',
    123: 'Developed/Med Intensity',
    124: 'Developed/High Intensity',
    131: 'Barren',
    141: 'Deciduous Forest',
    142: 'Evergreen Forest',
    143: 'Mixed Forest',
    152: 'Shrubland',
    176: 'Grassland/Pasture',
    190: 'Woody Wetlands',
    195: 'Herbaceous Wetlands',
    204: 'Pistachios',
    205: 'Triticale',
    206: 'Carrots',
    207: 'Asparagus',
    208: 'Garlic',
    209: 'Cantaloupes',
    210: 'Prunes',
    211: 'Olives',
    212: 'Oranges',
    213: 'Honeydew Melons',
    214: 'Broccoli',
    215: 'Avocados',
    216: 'Peppers',
    217: 'Pomegranates',
    218: 'Nectarines',
    219: 'Greens',
    220: 'Plums',
    221: 'Strawberries',
    222: 'Squash',
    223: 'Apricots',
    224: 'Vetch',
    225: 'Dbl Crop WinWht/Corn',
    226: 'Dbl Crop Oats/Corn',
    227: 'Lettuce',
    228: 'Dbl Crop Triticale/Corn',
    229: 'Pumpkins',
    230: 'Dbl Crop Lettuce/Durum Wht',
    231: 'Dbl Crop Lettuce/Cantaloupe',
    232: 'Dbl Crop Lettuce/Cotton',
    233: 'Dbl Crop Lettuce/Barley',
    234: 'Dbl Crop Durum Wht/Sorghum',
    235: 'Dbl Crop Barley/Sorghum',
    236: 'Dbl Crop WinWht/Sorghum',
    237: 'Dbl Crop Barley/Corn',
    238: 'Dbl Crop WinWht/Cotton',
    239: 'Dbl Crop Soybeans/Cotton',
    240: 'Dbl Crop Soybeans/Oats',
    241: 'Dbl Crop Corn/Soybeans',
    242: 'Blueberries',
    243: 'Cabbage',
    244: 'Cauliflower',
    245: 'Celery',
    246: 'Radishes',
    247: 'Turnips',
    248: 'Eggplants',
    249: 'Gourds',
    250: 'Cranberries',
    254: 'Dbl Crop Barley/Soybeans',
}


BANDS = {"S30": dict(blue="B02", green="B03", red="B04", nir="B8A", swir="B11"),
         "L30": dict(blue="B02", green="B03", red="B04", nir="B05", swir="B06")}
GRAN = re.compile(r"(HLS\.(S30|L30)\.(T\w{5})\.(\d{7})T\d{6}\.v2\.0)\.(B\d{2}|B8A|Fmask)\.tif$")
CH = ["ndvi", "evi", "ndwi"]


# ------------------------------------------------------------------ sample
def cmd_sample(a):
    import duckdb
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    col = f"CDL{a.year}"
    flt = [f"{col} IN ({','.join(str(int(c)) for c in a.classes)})", f"CSBACRES >= {a.min_acres}"]
    if a.state: flt.append(f"STATEFIPS = '{str(a.state).zfill(2)}'")
    if a.counties: flt.append("CNTYFIPS IN (" + ",".join(f"'{str(c).zfill(5)}'" for c in a.counties) + ")")
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{a.memory}'")
    con.execute(f"PRAGMA temp_directory='{(out / '_spill').as_posix()}'")
    src = (Path(a.attrs) / "batch_*.parquet").as_posix()
    df = con.execute(f"""SELECT CSBID, {col} AS cdl_code, CNTYFIPS AS county_fips, CSBACRES AS area_acres, centroid_lon, centroid_lat FROM (
            SELECT *, row_number() OVER (PARTITION BY {col} ORDER BY hash(CSBID || '{a.seed}')) AS rn
            FROM read_parquet('{src}') WHERE {' AND '.join(flt)}) WHERE rn <= {int(a.n_per_class)}""").df()
    if df.empty:
        sys.exit("no fields matched; check --year/--classes/--state/--counties/--min-acres")
    codes = sorted(df["cdl_code"].unique())
    cid = {c: i for i, c in enumerate(codes)}
    df["crop_id"] = df["cdl_code"].map(cid).astype("int64")
    df["crop_name"] = df["cdl_code"].map(lambda c: CDL.get(int(c), f"code_{c}"))
    df["year"] = a.year
    df.to_parquet(out / "fields.parquet", compression="zstd", index=False)
    cls = {int(cid[c]): {"cdl_code": int(c), "name": CDL.get(int(c), f"code_{c}"), "n_sampled": int((df.cdl_code == c).sum())} for c in codes}
    (out / "classes.json").write_text(json.dumps(cls, indent=2))
    for k, v in cls.items():
        flag = "" if v["n_sampled"] >= a.n_per_class else f"   <- fewer than requested ({a.n_per_class})"
        print(f"  crop_id {k}: CDL {v['cdl_code']} {v['name']}: {v['n_sampled']:,}{flag}")
    miss = [c for c in a.classes if c not in codes]
    if miss: print("  no fields at all for CDL codes:", miss)
    print(f"wrote {out / 'fields.parquet'} ({len(df):,} fields, {df.county_fips.nunique()} counties)")


# ------------------------------------------------------------------ extract
def granule_table(a, fields):
    """{granule_id: {'sensor':, 'date':, 'tile':, 'files': {band: path_or_url}}}"""
    g = {}

    def add(path):
        m = GRAN.search(str(path).replace("\\", "/"))
        if not m: return
        gid, sensor, tile, ymd, band = m.groups()
        d = g.setdefault(gid, dict(sensor=sensor, tile=tile, date=dt.datetime.strptime(ymd, "%Y%j").date(), files={}))
        d["files"][band] = str(path)
    if a.local:
        for f in glob.glob(str(Path(a.local) / "**" / "HLS.*.tif"), recursive=True): add(f)
    else:
        import earthaccess
        earthaccess.login(strategy="environment")
        box = (float(fields.centroid_lon.min()) - .02, float(fields.centroid_lat.min()) - .02, float(fields.centroid_lon.max()) + .02, float(fields.centroid_lat.max()) + .02)
        for prod in a.products:
            res = earthaccess.search_data(short_name=prod, version="2.0", bounding_box=box, cloud_cover=(0, a.max_cloud),
                                          temporal=(f"{a.year}-{a.start}", f"{a.year}-{a.end}"))
            print(f"  {prod}: {len(res)} granules", flush=True)
            for r in res:
                for u in r.data_links(): add(u)
    lo, hi = dt.date.fromisoformat(f"{a.year}-{a.start}"), dt.date.fromisoformat(f"{a.year}-{a.end}")
    g = {k: v for k, v in g.items() if lo <= v["date"] <= hi}
    need = {"Fmask", "B02", "B04"}
    return {k: v for k, v in g.items() if need <= set(v["files"]) and set(BANDS[v["sensor"]].values()) <= set(v["files"])}


def open_raster(src, a):
    """Local path -> plain rasterio; remote URL -> file object from the authenticated earthaccess session (handles the Earthdata redirect/login),
    or GDAL /vsicurl with a bearer token (--auth token)."""
    import rasterio
    if a.local or not str(src).startswith("http"):
        return rasterio.open(src)
    if a.auth == "token":
        return rasterio.open(src)                     # options come from rasterio.Env in process_granule
    import earthaccess
    fo = earthaccess.open([src])[0]
    return rasterio.open(fo)


def preflight(gr, a):
    """Open the header of one remote Fmask before starting the workers, so an authentication problem is explained once, clearly."""
    if a.local: return
    gid, info = next(iter(gr.items()))
    import rasterio
    opts = token_opts(a)
    try:
        with rasterio.Env(**opts):
            with open_raster(info["files"]["Fmask"], a) as d:
                d.read(1, window=((0, 8), (0, 8)))
        print(f"  access check OK ({a.auth}) on {gid}")
    except Exception as e:
        sys.exit(f"Cannot read HLS data ({type(e).__name__}: {e}).\n"
                 "Usually an Earthdata login problem: the server answered with a login page instead of a GeoTIFF.\n"
                 "  * --auth session (default): set EARTHDATA_USERNAME and EARTHDATA_PASSWORD (or a valid EARTHDATA_TOKEN) and accept the\n"
                 "    'LP DAAC Data Pool' / 'LP DAAC' application in https://urs.earthdata.nasa.gov > Applications > Authorized Apps.\n"
                 "  * --auth token: EARTHDATA_TOKEN must be a current token (they expire after 60 days).\n"
                 "  * or download granules with earthaccess yourself and use --local DIR.")


def token_opts(a):
    tok = os.environ.get("EARTHDATA_TOKEN")
    if a.auth == "token" and tok and not a.local:
        return dict(GDAL_HTTP_HEADERS=f"Authorization: Bearer {tok}", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2")
    return {}


def load_polygons(a, ids):
    import geopandas as gpd
    polys, want = {}, set(ids)
    for f in sorted(glob.glob(a.polygons, recursive=True)):
        g = gpd.read_file(f)
        g = g[g["CSBID"].isin(want)]
        if len(g): polys.update({r.CSBID: r.geometry for r in g.itertuples()}); crs = g.crs
        if len(polys) >= len(want): break
    if not polys: sys.exit("--polygons: none of the sampled CSBIDs found")
    print(f"  polygons for {len(polys):,}/{len(want):,} fields")
    return polys, crs


def process_granule(gid, info, fields, polys, a):
    import rasterio
    from rasterio.features import rasterize
    from rasterio.windows import Window, transform as wtransform
    from pyproj import Transformer
    from shapely.geometry import box
    import shapely
    dst = Path(a.out) / "obs" / f"{gid}.parquet"
    if dst.exists():
        return gid, -1
    opts = token_opts(a)
    bn = BANDS[info["sensor"]]
    rows = []
    with rasterio.Env(**opts):
        fm = open_raster(info["files"]["Fmask"], a)
        tf, crs, W, H = fm.transform, fm.crs, fm.width, fm.height
        tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        x, y = tr.transform(fields.centroid_lon.to_numpy(), fields.centroid_lat.to_numpy())
        x, y = np.asarray(x), np.asarray(y)
        side = np.sqrt(fields.area_acres.to_numpy() * 4046.856) * a.shrink
        half = np.clip(side / 2, 45.0, 1500.0)
        geoms = {}
        if polys is not None:
            import geopandas as gpd
            sub = gpd.GeoSeries({k: polys[0][k] for k in fields.CSBID if k in polys[0]}, crs=polys[1]).to_crs(crs)
            if a.inner_buffer_m: sub = sub.buffer(-a.inner_buffer_m)
            geoms = {k: g for k, g in sub.items() if g is not None and not g.is_empty}
        # pixel window of every field (clipped to the tile)
        c0 = np.floor((x - half - tf.c) / tf.a).astype(int); c1 = np.ceil((x + half - tf.c) / tf.a).astype(int)
        r0 = np.floor((y + half - tf.f) / tf.e).astype(int); r1 = np.ceil((y - half - tf.f) / tf.e).astype(int)
        ids = fields.CSBID.to_numpy()
        inside = (c1 > 0) & (c0 < W) & (r1 > 0) & (r0 < H) & (c0 >= -2) & (r0 >= -2) & (c1 <= W + 2) & (r1 <= H + 2)
        idx = np.where(inside)[0]
        if len(idx):
            blk = pd.Series(list(zip((x[idx] // a.block_m).astype(int), (y[idx] // a.block_m).astype(int))))
            ds = {k: open_raster(info["files"][v], a) for k, v in bn.items()}
            for _, grp in blk.groupby(blk):
                ii = idx[grp.index.to_numpy()]
                cA, rA = max(int(c0[ii].min()), 0), max(int(r0[ii].min()), 0)
                cB, rB = min(int(c1[ii].max()), W), min(int(r1[ii].max()), H)
                if cB <= cA or rB <= rA: continue
                win = Window(cA, rA, cB - cA, rB - rA)
                refl = {}
                for k, d in ds.items():
                    arr = d.read(1, window=win).astype("float32")
                    arr[arr <= -9000] = np.nan
                    refl[k] = arr * 1e-4
                q = fm.read(1, window=win)
                ok = ((q & 0x1E) == 0) & (q != 255)
                with np.errstate(divide="ignore", invalid="ignore"):
                    ndvi = (refl["nir"] - refl["red"]) / (refl["nir"] + refl["red"])
                    evi = np.clip(2.5 * (refl["nir"] - refl["red"]) / (refl["nir"] + 6 * refl["red"] - 7.5 * refl["blue"] + 1), -1, 1)
                    ndwi = ((refl["green"] - refl["nir"]) / (refl["green"] + refl["nir"]) if a.ndwi == "mcfeeters"
                            else (refl["nir"] - refl["swir"]) / (refl["nir"] + refl["swir"]))
                good = ok & np.isfinite(ndvi) & np.isfinite(evi) & np.isfinite(ndwi)
                for i in ii:
                    a0, b0 = max(int(c0[i]), cA) - cA, max(int(r0[i]), rA) - rA
                    a1, b1 = min(int(c1[i]), cB) - cA, min(int(r1[i]), rB) - rA
                    if a1 <= a0 or b1 <= b0: continue
                    g = geoms.get(ids[i]) if polys is not None else box(x[i] - half[i], y[i] - half[i], x[i] + half[i], y[i] + half[i])
                    if g is None: continue
                    sw = Window(cA + a0, rA + b0, a1 - a0, b1 - b0)
                    m = rasterize([(g, 1)], out_shape=(b1 - b0, a1 - a0), transform=wtransform(sw, tf), fill=0, dtype="uint8").astype(bool)
                    npx = int(m.sum())
                    if npx == 0: continue
                    mm = m & good[b0:b1, a0:a1]
                    nv = int(mm.sum())
                    if nv < max(3, a.min_valid_frac * npx): continue
                    rows.append((ids[i], info["date"], info["sensor"], info["tile"], float(ndvi[b0:b1, a0:a1][mm].mean()),
                                 float(evi[b0:b1, a0:a1][mm].mean()), float(ndwi[b0:b1, a0:a1][mm].mean()), nv, npx))
            for d in ds.values(): d.close()
        fm.close()
    df = pd.DataFrame(rows, columns=["CSBID", "date", "sensor", "tile", "ndvi", "evi", "ndwi", "n_valid_px", "n_px"])
    df = df.astype({"CSBID": "string", "sensor": "string", "tile": "string", "ndvi": "float64", "evi": "float64", "ndwi": "float64",
                    "n_valid_px": "int32", "n_px": "int32"})          # explicit types, also for granules without any field-date
    df["date"] = pd.to_datetime(df["date"])
    tmp = Path(str(dst) + ".part"); df.to_parquet(tmp, compression="zstd", index=False); tmp.replace(dst)
    return gid, len(df)


def need_fields(out):
    f = Path(out) / "fields.parquet"
    if not f.exists():
        sys.exit(f"{f} not found. Run the `sample` step first with the same --out, e.g.\n"
                 f"  python crop_ts.py sample --attrs <csb_work>/attrs --year <YYYY> --state 19 --out {out}")
    return pd.read_parquet(f)


def cmd_extract(a):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    out = Path(a.out); (out / "obs").mkdir(parents=True, exist_ok=True)
    fields = need_fields(out)
    gr = granule_table(a, fields)
    if not gr: sys.exit("no complete HLS granules found for these fields/dates")
    preflight(gr, a)
    polys = load_polygons(a, fields.CSBID) if a.polygons else None
    todo = {k: v for k, v in sorted(gr.items(), key=lambda kv: kv[1]["date"])}
    print(f"{len(todo)} granules ({sum(1 for k in todo if (out / 'obs' / (k + '.parquet')).exists())} already done)", flush=True)
    n = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(process_granule, k, v, fields, polys, a): k for k, v in todo.items()}
        for f in as_completed(futs):
            try:
                gid, rows = f.result()
            except Exception as e:
                print(f"  FAILED {futs[f]}: {type(e).__name__}: {e}", file=sys.stderr); continue
            n += 1
            if rows >= 0 and (n % 10 == 0 or n == len(futs)): print(f"  {n}/{len(futs)} granules  (last {gid}: {rows} field-dates)", flush=True)
    print("done; re-run the same command to retry failed granules (finished ones are skipped)")


# ------------------------------------------------------------------ compose
def cmd_compose(a):
    import duckdb
    out = Path(a.out); T = a.steps
    fields = need_fields(out)
    obs = (out / "obs" / "*.parquet").as_posix()
    if not list((out / "obs").glob("*.parquet")): sys.exit("no observations; run extract first")
    d0 = dt.date.fromisoformat(f"{a.year}-{a.start}"); d1 = dt.date.fromisoformat(f"{a.year}-{a.end}")
    span = (d1 - d0).days + 1
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{a.memory}'")
    agg = con.execute(f"""SELECT CSBID, CAST(floor(date_diff('day', DATE '{d0}', CAST(date AS DATE)) * {T}.0 / {span}) AS INT) AS step,
            median(ndvi) AS ndvi, median(evi) AS evi, median(ndwi) AS ndwi, count(*) AS n
        FROM read_parquet('{obs}', union_by_name=true) WHERE CSBID IS NOT NULL AND CAST(date AS DATE) BETWEEN DATE '{d0}' AND DATE '{d1}' GROUP BY 1, 2""").df()
    pos = {k: i for i, k in enumerate(fields.CSBID)}
    N = len(fields)
    X = np.full((N, 3, T), np.nan, dtype="float64")
    ii = agg["CSBID"].map(pos).to_numpy(); ss = agg["step"].to_numpy()
    for c, name in enumerate(CH):
        X[ii, c, ss] = agg[name].to_numpy()
    obs_mask = ~np.isnan(X)
    n_ch = obs_mask.sum(axis=2)                                   # (N, 3) observed steps per channel
    keep = (n_ch >= a.min_steps).all(axis=1)
    print(f"{N:,} fields sampled; {int((n_ch.max(axis=1) > 0).sum()):,} have any observation; {int(keep.sum()):,} have >= {a.min_steps} observed steps in all channels")
    t = np.arange(T)
    Xk, mk = X[keep], obs_mask[keep]
    for n_ in range(len(Xk)):                                      # linear interpolation, nearest at the ends
        for c in range(3):
            m = mk[n_, c]
            Xk[n_, c] = np.interp(t, t[m], Xk[n_, c, m])
    Xk = np.clip(Xk, -1.0, 1.0).astype("float32")
    assert not np.isnan(Xk).any()
    meta = fields[keep].reset_index(drop=True).copy()
    meta["n_observed_steps"] = mk[:, 0, :].sum(axis=1).astype("int16")
    meta["n_observed_steps_min_channel"] = mk.sum(axis=2).min(axis=1).astype("int16")
    # split: by county when there are enough counties, else by field
    rng = np.random.default_rng(a.seed)
    if meta.county_fips.nunique() >= 5:
        cs = sorted(meta.county_fips.unique()); rng.shuffle(cs)
        nt, nv = int(round(len(cs) * a.test_frac)), int(round(len(cs) * a.val_frac))
        lab = {c: ("test" if i < nt else "val" if i < nt + nv else "train") for i, c in enumerate(cs)}
        meta["split"] = meta.county_fips.map(lab)
    else:
        u = rng.random(len(meta))
        meta["split"] = np.where(u < a.test_frac, "test", np.where(u < a.test_frac + a.val_frac, "val", "train"))
    ds = out / "dataset"; ds.mkdir(exist_ok=True)
    y = meta["crop_id"].to_numpy().astype("int64")
    np.save(ds / "X.npy", Xk); np.save(ds / "y.npy", y)
    meta.to_parquet(ds / "meta.parquet", compression="zstd", index=False)
    tab = meta.copy()
    feats = {f"{n_}_d{k + 1}": Xk[:, c, k] for c, n_ in enumerate(CH) for k in range(T)}
    tab = pd.concat([tab, pd.DataFrame(feats)], axis=1)
    tab.to_parquet(ds / "tabular.parquet", compression="zstd", index=False)
    if a.csv: tab.to_csv(ds / "tabular.csv", index=False)
    cls = json.loads((out / "classes.json").read_text())
    for k in cls: cls[k]["n_in_dataset"] = int((meta.crop_id == int(k)).sum())
    (ds / "classes.json").write_text(json.dumps(cls, indent=2))
    if a.pt:
        try:
            import torch
            torch.save({"X": torch.from_numpy(Xk), "y": torch.from_numpy(y)}, ds / "X.pt")
        except ImportError:
            print("torch is not installed; skipped X.pt")
    print(f"wrote {ds}: X {Xk.shape} float32, y {y.shape}; range [{Xk.min():.3f}, {Xk.max():.3f}]")
    for k, v in cls.items():
        w = "" if v["n_in_dataset"] >= 1000 else "   (< 1000)"
        print(f"  crop_id {k} {v['name']}: {v['n_in_dataset']:,}{w}")
    print("split:", meta["split"].value_counts().to_dict())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("sample"); s.set_defaults(fn=cmd_sample)
    s.add_argument("--attrs", required=True); s.add_argument("--out", required=True); s.add_argument("--year", type=int, required=True)
    s.add_argument("--classes", type=int, nargs="+", default=[1, 5, 36, 176], help="CDL codes (1 corn, 5 soybeans, 36 alfalfa, 176 grassland/pasture, 24 winter wheat ...)")
    s.add_argument("--n-per-class", type=int, default=2000); s.add_argument("--min-acres", type=float, default=20)
    s.add_argument("--state"); s.add_argument("--counties", nargs="*"); s.add_argument("--seed", default="1"); s.add_argument("--memory", default="2GB")
    e = sp.add_parser("extract"); e.set_defaults(fn=cmd_extract)
    c = sp.add_parser("compose"); c.set_defaults(fn=cmd_compose)
    for q in (e, c):
        q.add_argument("--out", required=True); q.add_argument("--year", type=int, required=True)
        q.add_argument("--start", default="04-01"); q.add_argument("--end", default="10-31")
    e.add_argument("--products", nargs="+", default=["HLSS30", "HLSL30"]); e.add_argument("--max-cloud", type=int, default=80)
    e.add_argument("--local"); e.add_argument("--auth", choices=["session", "token"], default="session", help="session = earthaccess login (EARTHDATA_USERNAME/PASSWORD or token); token = GDAL bearer header")
    e.add_argument("--polygons", help="glob of GeoJSON files with CSBID property (csb_geometry.py output)")
    e.add_argument("--inner-buffer-m", type=float, default=30.0); e.add_argument("--shrink", type=float, default=0.7)
    e.add_argument("--ndwi", choices=["gao", "mcfeeters"], default="gao"); e.add_argument("--min-valid-frac", type=float, default=0.5)
    e.add_argument("--block-m", type=float, default=5000.0); e.add_argument("--workers", type=int, default=4)
    c.add_argument("--steps", type=int, default=16); c.add_argument("--min-steps", type=int, default=8)
    c.add_argument("--val-frac", type=float, default=0.15); c.add_argument("--test-frac", type=float, default=0.15); c.add_argument("--seed", type=int, default=1)
    c.add_argument("--memory", default="2GB"); c.add_argument("--pt", action="store_true"); c.add_argument("--csv", action="store_true")
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()