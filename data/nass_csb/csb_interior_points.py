#!/usr/bin/env python3
"""Interior point per field, computed from the polygon GeoJSON files made by `csb_geometry.py` (no geodatabase, no parquet needed).

The centroid of a concave polygon (L-, C-, U-shaped fields) can lie outside the field. This script reads the polygons and writes, for each field,
a Point that is GUARANTEED to be inside the polygon, as GeoJSON (gzip).

  --method polylabel (default)  pole of inaccessibility: the point farthest from the boundary (shapely.ops.polylabel, tolerance --tolerance-m).
                                Best for sampling pixels / building windows, and gives `inner_radius_m` = distance to the nearest boundary.
  --method representative       shapely representative_point(): cheap, inside, but not "central".

Input  : --src folder of <state>/<county>.geojson or .geojson.gz (or .geojsonseq) from `csb_geometry.py --by-county` (files named *_wgs84* are ignored).
         The CRS is read from <src>/crs.wkt, else from the "crs" member of each file; polygons are processed in that (metric) CRS.
         MultiPolygons: the largest part is used for the interior point (an interior point of the whole feature is then inside the field).
Output : Point features in EPSG:4326 (lon, lat) - geometry = the interior point. Properties = all input properties (or --props) plus
           centroid_lon, centroid_lat   true centroid (WGS84) for comparison
           centroid_inside              1 if the centroid is inside the polygon, 0 if not
           inner_radius_m               (polylabel) radius of the largest circle around the point that stays inside the polygon, in CRS units (m)
           point_method                 polylabel | representative
  default      one file --out (e.g. interior_points.geojson.gz)   (sequential)
  --by-county  <out>/<state>/<county>.geojson.gz, same layout as the input; counties are processed IN PARALLEL (--workers) and are
               resumable (finished counties are skipped; .part files are renamed when complete); index.csv summarises them.
  --format geojsonseq  newline-delimited features (.geojsonl.gz)

Examples
  python csb_interior_points.py --src ./geojson_by_county --out ./interior_by_county --by-county --workers 8
  python csb_interior_points.py --src ./geojson_by_county --out iowa_interior.geojson.gz --state 19
  python csb_interior_points.py --src ./geojson_by_county --out ./boone --by-county --county 19015 --method representative

Speed: polylabel costs roughly 0.2-2 ms per field, depending on vertices; use --by-county with --workers for the whole country.
Deps: pip install shapely pyproj
"""
import argparse, glob, gzip, json, os, re, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def find_inputs(src, state, counties):
    files = {}
    for pat in ("*.geojson", "*.geojson.gz", "*.geojsonl", "*.geojsonl.gz", "*.geojsonseq", "*.geojsonseq.gz"):
        for f in glob.glob(str(Path(src) / "**" / pat), recursive=True):
            name = os.path.basename(f)
            if "_wgs84" in name or name.startswith("."):
                continue
            county = name.split(".")[0]
            parent = Path(f).parent.name
            if state and parent != str(state).zfill(2):
                continue
            if counties and county not in {str(c).zfill(5) for c in counties}:
                continue
            files.setdefault((parent, county), f)
    return [(k, v) for k, v in sorted(files.items())]


def iter_features(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as fh:
        head = fh.read(1)
        fh.seek(0)
        txt = fh.read()
    s = txt.lstrip()
    if s.startswith("{") and '"features"' in s[:5000] and '"FeatureCollection"' in s[:200]:
        d = json.loads(s)
        return d.get("features", []), d.get("crs")
    return [json.loads(ln) for ln in txt.splitlines() if ln.strip() and not ln.startswith("\x1e")], None      # geojsonseq


def get_crs(src_dir, member):
    from pyproj import CRS
    w = Path(src_dir) / "crs.wkt"
    if w.exists():
        return CRS.from_wkt(w.read_text(encoding="utf-8"))
    if member:
        return CRS.from_user_input(member["properties"]["name"])
    sys.exit("no CRS: put crs.wkt in --src (csb_geometry.py writes it) or use files with a crs member")


def convert(path, src_dir, method, tol, props_keep):
    """Return list of JSON strings (Point features in WGS84) for one input file."""
    from shapely.geometry import shape
    from shapely.ops import polylabel, transform
    from pyproj import Transformer
    feats, member = iter_features(path)
    crs = get_crs(src_dir, member)
    tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    out = []
    for ft in feats:
        g = ft.get("geometry")
        if not g:
            continue
        geom = shape(g)
        if geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
        part = geom if geom.geom_type == "Polygon" else max(geom.geoms, key=lambda p: p.area)
        c = geom.centroid
        radius, used = None, "representative"
        if method == "polylabel":
            try:
                pt = polylabel(part, tolerance=tol)
                radius = part.boundary.distance(pt)
                if not geom.covers(pt):
                    raise ValueError
                used = "polylabel"
            except Exception:
                pt = part.representative_point(); radius = None
        else:
            pt = part.representative_point()
        lon, lat = tr.transform(pt.x, pt.y)
        clon, clat = tr.transform(c.x, c.y)
        pr = ft.get("properties") or {}
        if props_keep is not None:
            pr = {k: v for k, v in pr.items() if k in props_keep or k == "CSBID"}
        pr = {**pr, "centroid_lon": round(clon, 6), "centroid_lat": round(clat, 6), "centroid_inside": int(geom.covers(c)),
              "inner_radius_m": None if radius is None else round(float(radius), 2), "point_method": used}
        out.append(json.dumps({"type": "Feature", "id": ft.get("id", pr.get("CSBID")),
                               "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}, "properties": pr},
                              separators=(",", ":")))
    return out


def write_gz(final, feats, seq, level):
    final = Path(final); final.parent.mkdir(parents=True, exist_ok=True)
    part = Path(str(final) + ".part")
    with gzip.open(part, "wt", encoding="utf-8", compresslevel=level) as fh:
        if seq:
            fh.write("\n".join(feats) + ("\n" if feats else ""))
        else:
            fh.write('{"type":"FeatureCollection","features":[\n' + ",\n".join(feats) + "\n]}\n")
    part.replace(final)


def job(args):
    (state, county), path, a_ = args
    ext = "geojson.gz" if a_["fmt"] == "geojson" else "geojsonl.gz"
    dst = Path(a_["out"]) / state / f"{county}.{ext}"
    if dst.exists():
        return state, county, -1, 0
    feats = convert(path, a_["src"], a_["method"], a_["tol"], a_["props"])
    ins = sum(1 for f in feats if '"centroid_inside":0' in f)
    write_gz(dst, feats, a_["fmt"] == "geojsonseq", a_["level"])
    return state, county, len(feats), ins


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", required=True, help="folder written by csb_geometry.py --by-county")
    p.add_argument("--out", required=True)
    p.add_argument("--by-county", action="store_true"); p.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    p.add_argument("--format", choices=["geojson", "geojsonseq"], default="geojson")
    p.add_argument("--method", choices=["polylabel", "representative"], default="polylabel")
    p.add_argument("--tolerance-m", type=float, default=1.0, help="polylabel precision in CRS units (metres)")
    p.add_argument("--state"); p.add_argument("--county", nargs="*"); p.add_argument("--props", nargs="*", help="keep only these input properties (CSBID is always kept)")
    p.add_argument("--level", type=int, default=6)
    a = p.parse_args()
    items = find_inputs(a.src, a.state, a.county)
    if not items:
        sys.exit(f"no county GeoJSON files found under {a.src}")
    keep = set(a.props) if a.props else None
    a_ = dict(src=a.src, out=a.out, method=a.method, tol=a.tolerance_m, props=keep, fmt=a.format, level=a.level)
    ext = "geojson.gz" if a.format == "geojson" else "geojsonl.gz"
    print(f"{len(items)} county files; method {a.method}", flush=True)
    if a.by_county:
        total = outside = skipped = 0
        rows = []
        with ProcessPoolExecutor(a.workers) as ex:
            for i, (st, cn, n, o) in enumerate(ex.map(job, [(k, f, a_) for k, f in items]), 1):
                if n < 0: skipped += 1
                else: total += n; outside += o; rows.append((st, cn, n, f"{st}/{cn}.{ext}"))
                if i % 20 == 0 or i == len(items): print(f"  {i}/{len(items)} counties, {total:,} points", flush=True)
        import csv
        idxf = Path(a.out) / "index.csv"
        old = {}
        if idxf.exists():
            old = {(r["STATEFIPS"], r["CNTYFIPS"]): r for r in csv.DictReader(open(idxf, encoding="utf-8"))}
        for st, cn, n, f in rows: old[(st, cn)] = dict(STATEFIPS=st, CNTYFIPS=cn, n_points=n, file=f)
        Path(a.out).mkdir(parents=True, exist_ok=True)
        with open(idxf, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["STATEFIPS", "CNTYFIPS", "n_points", "file"]); w.writeheader()
            for k in sorted(old): w.writerow({c: old[k].get(c, "") for c in w.fieldnames})
        print(f"wrote {total:,} points in {len(rows)} counties ({skipped} already existed); centroid outside polygon for {outside:,} of them; index: {idxf}")
        return
    out = Path(a.out)
    if not out.name.endswith(".gz"):
        out = Path(str(out) + (".gz" if out.suffix in (".geojson", ".geojsonl", ".geojsonseq") else "." + ext))
    out.parent.mkdir(parents=True, exist_ok=True)
    part = Path(str(out) + ".part"); n = outside = 0; seq = a.format == "geojsonseq"
    with gzip.open(part, "wt", encoding="utf-8", compresslevel=a.level) as fh:
        if not seq: fh.write('{"type":"FeatureCollection","features":[\n')
        for i, (k, f) in enumerate(items, 1):
            for s in convert(f, a.src, a.method, a.tolerance_m, keep):
                outside += '"centroid_inside":0' in s
                fh.write(("," if (n and not seq) else "") + s + "\n"); n += 1
            if i % 20 == 0 or i == len(items): print(f"  {i}/{len(items)} counties, {n:,} points", flush=True)
        if not seq: fh.write("]}\n")
    part.replace(out)
    print(f"wrote {out}: {n:,} points ({outside:,} had a centroid outside the polygon), {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
