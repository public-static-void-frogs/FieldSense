#!/usr/bin/env python3
"""Approximate bounding boxes for CSB fields from centroid + area (no geometry needed).

Reads the Parquet batches written by `csb_pipeline.py ingest` (<work>/attrs/batch_*.parquet),
builds a box around each field's centre whose area equals the field's area, and writes lon/lat
bounds to <out>/batch_*.parquet. Batch by batch, resumable, flat memory.

THIS IS AN ESTIMATE. A field is irregular, so the true extent differs from the estimate. The box is a
square (default) or a rectangle with an aspect ratio you choose, centred on the point, not rotated.
It always encloses the right AREA, but not the real outline. For exact extents re-run ingest with
--keep-geometry and use the polygons.

Shapes (--shape):
  square   side = sqrt(area)                     box area == field area            (default)
  circle   box of the circle with the same area  side = 2*sqrt(area/pi); box area = 4/pi * field area
           (a safe "will contain a compact field" box, about 27 % larger)

Centre (--centre):
  centroid  centroid_lon/centroid_lat from ingest (default)
  inside    INSIDE_X/INSIDE_Y from NASS (projected metres; guaranteed-inside point, if documented as such)

Examples
  python csb_bounds.py --work ./csb_work --out ./csb_bounds
  python csb_bounds.py --work ./csb_work --out ./csb_bounds --shape circle --aspect 1.5
  python csb_bounds.py --work ./csb_work --out ./csb_bounds --one-file bounds_all.parquet

Deps: pip install pandas pyarrow numpy pyproj
"""
import argparse, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Transformer

ACRE_M2 = 4046.8564224
TO_M = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
TO_DEG = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)


def bounds_for(df, shape="square", aspect=1.0, centre="centroid"):
    """Return DataFrame with bbox columns for every row of df."""
    area_m2 = df["CSBACRES"].to_numpy(dtype="float64") * ACRE_M2
    if shape == "circle":
        area_m2 = area_m2 * 4.0 / math.pi            # bounding square of the equal-area circle
    # width * height = area, width / height = aspect
    w = np.sqrt(area_m2 * aspect)
    h = np.sqrt(area_m2 / aspect)
    if centre == "inside":
        cx, cy = df["INSIDE_X"].to_numpy("float64"), df["INSIDE_Y"].to_numpy("float64")
    else:
        cx, cy = TO_M.transform(df["centroid_lon"].to_numpy("float64"), df["centroid_lat"].to_numpy("float64"))
    xmin, xmax, ymin, ymax = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    lon0, lat0 = TO_DEG.transform(xmin, ymin)
    lon1, lat1 = TO_DEG.transform(xmax, ymax)
    out = pd.DataFrame({
        "CSBID": df["CSBID"].to_numpy(),
        "centroid_lon": df["centroid_lon"].to_numpy(),
        "centroid_lat": df["centroid_lat"].to_numpy(),
        "area_acres": df["CSBACRES"].to_numpy(),
        "bbox_width_m": np.round(w, 1),
        "bbox_height_m": np.round(h, 1),
        "min_lon": np.round(lon0, 6), "min_lat": np.round(lat0, 6),
        "max_lon": np.round(lon1, 6), "max_lat": np.round(lat1, 6),
    })
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--work", required=True, help="work dir used by csb_pipeline.py ingest")
    p.add_argument("--out", required=True, help="output dir (batch_*.parquet) ")
    p.add_argument("--shape", choices=["square", "circle"], default="square")
    p.add_argument("--aspect", type=float, default=1.0, help="width/height of the box (default 1 = square)")
    p.add_argument("--centre", choices=["centroid", "inside"], default="centroid")
    p.add_argument("--keep", nargs="*", default=["STATEFIPS", "CNTYFIPS", "CNTY"],
                   help="extra columns to copy through (also accepts CDLyyyy; use CDL for all CDL columns)")
    p.add_argument("--one-file", help="after processing, merge all batches into this single Parquet file")
    a = p.parse_args()

    files = sorted((Path(a.work) / "attrs").glob("batch_*.parquet"))
    if not files:
        sys.exit("no batches in <work>/attrs; run csb_pipeline.py ingest first")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(files, 1):
        dst = out / f.name
        if dst.exists():
            continue
        df = pd.read_parquet(f)
        need = {"CSBID", "CSBACRES"} | ({"INSIDE_X", "INSIDE_Y"} if a.centre == "inside" else {"centroid_lon", "centroid_lat"})
        miss = need - set(df.columns)
        if miss:
            sys.exit(f"{f.name}: missing columns {sorted(miss)}")
        # centroid lon/lat are still needed in the output for reference
        if "centroid_lon" not in df.columns:
            df["centroid_lon"], df["centroid_lat"] = TO_DEG.transform(df["INSIDE_X"].to_numpy("float64"), df["INSIDE_Y"].to_numpy("float64"))
        res = bounds_for(df, a.shape, a.aspect, a.centre)
        extra = []
        for k in a.keep:
            extra += [c for c in df.columns if c == k or (k == "CDL" and c.startswith("CDL") and c[3:].isdigit())]
        for c in dict.fromkeys(extra):
            res[c] = df[c].to_numpy()
        tmp = Path(str(dst) + ".tmp")
        res.to_parquet(tmp, compression="zstd", index=False)
        tmp.rename(dst)
        print(f"{i}/{len(files)} {f.name} -> {len(res):,} rows", flush=True)
    if a.one_file:
        import pyarrow.parquet as pq, pyarrow as pa
        writer = None
        for f in sorted(out.glob("batch_*.parquet")):
            t = pq.read_table(f)
            writer = writer or pq.ParquetWriter(a.one_file, t.schema, compression="zstd")
            writer.write_table(t)
        if writer:
            writer.close(); print("merged ->", a.one_file)


if __name__ == "__main__":
    main()
