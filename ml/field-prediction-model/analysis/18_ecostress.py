"""ECOSTRESS evaporative stress (ESI) and daily ET per field from NASA AppEEARS, for M2.

Peak NDVI barely sees the 2021 and 2023 droughts (17): the canopy saturates. ECOSTRESS measures canopy
temperature, so its evaporative stress index (ESI = actual / potential ET, 0-1) drops when a crop runs short
of water while it is still green. Products (70 m, from July 2018, irregular ISS overpasses):
- ECO_L4T_ESI.002: ESI, with the cloud mask;
- ECO_L3T_JET.002: ETdaily, the daily ET ensemble (mm/day).
AppEEARS cuts the 32 sample squares of 16 out on the NASA side, July-August, one request per MGRS tile and
year (AppEEARS sizes a request by the extent of all its polygons; one request for all squares and years is ~40
times over its limit), so no granules are downloaded whole. The script then reads every field centroid of 16's sample on every clear scene and
writes one row per field and scene, plus July-August means per field and year.

An Earthdata login is used only to obtain an AppEEARS token, read from EARTHDATA_USERNAME / EARTHDATA_PASSWORD
at `submit`; the token goes to --token-file (keep it outside shared folders) and the password is not stored.

Usage: python 18_ecostress.py submit --data path/to/Field-Shift-NASA-data --token-file token.json
       python 18_ecostress.py fetch  --data path/to/Field-Shift-NASA-data --token-file token.json
"""
import argparse
import base64
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
import numpy as np
import pandas as pd
import pyproj
import rasterio

API = "https://appeears.earthdatacloud.nasa.gov/api"
CTX = ssl.create_default_context(cafile=certifi.where())
UNIT_M = 20480
LAYERS = [("ECO_L4T_ESI.002", "ESI"), ("ECO_L4T_ESI.002", "cloud"), ("ECO_L3T_JET.002", "ETdaily")]
YEARS = (2020, 2021, 2023, 2024, 2025)
TASK_NAME = "sivozmina_m2_ecostress"


def call(path, token=None, body=None, method=None, auth=None, raw=False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode(auth.encode()).decode()
    req = urllib.request.Request(API + path, data=None if body is None else json.dumps(body).encode(), headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600, context=CTX) as r:
            return r.read() if raw else json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code} {path}: {e.read().decode()[:500]}") from None


def squares(data):
    """The 32 sample squares of 16 as lon/lat polygons."""
    tl = json.loads((data / "greenness/stac/tiles.json").read_text())
    feats = []
    for unit in pd.read_parquet(data / "greenness/sample_units.parquet").unit:
        tile, row, col = unit.split("_")
        t = tl[tile]
        x0, y0 = t["ulx"] + int(col) * UNIT_M, t["uly"] - int(row) * UNIT_M
        xs, ys = [x0, x0 + UNIT_M, x0 + UNIT_M, x0, x0], [y0, y0, y0 - UNIT_M, y0 - UNIT_M, y0]
        lon, lat = pyproj.Transformer.from_crs(t["epsg"], 4326, always_xy=True).transform(xs, ys)
        feats.append({"type": "Feature", "properties": {"unit": unit},
                      "geometry": {"type": "Polygon", "coordinates": [[[round(a, 6), round(b, 6)] for a, b in zip(lon, lat)]]}})
    return {"type": "FeatureCollection", "features": feats}


def submit(args):
    data, out = Path(args.data), Path(args.data) / "raw/ecostress"
    out.mkdir(parents=True, exist_ok=True)
    tf = Path(args.token_file)
    login = json.loads(tf.read_text()) if tf.exists() else {}
    if not login or pd.Timestamp(login["expiration"]) < pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=2):
        login = call("/login", body={}, method="POST", auth=f"{os.environ['EARTHDATA_USERNAME']}:{os.environ['EARTHDATA_PASSWORD']}")
        tf.write_text(json.dumps({"token": login["token"], "expiration": login.get("expiration")}))
        os.chmod(tf, 0o600)
    print("logged in; token valid until", login.get("expiration"))
    # AppEEARS sizes a request by the extent of all its polygons: one request per MGRS tile and year
    groups = {}
    for f in squares(data)["features"]:
        groups.setdefault(f["properties"]["unit"].split("_")[0], []).append(f)
    done = json.loads((out / "tasks.json").read_text()) if (out / "tasks.json").exists() else {}
    for year in YEARS:
        for tile, feats in sorted(groups.items()):
            key = f"{year}_{tile}"
            if key in done:
                continue
            task = {"task_type": "area", "task_name": f"{TASK_NAME}_{key}",
                    "params": {"dates": [{"startDate": f"07-01-{year}", "endDate": f"08-31-{year}"}],
                               "layers": [{"product": p, "layer": l} for p, l in LAYERS],
                               "output": {"format": {"type": "geotiff"}, "projection": "geographic"},
                               "geo": {"type": "FeatureCollection", "features": feats}}}
            done[key] = call("/task", token=login["token"], body=task, method="POST")["task_id"]
            (out / "tasks.json").write_text(json.dumps(done))
    print(f"{len(done)} requests submitted ({len(groups)} tiles x {len(YEARS)} years)")


def fetch(args):
    """Download every file of every finished request, in parallel (one connection is ~25 KB/s from here),
    ESI and cloud first, ETdaily last; then extract."""
    data, out = Path(args.data), Path(args.data) / "raw/ecostress"
    token = json.loads(Path(args.token_file).read_text())["token"]
    tasks = json.loads((out / "tasks.json").read_text())
    jobs = []
    for key, task_id in tasks.items():
        st = call(f"/task/{task_id}", token=token)
        if st.get("status") != "done":
            print(f"{key}: {st.get('status')}, skipped for now")
            continue
        for f in call(f"/bundle/{task_id}", token=token)["files"]:
            p = out / "files" / key / f["file_name"]
            if not (p.exists() and p.stat().st_size == f["file_size"]):
                jobs.append((0 if ("_ESI_" in f["file_name"] or "_cloud_" in f["file_name"]) else 1, task_id, f, p))
    jobs.sort(key=lambda j: j[0])
    print(f"{len(jobs)} files to download, {sum(j[2]['file_size'] for j in jobs) / 1e6:.0f} MB", flush=True)

    def get(job):
        _, task_id, f, p = job
        p.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(5):
            try:
                body = call(f"/bundle/{task_id}/{f['file_id']}", token=token, raw=True)
                tmp = p.with_suffix(p.suffix + ".part")
                tmp.write_bytes(body)
                os.replace(tmp, p)
                return len(body)
            except Exception:
                time.sleep(10 * (attempt + 1))
        return 0
    t0, got = time.time(), 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, n in enumerate(ex.map(get, jobs), 1):
            got += n
            if i % 250 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} files, {got / 1e6:.0f} MB, {(time.time() - t0) / 60:.1f} min", flush=True)
    extract(data, out)


def extract(data, out):
    """Value of every layer at every sample-field centroid, per scene; July-August means per field and year."""
    sample = pd.read_parquet(data / "greenness/sample_fields.parquet", columns=["CSBID", "unit", "centroid_lon", "centroid_lat"])
    rows = []
    pat = re.compile(r"(ECO_L\dT_[A-Z_]+)\.002_(\w+?)_doy(\d{7})(\d{6})_aid(\d+)")
    for p in sorted((out / "files").rglob("*.tif")):
        m = pat.search(p.name)
        if not m:
            continue
        product, layer, ydoy, hms, aid = m.groups()
        with rasterio.open(p) as src:
            b = src.bounds
            inside = sample[(sample.centroid_lon > b.left) & (sample.centroid_lon < b.right) & (sample.centroid_lat > b.bottom) & (sample.centroid_lat < b.top)]
            if inside.empty:
                continue
            vals = np.array([v[0] for v in src.sample(zip(inside.centroid_lon, inside.centroid_lat))], dtype=float)
            nod = src.nodata
        vals[np.isnan(vals) | ((vals == nod) if nod is not None else False)] = np.nan
        rows.append(pd.DataFrame({"CSBID": inside.CSBID.to_numpy(), "layer": layer, "time": pd.to_datetime(ydoy + hms, format="%Y%j%H%M%S"), "value": vals}))
    obs = pd.concat(rows, ignore_index=True).pivot_table(index=["CSBID", "time"], columns="layer", values="value", aggfunc="first").reset_index()
    clear = (obs.get("cloud", 0) == 0) & (obs.get("water", 0) == 0)
    obs["clear"] = clear
    obs.to_parquet(data / "greenness/ecostress_obs.parquet", index=False)
    o = obs[obs.clear & obs.time.dt.month.isin([7, 8])].copy()
    o["year"] = o.time.dt.year
    fy = o.groupby(["CSBID", "year"]).agg(esi_jul_aug=("ESI", "mean"), esi_n=("ESI", "count"),
                                          et_jul_aug=("ETdaily", "mean"), et_n=("ETdaily", "count")).reset_index()
    fy.to_parquet(data / "greenness/ecostress_field_year.parquet", index=False)
    print(f"{len(obs):,} field-scenes ({obs.clear.mean():.1%} clear), {obs.time.dt.normalize().nunique()} scene dates; "
          f"Jul-Aug: {len(fy):,} field-years, median {fy.esi_n.median():.0f} clear ESI values each")
    print(fy.groupby("year")[["esi_jul_aug", "esi_n", "et_jul_aug"]].median().round(3).to_string())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["submit", "fetch", "extract"])
    ap.add_argument("--data", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()
    if args.action == "submit":
        submit(args)
    elif args.action == "fetch":
        fetch(args)
    else:
        extract(Path(args.data), Path(args.data) / "raw/ecostress")


if __name__ == "__main__":
    main()
