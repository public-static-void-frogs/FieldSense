#!/usr/bin/env python3
"""Collect N NAIP aerial chips (0.6-1 m, RGB+NIR) over Iowa for field-segmentation tests.

Source: Microsoft Planetary Computer STAC, collection "naip" (public COGs; the script fetches a free anonymous SAS token itself,
no account needed). NAIP is the best match for *field boundary* work: individual fields are 100s of pixels wide.
IMPORTANT: Iowa has no 2026 NAIP flight. The newest available year is picked (usually 2023 or 2025), see index.csv.

For every point: newest NAIP scene covering it -> SIZE x SIZE pixel window around the point ->
  <out>/<name>.tif  4-band uint8 (R,G,B,NIR), georeferenced (native UTM)
  <out>/<name>.png  RGB preview
  <out>/index.csv   name, lon, lat, item id, datetime, gsd, crs

  python iowa_samples_naip.py --out ./iowa_naip --n 20 --size 1024
Deps: numpy, rasterio, requests, pillow
"""
import argparse, csv, math, random, sys, time
from pathlib import Path
import numpy as np
import requests

PC = "https://planetarycomputer.microsoft.com/api"
IOWA_BOX = (-95.4, 41.0, -91.2, 43.2)          # lon_min, lat_min, lon_max, lat_max (inside Iowa)


def pick_points(n, seed, min_km=40.0):
    rnd = random.Random(seed); pts = []
    while len(pts) < n:
        lon = rnd.uniform(IOWA_BOX[0], IOWA_BOX[2]); lat = rnd.uniform(IOWA_BOX[1], IOWA_BOX[3])
        if all(math.hypot((lon - x) * 83.0, (lat - y) * 111.0) >= min_km for x, y in pts):
            pts.append((lon, lat))
        elif rnd.random() < 0.001: min_km *= 0.9
    return pts


def load_points(path, n, seed):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    lo = next(k for k in rows[0] if k.lower() in ("lon", "lng", "longitude", "x"))
    la = next(k for k in rows[0] if k.lower() in ("lat", "latitude", "y"))
    random.Random(seed).shuffle(rows)
    return [(float(r[lo]), float(r[la])) for r in rows[:n]]


def retry(fn, tries=4):
    for t in range(tries):
        try: return fn()
        except Exception:
            if t == tries - 1: raise
            time.sleep(2 * (t + 1))


def search(lon, lat, year_min):
    body = {"collections": ["naip"], "intersects": {"type": "Point", "coordinates": [lon, lat]},
            "datetime": f"{year_min}-01-01T00:00:00Z/..", "limit": 5, "sortby": [{"field": "properties.datetime", "direction": "desc"}]}
    def go():
        r = requests.post(f"{PC}/stac/v1/search", json=body, timeout=60); r.raise_for_status(); return r.json().get("features", [])
    return retry(go)


_tok = {}
def sign(href):
    if "token" not in _tok or _tok["exp"] < time.time() + 60:
        r = retry(lambda: requests.get(f"{PC}/sas/v1/token/naip", timeout=60)); r.raise_for_status(); j = r.json()
        _tok.update(token=j["token"], exp=time.time() + 1800)
    return href + ("&" if "?" in href else "?") + _tok["token"]


def read_chip(item, lon, lat, size):
    import rasterio
    from rasterio.windows import Window
    from rasterio.warp import transform
    with rasterio.open(sign(item["assets"]["image"]["href"])) as ds:
        x, y = transform("EPSG:4326", ds.crs, [lon], [lat]); r, c = ds.index(x[0], y[0])
        if not (0 <= r < ds.height and 0 <= c < ds.width): raise ValueError("point outside scene")
        r0 = min(max(r - size // 2, 0), ds.height - size); c0 = min(max(c - size // 2, 0), ds.width - size)
        win = Window(c0, r0, size, size)
        arr = ds.read(window=win); meta = dict(crs=ds.crs, transform=ds.window_transform(win), res=ds.res[0])
    return arr, meta


def save(arr, meta, stem):
    import rasterio
    from PIL import Image
    with rasterio.open(f"{stem}.tif", "w", driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0],
                       dtype=arr.dtype, crs=meta["crs"], transform=meta["transform"], compress="deflate", tiled=True) as dst:
        dst.write(arr)
        if arr.shape[0] == 4: dst.descriptions = ("red", "green", "blue", "nir")
    Image.fromarray(arr[:3].transpose(1, 2, 0)).save(f"{stem}.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="./iowa_naip"); ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--size", type=int, default=1024, help="chip size in pixels (~0.6-1 m each)")
    ap.add_argument("--year-min", type=int, default=2019); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--points", help="csv with lon,lat columns (optional)")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pts = load_points(a.points, a.n * 3, a.seed) if a.points else pick_points(a.n * 2, a.seed)
    rows, done = [], 0
    for i, (lon, lat) in enumerate(pts):
        if done >= a.n: break
        try:
            feats = search(lon, lat, a.year_min)
            if not feats: print(f"  point {i}: no NAIP scene, skipped"); continue
            it = feats[0]; arr, meta = read_chip(it, lon, lat, a.size)
            if (arr[:3].sum(0) == 0).mean() > 0.02: print(f"  point {i}: nodata edge, skipped"); continue
            name = f"iowa_naip_{done:02d}_{it['properties']['datetime'][:4]}"
            save(arr, meta, str(out / name))
            rows.append(dict(name=name, lon=round(lon, 5), lat=round(lat, 5), item=it["id"], datetime=it["properties"]["datetime"],
                             gsd_m=round(meta["res"], 2), crs=str(meta["crs"]), size_px=a.size))
            done += 1; print(f"[{done}/{a.n}] {name}  {it['id']}  {meta['res']:.2f} m", flush=True)
        except Exception as e:
            print(f"  point {i}: {type(e).__name__}: {str(e)[:150]}", file=sys.stderr)
    if rows:
        with open(out / "index.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"done: {done} chips -> {out}")
    if done < a.n: sys.exit(f"only {done}/{a.n} chips")


if __name__ == "__main__":
    main()
