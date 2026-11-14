#!/usr/bin/env python3
"""Step 5 (optional) - SoilGrids 0-5 cm county means (clay, sand, silt, soc, phh2o, cec), sampled at CSB field centroids.

Static layer, so the output has one row per county (the assembler repeats it for every year).

  download : fetch the Iowa window of each SoilGrids layer by WCS (one small GeoTIFF per property, ~tens of MB at most)
  sample   : read the GeoTIFFs, look up the value at every field centroid (streaming over the ingest batches), convert units,
             average per county weighted by CSBACRES
Examples
  python yield_soil.py download --attrs ./csb_work/attrs --state 19 --tif-dir ./soil_tif
  python yield_soil.py sample   --attrs ./csb_work/attrs --state 19 --tif-dir ./soil_tif --out ./yield_work

Layers: <property>_0-5cm_mean.tif for clay, sand, silt, soc, phh2o, cec. If you already have such GeoTIFFs (any CRS, e.g. clipped from ISRIC's
VRTs or cropped in QGIS) put them in --tif-dir under these names and skip `download`.
Raw integer -> unit: clay/sand/silt /10 -> mass %; soc /10 -> g/kg; phh2o /10 -> pH; cec /10 -> cmol(c)/kg  (ISRIC SoilGrids FAQ table).
--level field (sample): also writes one row per FIELD, <out>/soil_field/part_NNNNNN.parquet (CSBID + the six soil_* columns, one part per ingest
batch, no big table in memory); used by yield_fields_assemble.py.
Output soil_county.parquet: county_fips, soil_clay_0_5_mean, soil_sand_0_5_mean, soil_silt_0_5_mean, soil_soc_0_5_mean,
soil_phh2o_0_5_mean, soil_cec_0_5_mean, (QA) soil_n_fields.

Notes
  * Fields = CSB polygons, so the mean describes cropland soil, not the whole county. Values are 250 m model predictions, not samples.
  * WCS request follows the ISRIC example (VERSION 2.0.1, SUBSET=X/Y in EPSG:152160 = Homolosine, FORMAT=GEOTIFF_INT16, map file
    /map/<property>.map, COVERAGEID <property>_0-5cm_mean). The exact IDs for the 'mean' layers were NOT verified; override with --wcs-template.
    Homolosine is given by the PROJ string +proj=igh +datum=WGS84; if the downloaded tif has no CRS, that string is used.
  * Rasters are read once, as a whole window in their native int16 (an Iowa window is a few million pixels; all of CONUS is ~210 M pixels = ~0.4 GB per property,
    and the WCS download of such a window may be refused - then download per state or clip the VRTs yourself and use --tif-dir). County keys are 5-digit state+county.
  * --state all | 19 | 19,20 (default all).
Deps: pip install rasterio pyproj numpy pandas pyarrow requests duckdb
"""
import argparse, re, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def state_cond(state, col="STATEFIPS"):
    """SQL predicate for --state: 'all', one FIPS ('19') or a comma list ('19,20')"""
    s = str(state).strip().lower()
    if s in ("all", "*", ""):
        return "TRUE"
    return f"lpad(CAST({col} AS VARCHAR), 2, '0') IN (" + ",".join(f"'{x.strip().zfill(2)}'" for x in s.split(",")) + ")"


CKEY = ("CASE WHEN length(CAST(CNTYFIPS AS VARCHAR)) <= 3 THEN lpad(CAST(STATEFIPS AS VARCHAR), 2, '0') || lpad(CAST(CNTYFIPS AS VARCHAR), 3, '0') "
        "ELSE lpad(CAST(CNTYFIPS AS VARCHAR), 5, '0') END")      # 5-digit state+county key (so counties of different states never collide)

PROPS = {"clay": 10.0, "sand": 10.0, "silt": 10.0, "soc": 10.0, "phh2o": 10.0, "cec": 10.0}
IGH = "+proj=igh +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
WCS = ("https://maps.isric.org/mapserv?map=/map/{prop}.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&COVERAGEID={prop}_0-5cm_mean"
       "&FORMAT=GEOTIFF_INT16&SUBSET=X({x0:.0f},{x1:.0f})&SUBSET=Y({y0:.0f},{y1:.0f})"
       "&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/152160&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/152160")


def batches(a, cols):
    files = sorted(Path(a.attrs).glob("batch_*.parquet"))
    if not files:
        sys.exit("no batches in --attrs")
    for f in files:
        df = pd.read_parquet(f, columns=cols)
        sf = df["STATEFIPS"].astype(str).str.zfill(2)
        df["CNTYFIPS"] = np.where(df["CNTYFIPS"].astype(str).str.len() <= 3, sf + df["CNTYFIPS"].astype(str).str.zfill(3), df["CNTYFIPS"].astype(str).str.zfill(5))
        sel = str(a.state).strip().lower()
        if sel not in ("all", "*", ""):
            df = df[sf.isin([x.strip().zfill(2) for x in sel.split(",")])]
        if len(df):
            yield df


def extent(a):
    import duckdb
    r = duckdb.connect().execute(f"SELECT min(centroid_lon), max(centroid_lon), min(centroid_lat), max(centroid_lat) "
                                 f"FROM read_parquet('{(Path(a.attrs) / 'batch_*.parquet').as_posix()}') WHERE {state_cond(a.state)}").fetchone()
    if r[0] is None:
        sys.exit("no fields for this state")
    return r


def cmd_download(a):
    import requests
    from pyproj import Transformer
    lo0, lo1, la0, la1 = extent(a)
    tr = Transformer.from_crs("EPSG:4326", IGH, always_xy=True)
    xs, ys = tr.transform([lo0, lo1, lo0, lo1], [la0, la0, la1, la1])
    m = a.margin_m
    box = dict(x0=min(xs) - m, x1=max(xs) + m, y0=min(ys) - m, y1=max(ys) + m)
    Path(a.tif_dir).mkdir(parents=True, exist_ok=True)
    for prop in PROPS:
        dst = Path(a.tif_dir) / f"{prop}_0-5cm_mean.tif"
        if dst.exists():
            print("have", dst.name); continue
        url = (a.wcs_template or WCS).format(prop=prop, **box)
        r = requests.get(url, timeout=600)
        if r.status_code != 200 or r.content[:4] not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
            sys.exit(f"{prop}: WCS did not return a GeoTIFF (HTTP {r.status_code}): {r.content[:300]!r}\nURL: {url}")
        tmp = Path(str(dst) + ".part"); tmp.write_bytes(r.content); tmp.replace(dst)
        print(f"{prop}: {dst.stat().st_size / 1e6:.1f} MB", flush=True)


def cmd_sample(a):
    import rasterio
    from pyproj import Transformer
    rasters = {}
    for prop in PROPS:
        f = Path(a.tif_dir) / f"{prop}_0-5cm_mean.tif"
        if not f.exists():
            print(f"  missing {f.name}; column will be absent"); continue
        ds = rasterio.open(f)
        crs = ds.crs.to_string() if ds.crs else IGH
        rasters[prop] = (ds.read(1), ds.transform, ds.nodata, Transformer.from_crs("EPSG:4326", crs, always_xy=True))
    if not rasters:
        sys.exit("no GeoTIFFs found")
    acc = {}          # county -> {prop: [sum(w*v), sum(w)]}, n
    nf = {}
    pk = 0
    for df in batches(a, ["CSBID", "STATEFIPS", "CNTYFIPS", "CSBACRES", "centroid_lon", "centroid_lat"]):
        fv = {"CSBID": df["CSBID"].to_numpy()}
        lon, lat, w = df["centroid_lon"].to_numpy(), df["centroid_lat"].to_numpy(), df["CSBACRES"].to_numpy(float)
        for prop, (arr, tf, nod, tr) in rasters.items():
            x, y = tr.transform(lon, lat)
            col = np.floor((np.asarray(x) - tf.c) / tf.a).astype(int)
            row = np.floor((np.asarray(y) - tf.f) / tf.e).astype(int)
            ok = (row >= 0) & (row < arr.shape[0]) & (col >= 0) & (col < arr.shape[1])
            v = np.full(len(df), np.nan)
            v[ok] = arr[row[ok], col[ok]].astype("float64")
            if nod is not None:
                v[v == nod] = np.nan
            v[v < -30000] = np.nan                                  # INT16 nodata safety (-32768)
            v = v / PROPS[prop]
            fv[f"soil_{prop}_0_5_mean"] = v
            g = pd.DataFrame({"c": df["CNTYFIPS"].to_numpy(), "wv": np.where(np.isnan(v), 0, w * v), "w": np.where(np.isnan(v), 0, w),
                              "n": (~np.isnan(v)).astype(int)}).groupby("c").sum()
            for c, r_ in g.iterrows():
                e = acc.setdefault(c, {}).setdefault(prop, [0.0, 0.0])
                e[0] += r_["wv"]; e[1] += r_["w"]
                if prop == "clay":
                    nf[c] = nf.get(c, 0) + int(r_["n"])
        if a.level == "field":
            sd = Path(a.out) / "soil_field"; sd.mkdir(parents=True, exist_ok=True)
            tmp = sd / f"part_{pk:06d}.parquet.part"
            pd.DataFrame(fv).to_parquet(tmp, compression="zstd", index=False); tmp.replace(sd / f"part_{pk:06d}.parquet"); pk += 1
    rows = []
    for c, d in sorted(acc.items()):
        row = {"county_fips": c}
        for prop in PROPS:
            if prop in d and d[prop][1] > 0:
                row[f"soil_{prop}_0_5_mean"] = d[prop][0] / d[prop][1]
        row["soil_n_fields"] = nf.get(c, 0)
        rows.append(row)
    r = pd.DataFrame(rows)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    fn = Path(a.out) / "soil_county.parquet"; r.to_parquet(fn, compression="zstd", index=False)
    print("wrote", fn, f"({len(r)} counties)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    for n, fn in (("download", cmd_download), ("sample", cmd_sample)):
        s = sp.add_parser(n); s.set_defaults(fn=fn)
        s.add_argument("--attrs", required=True); s.add_argument("--state", default="all", help="all | FIPS | FIPS,FIPS (default all)"); s.add_argument("--tif-dir", required=True)
        if n == "download":
            s.add_argument("--margin-m", type=float, default=5000); s.add_argument("--wcs-template")
        else:
            s.add_argument("--out", required=True); s.add_argument("--level", choices=["county", "field"], default="county")
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
