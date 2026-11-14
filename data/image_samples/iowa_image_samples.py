#!/usr/bin/env python3
"""Collect N Sentinel-2 L2A (10 m) image chips over Iowa for field-segmentation tests.

Source: Element84 Earth Search STAC (collection sentinel-2-l2a), public COGs on AWS -> NO login/token needed.
Why Sentinel-2 and not NAIP: Iowa has no 2026 NAIP flight; HLS needs Earthdata login. S2 gives 10 m, 4 bands (B04 B03 B02 B08).

For every point: search the growing season, keep the least cloudy scene covering the point, read a SIZE x SIZE pixel window
(default 512 px = 5.12 km) and write
  <out>/<name>.tif   4-band uint16 reflectance*10000 (R,G,B,NIR), georeferenced (native UTM CRS)
  <out>/<name>.png   contrast-stretched RGB preview
  <out>/index.csv    name, lon, lat, scene id, datetime, cloud cover, crs, bounds

Points: --points file.csv (columns lon,lat; e.g. from csb_interior_points) or, by default, N spaced pseudo-random points inside a
rectangle that lies fully within Iowa cropland (41.0-43.2 N, 95.4-91.2 W).

  python iowa_samples.py --out ./iowa_2026 --n 20 --start 2026-06-01 --end 2026-08-31
Deps: numpy, rasterio, requests, pillow
"""
import argparse, csv, math, random, sys, time
from pathlib import Path
import numpy as np
import requests

STAC = "https://earth-search.aws.element84.com/v1/search"
BANDS = ["red", "green", "blue", "nir"]          # B04 B03 B02 B08
IOWA_BOX = (-95.4, 41.0, -91.2, 43.2)            # lon_min, lat_min, lon_max, lat_max (inside Iowa)


def pick_points(n, seed, min_km=40.0):
    rnd = random.Random(seed); pts = []
    while len(pts) < n:
        lon = rnd.uniform(IOWA_BOX[0], IOWA_BOX[2]); lat = rnd.uniform(IOWA_BOX[1], IOWA_BOX[3])
        if all(math.hypot((lon - x) * 83.0, (lat - y) * 111.0) >= min_km for x, y in pts):
            pts.append((lon, lat))
        elif len(pts) < n and rnd.random() < 0.001: min_km *= 0.9      # relax if the box is crowded
    return pts


def load_points(path, n, seed):
    import csv as _c
    rows = list(_c.DictReader(open(path, encoding="utf-8-sig")))
    lo = next(k for k in rows[0] if k.lower() in ("lon", "lng", "longitude", "x"))
    la = next(k for k in rows[0] if k.lower() in ("lat", "latitude", "y"))
    random.Random(seed).shuffle(rows)
    return [(float(r[lo]), float(r[la])) for r in rows[:n]]


def search(lon, lat, start, end, max_cloud):
    body = {"collections": ["sentinel-2-l2a"], "intersects": {"type": "Point", "coordinates": [lon, lat]},
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 50,
            "query": {"eo:cloud_cover": {"lt": max_cloud}}, "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}]}
    for t in range(4):
        try:
            r = requests.post(STAC, json=body, timeout=60); r.raise_for_status()
            return r.json().get("features", [])
        except Exception as e:
            if t == 3: raise
            time.sleep(2 * (t + 1))


def read_chip(item, lon, lat, size):
    import rasterio
    from rasterio.windows import Window
    from rasterio.warp import transform
    arrs, meta = [], None
    for b in BANDS:
        href = item["assets"][b]["href"]
        with rasterio.open(href) as ds:
            if meta is None:
                x, y = transform("EPSG:4326", ds.crs, [lon], [lat]); r, c = ds.index(x[0], y[0])
                r0 = min(max(r - size // 2, 0), ds.height - size); c0 = min(max(c - size // 2, 0), ds.width - size)
                win = Window(c0, r0, size, size)
                meta = dict(crs=ds.crs, transform=ds.window_transform(win), nodata=ds.nodata)
            arrs.append(ds.read(1, window=win))
    return np.stack(arrs).astype("uint16"), meta


def save(arr, meta, stem, item):
    import rasterio
    from PIL import Image
    with rasterio.open(f"{stem}.tif", "w", driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=4, dtype="uint16",
                       crs=meta["crs"], transform=meta["transform"], compress="deflate", tiled=True) as dst:
        dst.write(arr); dst.descriptions = ("B04_red", "B03_green", "B02_blue", "B08_nir")
    rgb = arr[:3].astype("float32")
    lo, hi = np.percentile(rgb[rgb > 0], (2, 98)) if (rgb > 0).any() else (0, 3000)
    img = np.clip((rgb - lo) / max(hi - lo, 1), 0, 1)
    Image.fromarray((img.transpose(1, 2, 0) * 255).astype("uint8")).save(f"{stem}.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="./iowa_2026"); ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--start", default="2026-06-01"); ap.add_argument("--end", default="2026-08-31")
    ap.add_argument("--size", type=int, default=512, help="chip size in pixels (10 m each)")
    ap.add_argument("--max-cloud", type=float, default=10.0); ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--points", help="csv with lon,lat columns (optional)")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pts = load_points(a.points, a.n * 3, a.seed) if a.points else pick_points(a.n * 2, a.seed)
    rows, done = [], 0
    for i, (lon, lat) in enumerate(pts):
        if done >= a.n: break
        try:
            feats = search(lon, lat, a.start, a.end, a.max_cloud)
            if not feats: print(f"  point {i}: no scene < {a.max_cloud}% cloud, skipped"); continue
            it = feats[0]
            arr, meta = read_chip(it, lon, lat, a.size)
            if (arr[0] == 0).mean() > 0.02: print(f"  point {i}: nodata edge, skipped"); continue
            name = f"iowa_{done:02d}_{it['properties']['datetime'][:10]}"
            save(arr, meta, str(out / name), it)
            rows.append(dict(name=name, lon=round(lon, 5), lat=round(lat, 5), scene=it["id"], datetime=it["properties"]["datetime"],
                             cloud=it["properties"]["eo:cloud_cover"], crs=str(meta["crs"]), px_size_m=10, size_px=a.size))
            done += 1; print(f"[{done}/{a.n}] {name}  {it['id']}  cloud {it['properties']['eo:cloud_cover']:.1f}%", flush=True)
        except Exception as e:
            print(f"  point {i}: {type(e).__name__}: {str(e)[:150]}", file=sys.stderr)
    if rows:
        with open(out / "index.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"done: {done} chips -> {out}")
    if done < a.n: sys.exit(f"only {done}/{a.n}: widen --start/--end or raise --max-cloud")


if __name__ == "__main__":
    main()
