"""Field greenness from NASA HLS v2.0 (Sentinel-2 and Landsat, no key): NDVI and NDWI per CSB field, for M2.

M2 needs each field's greenness in drought seasons (2021, 2023) and normal ones (2024, 2025), for fields whose
rotation is known (07). The M1 archive has 2025 only, so this builds the same 16-step tensor:
- source: HLS v2.0 S30 (Sentinel-2) and L30 (Landsat 8/9) on Microsoft Planetary Computer, read with its
  anonymous SAS token (West Europe; the Sentinel-2 COGs on AWS us-west-2 came at ~250 KB/s from here);
  HLS starts there in 2020; reflectance = DN * 0.0001, 30 m, MGRS tiles;
- NDVI = (NIR - red) / (NIR + red), NDWI = (NIR - SWIR1) / (NIR + SWIR1) (Gao, as in the M1 archive);
  S30 bands B04 / B8A / B11, L30 bands B04 / B05 / B06;
- a pixel counts when Fmask bits 0-5 (cirrus, cloud, adjacent, shadow, snow/ice, water) are clear and the
  aerosol level is not high; a field takes the median of its valid pixels in the 3 x 3 window at the centroid
  (fields >= 10 acres, at least 5 valid) or its centroid pixel (5-10 acres);
- sample: whole ~20 x 20 km squares where corn after corn and corn after soybeans both sit in USDM drought
  seasons (07), plus squares never in drought, one square per county, with a bonus for M1-archive fields;
- steps: 16 equal steps over 1 April - 31 October (13.375 days), median of valid observations, gaps filled
  linearly and carried flat at the ends. The 2025 check compares both M1 archive versions with this build.
Per-scene results are written as they finish, so an interrupted run resumes.

Usage: python 16_hls_greenness.py --data path/to/Field-Shift-NASA-data --years 2025 2021 2023 2024 [--dry-run]
"""
import argparse
import json
import os
import ssl
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import certifi
import numpy as np
import pandas as pd
import pyproj
import rasterio
from rasterio.windows import Window

S2_STAC = "https://earth-search.aws.element84.com/v1/search"           # tile footprints only
PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}"
CTX = ssl.create_default_context(cafile=certifi.where())
IOWA_BBOX = [-96.7, 40.3, -90.1, 43.6]
BANDS = {"hls2-s30": {"red": "B04", "nir": "B8A", "swir": "B11", "fmask": "Fmask"},
         "hls2-l30": {"red": "B04", "nir": "B05", "swir": "B06", "fmask": "Fmask"}}
BLOCK = 256
UNIT_M = 20480                                          # sampling square, metres
MIN_ACRES, WINDOW_ACRES = 5, 10
N_DROUGHT_UNITS, N_NORMAL_UNITS = 24, 8
MAX_CLOUD = 60
STEP_DAYS = 214 / 16                                    # 1 April .. 31 October
GDAL_ENV = {"CURL_CA_BUNDLE": certifi.where(), "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_MAX_RETRY": "4", "GDAL_HTTP_RETRY_DELAY": "2"}
_tokens, _lock = {}, threading.Lock()


def http_json(url, body=None):
    for attempt in range(5):
        try:
            r = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                       headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(r, timeout=120, context=CTX).read())
        except Exception as e:
            err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{url}: {err}")


def stac(url, body):
    out, req = [], dict(body, limit=200)
    while True:
        d = http_json(url, req)
        out += d["features"]
        nxt = [l for l in d.get("links", []) if l.get("rel") == "next"]
        if not nxt:
            return out
        req = nxt[0].get("body", req)


def signed(href, collection):
    """Planetary Computer anonymous SAS token, refreshed 10 minutes before it expires."""
    with _lock:
        tok, exp = _tokens.get(collection, (None, 0))
        if time.time() > exp - 600:
            d = http_json(PC_TOKEN.format(collection=collection))
            exp = datetime.fromisoformat(d["msft:expiry"].replace("Z", "+00:00")).timestamp()
            tok = d["token"]
            _tokens[collection] = (tok, exp)
    return f"{href}?{tok}"


def tiles(cache):
    path = cache / "tiles.json"
    if not path.exists():
        feats = stac(S2_STAC, {"collections": ["sentinel-2-c1-l2a"], "bbox": IOWA_BBOX, "datetime": "2025-07-01T00:00:00Z/2025-07-15T23:59:59Z"})
        t = {}
        for f in feats:
            tr = f["assets"]["red"]["proj:transform"]
            t[f["properties"]["grid:code"].removeprefix("MGRS-")] = {"epsg": f["properties"]["proj:epsg"], "ulx": tr[2], "uly": tr[5]}
        path.write_text(json.dumps(t))
    return json.loads(path.read_text())


def assign(fields, tl):
    """Each field to the MGRS tile where its centroid sits deepest; its 30 m pixel and its sampling square."""
    best = np.full(len(fields), -1.0)
    tile, xs, ys = np.empty(len(fields), dtype=object), np.zeros(len(fields)), np.zeros(len(fields))
    for code, t in tl.items():
        x, y = pyproj.Transformer.from_crs(4326, t["epsg"], always_xy=True).transform(fields.centroid_lon.values, fields.centroid_lat.values)
        margin = np.minimum.reduce([x - t["ulx"], t["ulx"] + 109800 - x, t["uly"] - y, y - (t["uly"] - 109800)])
        better = margin > best
        best[better], tile[better], xs[better], ys[better] = margin[better], code, x[better], y[better]
    f = fields.assign(tile=tile, x=xs, y=ys)[best > 30].copy()
    ulx, uly = f.tile.map({k: v["ulx"] for k, v in tl.items()}), f.tile.map({k: v["uly"] for k, v in tl.items()})
    f["c30"], f["r30"] = ((f.x - ulx) // 30).astype(int), ((uly - f.y) // 30).astype(int)
    f["unit"] = f.tile + "_" + ((uly - f.y) // UNIT_M).astype(int).astype(str) + "_" + ((f.x - ulx) // UNIT_M).astype(int).astype(str)
    return f[f.c30.between(1, 3658) & f.r30.between(1, 3658)]


def select_units(f, hist, m1):
    """Squares with both corn arms in drought (2021, 2023), squares never in drought, M1 fields as a bonus."""
    h = hist[hist.season.isin([2021, 2023]) & (hist.crop_t == 1) & hist.crop_t1.isin([1, 5])]
    h = h.merge(f[f.area_acres >= MIN_ACRES][["CSBID", "unit"]], on="CSBID")
    g = h.groupby(["unit", "usdm_drought_season", "crop_t1"]).size().unstack("crop_t1", fill_value=0)
    pair = g[[1, 5]].min(axis=1).unstack("usdm_drought_season", fill_value=0)
    u = pd.DataFrame({"drought_pairs": pair.get(True, 0), "normal_pairs": pair.get(False, 0)}).fillna(0)
    u["drought_fields"] = h[h.usdm_drought_season].groupby("unit").size().reindex(u.index, fill_value=0)
    u["m1_fields"] = f[f.CSBID.isin(m1)].groupby("unit").size().reindex(u.index, fill_value=0)
    u["county"] = f.groupby("unit").county_fips.agg(lambda s: s.mode().iat[0]).reindex(u.index)
    u["score_d"], u["score_n"] = u.drought_pairs + 10 * u.m1_fields, u.normal_pairs + 10 * u.m1_fields
    pick, used = [], set()
    for kind, cond, score, n in (("drought", u.drought_pairs > 0, "score_d", N_DROUGHT_UNITS),
                                 ("normal", u.drought_fields == 0, "score_n", N_NORMAL_UNITS)):
        k = 0
        for unit, r in u[cond].sort_values(score, ascending=False).iterrows():
            if r.county not in used and k < n:
                pick.append((unit, kind)); used.add(r.county); k += 1
    return u.loc[[p[0] for p in pick]].assign(kind=[p[1] for p in pick])


def scenes(sample, year, cache):
    """HLS S30 and L30 items of each sampled square's own tile, April-October, below MAX_CLOUD."""
    path = cache / f"hls_items_{year}.json"
    if not path.exists():
        items = {}
        for unit, g in sample.groupby("unit"):
            tile = g.tile.iat[0]
            lon, lat = g.centroid_lon.mean(), g.centroid_lat.mean()
            feats = stac(PC_STAC, {"collections": list(BANDS), "intersects": {"type": "Point", "coordinates": [lon, lat]},
                                   "datetime": f"{year}-04-01T00:00:00Z/{year}-10-31T23:59:59Z", "query": {"eo:cloud_cover": {"lt": MAX_CLOUD}}})
            # older items carry no proj:transform; HLS tiles share the Sentinel-2 MGRS origins, 30 m
            origin = [30.0, 0.0, float(g.ulx.iat[0]), 0.0, -30.0, float(g.uly.iat[0])]
            for x in feats:
                if f".T{tile}." in x["id"]:
                    tr = x["properties"].get("proj:transform") or x["assets"]["B04"].get("proj:transform") or origin
                    items[x["id"]] = {"id": x["id"], "collection": x["collection"], "tile": tile, "datetime": x["properties"]["datetime"],
                                      "cloud": x["properties"]["eo:cloud_cover"], "transform": tr[:6],
                                      "assets": {k: x["assets"][b]["href"] for k, b in BANDS[x["collection"]].items()}}
        path.write_text(json.dumps(list(items.values())))
    return json.loads(path.read_text())


def read_item(item, fields, out_path):
    """All sample fields of one tile in one scene: read only the 256 x 256 blocks that hold them."""
    t = item["transform"]
    c = fields.c30.to_numpy() if t[2] == fields.ulx.iat[0] else ((fields.x - t[2]) // 30).astype(int).to_numpy()
    r = fields.r30.to_numpy() if t[5] == fields.uly.iat[0] else ((t[5] - fields.y) // 30).astype(int).to_numpy()
    groups = fields.groupby([c // BLOCK, r // BLOCK]).indices
    win = {}
    with rasterio.Env(**GDAL_ENV):
        for band in ("red", "nir", "swir", "fmask"):
            vals = np.full((len(fields), 9), -9999, dtype=np.int32)
            for attempt in range(4):
                try:
                    with rasterio.open(signed(item["assets"][band], item["collection"])) as src:
                        for (bc, br), idx in groups.items():
                            x0, y0 = max(bc * BLOCK - 1, 0), max(br * BLOCK - 1, 0)
                            w = Window(x0, y0, min(BLOCK + 2, src.width - x0), min(BLOCK + 2, src.height - y0))
                            block = src.read(1, window=w, boundless=False).astype(np.int32)
                            cc, rr = c[idx] - x0, r[idx] - y0
                            vals[idx] = np.stack([block[np.clip(rr + dr, 0, block.shape[0] - 1), np.clip(cc + dc, 0, block.shape[1] - 1)]
                                                  for dr in (-1, 0, 1) for dc in (-1, 0, 1)], axis=1)
                    break
                except rasterio.errors.RasterioIOError:
                    time.sleep(5 * (attempt + 1))
            else:
                raise RuntimeError(f"{item['id']} {band}: read failed")
            win[band] = vals
    fm = win["fmask"]
    ok = (fm >= 0) & ((fm & 0x3F) == 0) & ((fm >> 6) != 3)
    for b in ("red", "nir", "swir"):
        ok &= win[b] != -9999
    small = (fields.area_acres < WINDOW_ACRES).to_numpy()
    ok[small] &= np.isin(np.arange(9), [4])[None, :]                       # small fields: centroid pixel only
    n_ok = ok.sum(axis=1)
    enough = np.where(small, n_ok >= 1, n_ok >= 5)
    refl = {b: np.where(ok, win[b] * 1e-4, np.nan) for b in ("red", "nir", "swir")}
    with np.errstate(all="ignore"):
        ndvi = np.nanmedian((refl["nir"] - refl["red"]) / (refl["nir"] + refl["red"]), axis=1)
        ndwi = np.nanmedian((refl["nir"] - refl["swir"]) / (refl["nir"] + refl["swir"]), axis=1)
    covered = (win["fmask"][:, 4] >= 0) & (win["red"][:, 4] != -9999)
    df = pd.DataFrame({"CSBID": fields.CSBID.to_numpy(), "item": item["id"], "sensor": item["collection"][-3:].upper(),
                       "date": pd.Timestamp(item["datetime"][:10]), "ndvi": ndvi, "ndwi": ndwi, "n_valid_px": n_ok,
                       "valid": enough & np.isfinite(ndvi) & np.isfinite(ndwi)})[covered]
    tmp = out_path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, out_path)
    return len(df), int(df.valid.sum())


def composite(obs, year):
    """16 steps over 1 Apr - 31 Oct: median of valid observations, linear fill, flat ends."""
    o = obs[obs.valid].copy()
    o["step"] = ((o.date - pd.Timestamp(year, 4, 1)).dt.days // STEP_DAYS).astype(int) + 1
    o = o[o.step.between(1, 16)]
    res = pd.DataFrame(index=pd.Index(sorted(o.CSBID.unique()), name="CSBID"))
    for idx in ("ndvi", "ndwi"):
        m = o.groupby(["CSBID", "step"])[idx].median().unstack().reindex(columns=range(1, 17))
        if idx == "ndvi":
            res["n_observed_steps"] = m.notna().sum(axis=1)
        m = m.T.interpolate(limit_direction="both").T
        m.columns = [f"{idx}_d{k}" for k in m.columns]
        res = res.join(m)
    return res.reset_index().assign(year=year)


def check_2025(tensor, data):
    """This build against both M1 archive versions on shared fields: r and bias per step, with lags."""
    rows = []
    for v in ("v1", "v2"):
        a = pd.read_parquet(Path(data) / f"src/greenness_2025_{v}/dataset/tabular.parquet")
        j = tensor.merge(a, on="CSBID", suffixes=("_hls", "_m1"))
        for idx in ("ndvi", "ndwi"):
            s = j[[f"{idx}_d{k}_hls" for k in range(1, 17)]].to_numpy()
            m = j[[f"{idx}_d{k}_m1" for k in range(1, 17)]].to_numpy()
            for lag in range(-2, 3):
                a_, b_ = s[:, max(0, -lag):16 - max(0, lag)], m[:, max(0, lag):16 - max(0, -lag)]
                r = [np.corrcoef(a_[:, k], b_[:, k])[0, 1] for k in range(a_.shape[1])]
                rows.append({"version": v, "index": idx, "lag_steps": lag, "fields": len(j), "mean_step_r": np.nanmean(r),
                             "r_pooled": np.corrcoef(a_.ravel(), b_.ravel())[0, 1], "bias_hls_minus_m1": float(np.mean(a_ - b_))})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--years", type=int, nargs="+", default=[2025, 2021, 2023, 2024])
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true", help="one scene of one tile, printed")
    args = ap.parse_args()
    D = Path(args.data)
    out = D / "greenness"
    cache = out / "stac"
    cache.mkdir(parents=True, exist_ok=True)

    sample_path = out / "sample_fields.parquet"
    if not sample_path.exists():
        tl = tiles(cache)
        fields = pd.read_parquet(D / "field_daily_2025/fields.parquet", columns=["CSBID", "county_fips", "centroid_lon", "centroid_lat", "area_acres"])
        f = assign(fields, tl)
        hist = pd.read_parquet(D / "m2/field_season_drought.parquet", columns=["CSBID", "season", "usdm_drought_season", "crop_t", "crop_t1"])
        m1 = set(pd.read_parquet(D / "src/greenness_2025_v1/dataset/meta.parquet", columns=["CSBID"]).CSBID)
        sel = select_units(f, hist, m1)
        sample = f[f.unit.isin(sel.index) & (f.area_acres >= MIN_ACRES)].merge(sel[["kind"]], left_on="unit", right_index=True)
        sample["ulx"], sample["uly"] = sample.tile.map({k: v["ulx"] for k, v in tl.items()}), sample.tile.map({k: v["uly"] for k, v in tl.items()})
        sel.reset_index(names="unit").to_parquet(out / "sample_units.parquet", index=False)
        sample.to_parquet(sample_path, index=False)
        print(f"{len(f):,} fields placed in {f.tile.nunique()} tiles; squares picked:")
        print(sel.to_string())
    sample = pd.read_parquet(sample_path)
    m1 = pd.read_parquet(D / "src/greenness_2025_v1/dataset/meta.parquet", columns=["CSBID"]).CSBID
    print(f"sample: {len(sample):,} fields >= {MIN_ACRES} acres in {sample.unit.nunique()} squares "
          f"({(sample.groupby('unit').kind.first() == 'drought').sum()} drought), {sample.tile.nunique()} tiles; "
          f"M1-archive fields: {sample.CSBID.isin(m1).sum()}")

    for year in args.years:
        obs_dir = out / f"obs_{year}"
        obs_dir.mkdir(exist_ok=True)
        items = scenes(sample, year, cache)
        by_tile = {t: g.reset_index(drop=True) for t, g in sample.groupby("tile")}
        jobs = [(it, by_tile[it["tile"]], obs_dir / f"{it['id']}.parquet") for it in sorted(items, key=lambda x: x["datetime"])]
        print(f"{year}: {len(jobs)} scenes ({sum(j[0]['collection'] == 'hls2-s30' for j in jobs)} S30)")
        if args.dry_run:
            it, tf, p = max(jobs, key=lambda j: (j[0]["datetime"][5:7] in ("07", "08")) - j[0]["cloud"] / 100)
            t0 = time.time()
            n, v = read_item(it, tf, p.with_name("dryrun.parquet"))
            d = pd.read_parquet(p.with_name("dryrun.parquet")).merge(
                pd.read_parquet(D / "m2/field_season_drought.parquet", columns=["CSBID", "season", "crop_t1"]).query("season == 2025"), on="CSBID", how="left")
            print(f"dry run {it['id']} ({it['cloud']:.0f}% cloud, {len(tf)} fields of tile {it['tile']}): {n} covered, {v} valid, {time.time() - t0:.1f} s")
            print("valid NDVI by 2024 crop (2025 is mostly the other one):")
            print(d[d.valid].groupby("crop_t1").ndvi.describe().round(3).to_string())
            return
        todo = [j for j in jobs if not j[2].exists()]
        t0, done = time.time(), 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(read_item, *j) for j in todo]
            for fu in as_completed(futs):
                fu.result()
                done += 1
                if done % 25 == 0 or done == len(todo):
                    print(f"  {year}: {done}/{len(todo)} scenes, {(time.time() - t0) / 60:.1f} min", flush=True)
        obs = pd.concat([pd.read_parquet(p) for p in sorted(obs_dir.glob("*.parquet")) if p.name != "dryrun.parquet"], ignore_index=True)
        obs.to_parquet(out / f"hls_obs_{year}.parquet", index=False)
        tensor = composite(obs, year)
        tensor.to_parquet(out / f"hls_tensor_{year}.parquet", index=False)
        print(f"{year}: {len(obs):,} field-scenes, {obs.valid.mean():.1%} valid; tensor {len(tensor):,} fields, "
              f"observed steps median {tensor.n_observed_steps.median():.0f}")
        if year == 2025:
            chk = check_2025(tensor, D)
            print(chk.round(3).to_string(index=False))
            chk.to_csv(out / "check_2025_vs_m1_archive.csv", index=False)
            assert chk[chk.lag_steps == 0].groupby("version").mean_step_r.mean().max() >= 0.5, \
                "HLS and the M1 archive disagree for both versions: check the grid and geolocation"


if __name__ == "__main__":
    main()
