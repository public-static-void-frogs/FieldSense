#!/usr/bin/env python3
"""Per-field original polygon/multipolygon geometry as GeoJSON, with the CRS preserved.

Geometry is NOT stored in the `csb_pipeline.py ingest` output (only centroids). This script takes the fields you select
from the ingest batches (<work>/attrs/batch_*.parquet) and reads their exact geometry back from the original
File Geodatabase, without simplification, reprojection or type changes.

How a field is found in the geodatabase
  ingest reads the layer in order, `batch_N` = layer rows [N*batch_size, (N+1)*batch_size). The script turns each selected
  row into its position in the layer, reads that feature by FID (fast, random access) and CHECKS that the CSBID matches.
  If the FIDs do not line up with positions, it falls back to an attribute query on CSBID (slow: a full scan per chunk).

CRS handling
  * GeoJSON output keeps the geodatabase CRS (not reprojected). A legacy "crs" member is written
    (urn:ogc:def:crs:EPSG::<code> if the CRS has an EPSG code, else its name) because RFC 7946 has no CRS member.
    The exact CRS is also saved as <out>.crs.wkt (full WKT). Readers such as GDAL/QGIS/geopandas honour the "crs" member.
  * Geometry types are written as GDAL reports them. A geodatabase layer is often exposed as MultiPolygon for every
    feature; --unwrap-single turns single-part ones into Polygon (coordinates are untouched).
  * --wgs84 additionally writes a second file in lon/lat (EPSG:4326) for web maps.
  * --format geojsonseq writes one Feature per line (no crs member, use the .crs.wkt) and suits millions of fields.

Selection (from the ingest attributes)
  --ids FILE        text/CSV with CSBIDs (one per line, or a CSBID column)
  --state 19  --county 19015  --limit N

Examples
  python csb_geometry.py --gdb CSB1623.gdb --work ./csb_work --county 19015 --out boone_fields.geojson
  python csb_geometry.py --gdb CSB1623.gdb --work ./csb_work --ids my_fields.csv --out my_fields.geojson --wgs84
  python csb_geometry.py --gdb CSB1623.gdb --work ./csb_work --state 19 --out iowa.geojsonseq --format geojsonseq
  python csb_geometry.py --gdb CSB1623.gdb --work ./csb_work --ids my_fields.csv --out ./per_field --split

Whole dataset, one file per county (resumable; ~3,100 counties; needs several GB of RAM for the field index):
  python csb_geometry.py --gdb CSB1623.gdb --work ./csb_work --out ./geojson_by_county --by-county --unwrap-single
  -> geojson_by_county/<state FIPS>/<county FIPS>.geojson, index.csv, crs.wkt

Deps: pip install geopandas pyogrio pandas pyarrow shapely pyproj
"""
import argparse, json, re, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pyogrio

DEFAULT_PROPS = ["CSBACRES", "STATEFIPS", "CNTYFIPS", "CNTY"]


def find_layer(gdb, layer=None):
    names = [l[0] for l in pyogrio.list_layers(gdb)]
    if layer:
        if layer not in names:
            sys.exit(f"layer {layer!r} not found; available: {names}")
        return layer
    cand = [n for n in names if re.fullmatch(r"national\d+", n, re.I)] or names
    return cand[0]


def read_ids(path):
    raw = Path(path).read_text().splitlines()
    if raw and "CSBID" in raw[0].split(","):
        col = raw[0].split(",").index("CSBID")
        return {ln.split(",")[col].strip() for ln in raw[1:] if ln.strip()}
    return {ln.split(",")[0].strip() for ln in raw if ln.strip()}


def select(a):
    """Return DataFrame: CSBID, pos (position in the layer), plus property columns."""
    files = sorted(Path(a.work, "attrs").glob("batch_*.parquet"))
    if not files:
        sys.exit(f"no batches in {a.work}/attrs; run csb_pipeline.py ingest first")
    first = pq.read_metadata(files[0]).num_rows
    bs = first                                    # every batch except the last has batch_size rows
    ids = read_ids(a.ids) if a.ids else None
    parts, n = [], 0
    for f in files:
        b = int(re.search(r"batch_(\d+)", f.name).group(1))
        have = set(pq.read_schema(f).names)
        want = ["CSBID"] + [c for c in a.props if c in have]
        if a.state and "STATEFIPS" not in want: want.append("STATEFIPS")
        if a.county and "CNTYFIPS" not in want: want.append("CNTYFIPS")
        df = pd.read_parquet(f, columns=want)
        df["pos"] = b * bs + np.arange(len(df))
        if a.state: df = df[df["STATEFIPS"] == str(a.state).zfill(2)]
        if a.county: df = df[df["CNTYFIPS"] == str(a.county).zfill(5)]
        if ids is not None: df = df[df["CSBID"].isin(ids)]
        if a.limit: df = df.head(a.limit - n)
        if len(df):
            parts.append(df); n += len(df)
        if a.limit and n >= a.limit:
            break
    if not parts:
        sys.exit("no fields matched the selection")
    sel = pd.concat(parts, ignore_index=True)
    if ids is not None:
        miss = ids - set(sel["CSBID"])
        if miss:
            print(f"WARNING: {len(miss)} requested IDs not found in the ingest data, e.g. {sorted(miss)[:3]}", file=sys.stderr)
    return sel


def probe_fid_base(gdb, layer, pos0, csbid0):
    for base in (1, 0):
        try:
            g = pyogrio.read_dataframe(gdb, layer=layer, fids=[int(pos0) + base], columns=["CSBID"], read_geometry=False)
            if len(g) and g["CSBID"].iloc[0] == csbid0:
                return base
        except Exception:
            pass
    return None


def read_chunk(gdb, layer, chunk, base):
    """Read geometries for the rows of `chunk` (CSBID, pos). Returns GeoDataFrame aligned to chunk order."""
    import geopandas as gpd
    want = chunk["CSBID"].tolist()
    got = None
    if base is not None:
        g = gpd.read_file(gdb, engine="pyogrio", layer=layer, fids=(chunk["pos"].to_numpy() + base).astype(int).tolist(),
                          columns=["CSBID"])
        if g["CSBID"].tolist() == want:
            got = g
    if got is None:                                  # fallback: attribute query (full scan per call)
        print("  FID lookup did not match; falling back to CSBID query (slow)", file=sys.stderr)
        parts = []
        for i in range(0, len(want), 1000):
            ids = ",".join("'" + x.replace("'", "''") + "'" for x in want[i:i + 1000])
            parts.append(gpd.read_file(gdb, engine="pyogrio", layer=layer, where=f"CSBID IN ({ids})", columns=["CSBID"]))
        g = pd.concat(parts, ignore_index=True)
        g = gpd.GeoDataFrame(g, geometry="geometry", crs=parts[0].crs)
        got = g.set_index("CSBID").loc[want].reset_index()
        got = gpd.GeoDataFrame(got, geometry="geometry", crs=parts[0].crs)
    return got


def crs_member(crs):
    try:
        auth = crs.to_authority()
    except Exception:
        auth = None
    name = f"urn:ogc:def:crs:{auth[0]}::{auth[1]}" if auth else (crs.name or "unknown")
    return {"type": "name", "properties": {"name": name}}


def features(gdf):
    return json.loads(gdf.to_json(na="null", drop_id=True, to_wgs84=False))["features"]


class CollectionWriter:
    """Streams one FeatureCollection (or GeoJSONSeq) to <path>.part and renames it to <path> when finished."""

    def __init__(self, path, fmt, member, wgs84):
        self.final, self.fmt, self.member, self.wgs84 = Path(path), fmt, member, wgs84
        self.final.parent.mkdir(parents=True, exist_ok=True)
        self.fh = self.fh84 = None
        self.sep = self.sep84 = ""
        self.n = 0
        self.part = Path(str(self.final) + ".part")
        self.p84 = self.final.with_name(self.final.stem + "_wgs84.geojson")

    @staticmethod
    def _open(path, member):
        f = open(path, "w", encoding="utf-8")
        head = {"type": "FeatureCollection"}
        if member:
            head["crs"] = member
        f.write(json.dumps(head)[:-1] + ', "features": [\n')
        return f

    def add(self, g):
        if self.fh is None:
            self.fh = self._open(self.part, self.member) if self.fmt == "geojson" else open(self.part, "w", encoding="utf-8")
            if self.wgs84:
                self.fh84 = self._open(str(self.p84) + ".part", None)
        feats = features(g)
        for ft in feats:
            txt = json.dumps(ft, separators=(",", ":"))
            if self.fmt == "geojson":
                self.fh.write(self.sep + txt); self.sep = ",\n"
            else:
                self.fh.write(txt + "\n")
        if self.fh84 is not None:
            for ft in features(g.to_crs(4326)):
                self.fh84.write(self.sep84 + json.dumps(ft, separators=(",", ":"))); self.sep84 = ",\n"
        self.n += len(feats)

    def close(self, ok):
        for f, tail in ((self.fh, "\n]}\n" if self.fmt == "geojson" else ""), (self.fh84, "\n]}\n")):
            if f is not None:
                f.write(tail) if ok else None
                f.close()
        if ok and self.fh is not None:
            self.part.rename(self.final)
            if self.fh84 is not None:
                Path(str(self.p84) + ".part").rename(self.p84)
        else:
            self.part.unlink(missing_ok=True)
            Path(str(self.p84) + ".part").unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gdb", required=True, help="original CSB File Geodatabase (the .gdb folder)")
    p.add_argument("--layer"); p.add_argument("--work", required=True, help="work dir of csb_pipeline.py ingest")
    p.add_argument("--ids"); p.add_argument("--state"); p.add_argument("--county"); p.add_argument("--limit", type=int)
    p.add_argument("--props", nargs="*", default=DEFAULT_PROPS,
                   help="attributes copied into each feature; names or CDL for all CDLyyyy columns")
    p.add_argument("--out", required=True, help="output file; with --split or --by-county an output directory")
    p.add_argument("--format", choices=["geojson", "geojsonseq"], default="geojson")
    p.add_argument("--by-county", action="store_true",
                   help="one file per county: <out>/<state FIPS>/<county FIPS>.geojson (resumable: finished counties are skipped)")
    p.add_argument("--split", action="store_true", help="one GeoJSON file per field in the --out directory")
    p.add_argument("--wgs84", action="store_true", help="also write an EPSG:4326 copy (<name>_wgs84.geojson)")
    p.add_argument("--unwrap-single", action="store_true",
                   help="write single-part MultiPolygons as Polygon (GDAL often reports every polygon of a geodatabase as MultiPolygon)")
    p.add_argument("--chunk", type=int, default=5000)
    a = p.parse_args()
    if a.by_county and a.split:
        sys.exit("use either --by-county or --split, not both")
    if "CDL" in a.props:
        files = sorted(Path(a.work, "attrs").glob("batch_*.parquet"))
        a.props = [c for c in a.props if c != "CDL"] + [c for c in pq.read_schema(files[0]).names if re.fullmatch(r"CDL\d{4}", c)]
    if a.by_county:
        a.props = list(dict.fromkeys(list(a.props) + ["STATEFIPS", "CNTYFIPS", "CNTY"]))

    layer = find_layer(a.gdb, a.layer)
    sel = select(a).sort_values("pos", kind="stable").reset_index(drop=True)
    base = probe_fid_base(a.gdb, layer, sel["pos"].iloc[0], sel["CSBID"].iloc[0])
    print(f"{len(sel):,} fields selected; layer {layer!r}; FID offset {'unknown, using CSBID query' if base is None else base}", flush=True)

    out = Path(a.out)
    state = {"crs": None, "member": None}

    def load(chunk):
        g = read_chunk(a.gdb, layer, chunk, base)
        for c in chunk.columns:
            if c not in ("CSBID", "pos"):
                g[c] = chunk[c].to_numpy()
        g = g.set_geometry("geometry")
        if a.unwrap_single:
            g["geometry"] = g.geometry.apply(lambda x: x.geoms[0] if x is not None and x.geom_type == "MultiPolygon" and len(x.geoms) == 1 else x)
            g = g.set_geometry("geometry")
        if state["crs"] is None:
            if g.crs is None:
                sys.exit("geodatabase layer has no CRS; cannot preserve it")
            state["crs"], state["member"] = g.crs, crs_member(g.crs)
            wkt = (out / "crs.wkt") if (a.split or a.by_county) else Path(str(out) + ".crs.wkt")
            wkt.parent.mkdir(parents=True, exist_ok=True)
            wkt.write_text(g.crs.to_wkt(), encoding="utf-8")
        return g

    ext = "geojson" if a.format == "geojson" else "geojsonseq"
    done = 0
    if a.split:                                           # one file per field
        out.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(sel), a.chunk):
            g = load(sel.iloc[i:i + a.chunk].reset_index(drop=True))
            for ft in features(g):
                fid = ft["properties"]["CSBID"]
                (out / f"{fid}.geojson").write_text(json.dumps({"type": "FeatureCollection", "crs": state["member"], "features": [ft]}), encoding="utf-8")
            done += len(g); print(f"{done:,}/{len(sel):,}", flush=True)
    else:
        if a.by_county:
            groups = [(k, grp) for k, grp in sel.groupby(["STATEFIPS", "CNTYFIPS"], sort=True)]
        else:
            groups = [(None, sel)]
        skipped = 0
        for gi, (key, grp) in enumerate(groups, 1):
            path = out if key is None else out / str(key[0]) / f"{key[1]}.{ext}"
            if key is not None and path.exists():
                skipped += 1; done += len(grp); continue
            w = CollectionWriter(path, a.format, None, a.wgs84)
            ok = False
            try:
                for i in range(0, len(grp), a.chunk):
                    g = load(grp.iloc[i:i + a.chunk].reset_index(drop=True))
                    w.member = state["member"]
                    w.add(g)
                ok = True
            finally:
                w.close(ok)
            done += len(grp)
            if key is None or gi % 25 == 0 or gi == len(groups):
                print(f"{done:,}/{len(sel):,} fields" + (f", county {gi}/{len(groups)}" if key is not None else ""), flush=True)
        if a.by_county:
            idx = sel.groupby(["STATEFIPS", "CNTYFIPS"], sort=True).agg(county_name=("CNTY", "first"), n_fields=("CSBID", "size")).reset_index()
            idx["file"] = [f"{s}/{c}.{ext}" for s, c in zip(idx["STATEFIPS"], idx["CNTYFIPS"])]
            idx.to_csv(out / "index.csv", index=False)
            print(f"{len(groups)} counties ({skipped} already done); index: {out / 'index.csv'}")
    crs = state["crs"]
    print(f"wrote {out}  (CRS {crs.name if crs else '?'}; full WKT in the crs.wkt file)")


if __name__ == "__main__":
    main()
