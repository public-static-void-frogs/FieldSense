#!/usr/bin/env python3
"""Explore and extract data from the NASS Crop Sequence Boundaries (CSB) File Geodatabase.

Expected layout (2023 edition): NationalCSB_2016-2023_rev23/CSB1623.gdb, layer 'national1623'.
Columns: CSBID, CSBACRES, CDL2016..CDL2023, STATEFIPS, STATEASD, ASD, CNTY, CNTYFIPS, geometry (EPSG:5070).
The gdb holds ~16 M polygons: ALWAYS filter (state / county / bbox) before loading geometry.

Subcommands
  info     GDB layers, columns, CRS, feature count (no geometry read)
  stats    crop acreage per year, for a state/county, attributes only (fast, no geometry)
  rotation most common crop sequences (rotations) in an area, with acreage
  export   extract an area to GeoParquet/GeoPackage + a long CSV (one row per field per year, with centroid lon/lat)

Examples
  python csb_explore.py info  CSB1623.gdb
  python csb_explore.py stats CSB1623.gdb --state 19 --top 15
  python csb_explore.py rotation CSB1623.gdb --state 19 --county 19015 --top 20
  python csb_explore.py export CSB1623.gdb --state 19 --county 19015 --out boone_ia
  python csb_explore.py export CSB1623.gdb --bbox -93.8 41.9 -93.6 42.1 --out ames --crops 1 5

Deps: pip install geopandas pyogrio pandas pyarrow shapely   (needs GDAL with OpenFileGDB driver; pyogrio wheels include it)
"""
import argparse, re, sys
from pathlib import Path
import pandas as pd

# CDL class codes -> names. Partial list of the most common classes; unknown codes print as "code_<n>".
# Verify against the official CDL legend before publishing results.
CDL = {
    1: "Corn", 2: "Cotton", 3: "Rice", 4: "Sorghum", 5: "Soybeans", 6: "Sunflower", 10: "Peanuts",
    11: "Tobacco", 12: "Sweet Corn", 13: "Pop or Orn Corn", 14: "Mint", 21: "Barley", 22: "Durum Wheat",
    23: "Spring Wheat", 24: "Winter Wheat", 25: "Other Small Grains", 26: "Dbl Crop WinWht/Soybeans",
    27: "Rye", 28: "Oats", 29: "Millet", 30: "Speltz", 31: "Canola", 32: "Flaxseed", 33: "Safflower",
    34: "Rape Seed", 35: "Mustard", 36: "Alfalfa", 37: "Other Hay/Non Alfalfa", 38: "Camelina",
    39: "Buckwheat", 41: "Sugarbeets", 42: "Dry Beans", 43: "Potatoes", 44: "Other Crops",
    45: "Sugarcane", 46: "Sweet Potatoes", 47: "Misc Vegs & Fruits", 48: "Watermelons", 49: "Onions",
    50: "Cucumbers", 51: "Chick Peas", 52: "Lentils", 53: "Peas", 54: "Tomatoes", 55: "Caneberries",
    56: "Hops", 57: "Herbs", 58: "Clover/Wildflowers", 59: "Sod/Grass Seed", 60: "Switchgrass",
    61: "Fallow/Idle Cropland", 62: "Pasture/Grass", 63: "Forest", 64: "Shrubland", 65: "Barren",
    66: "Cherries", 67: "Peaches", 68: "Apples", 69: "Grapes", 70: "Christmas Trees", 71: "Other Tree Crops",
    72: "Citrus", 74: "Pecans", 75: "Almonds", 76: "Walnuts", 77: "Pears", 111: "Open Water",
    121: "Developed/Open Space", 122: "Developed/Low Intensity", 123: "Developed/Med Intensity",
    124: "Developed/High Intensity", 131: "Barren", 141: "Deciduous Forest", 142: "Evergreen Forest",
    143: "Mixed Forest", 152: "Shrubland", 176: "Grass/Pasture", 190: "Woody Wetlands", 195: "Herbaceous Wetlands",
    204: "Pistachios", 205: "Triticale", 206: "Carrots", 207: "Asparagus", 208: "Garlic", 209: "Cantaloupes",
    213: "Honeydew Melons", 214: "Broccoli", 216: "Peppers", 217: "Pomegranates", 218: "Nectarines",
    219: "Greens", 220: "Plums", 221: "Strawberries", 222: "Squash", 223: "Apricots", 224: "Vetch",
    225: "Dbl Crop WinWht/Corn", 226: "Dbl Crop Oats/Corn", 227: "Lettuce", 228: "Dbl Crop Triticale/Corn",
    229: "Pumpkins", 236: "Dbl Crop WinWht/Sorghum", 237: "Dbl Crop Barley/Corn", 238: "Dbl Crop WinWht/Cotton",
    239: "Dbl Crop Soybeans/Cotton", 240: "Dbl Crop Soybeans/Oats", 241: "Dbl Crop Corn/Soybeans",
    254: "Dbl Crop Barley/Soybeans",
}
AC_TO_HA = 0.404686


def name(code):
    try:
        c = int(code)
    except (TypeError, ValueError):
        return None
    return CDL.get(c, f"code_{c}")


def find_layer(gdb, layer=None):
    import pyogrio
    layers = pyogrio.list_layers(gdb)          # array of [name, geometry_type]
    names = [l[0] for l in layers]
    if layer:
        if layer not in names:
            sys.exit(f"layer {layer!r} not found; available: {names}")
        return layer
    cand = [n for n in names if re.fullmatch(r"national\d+", n, re.I)] or names
    return cand[0]


def year_cols(columns):
    return sorted([c for c in columns if re.fullmatch(r"CDL\d{4}", c)], key=lambda c: int(c[3:]))


def build_where(a):
    """SQL WHERE for the OpenFileGDB driver. FIPS codes are strings in the CSB schema."""
    w = []
    if a.state:
        w.append(f"STATEFIPS = '{str(a.state).zfill(2)}'")
    if getattr(a, "county", None):
        w.append(f"CNTYFIPS = '{str(a.county).zfill(5)}'")
    return " AND ".join(w) or None


def read(a, geometry=False, columns=None):
    import pyogrio
    layer = find_layer(a.gdb, a.layer)
    kw = dict(layer=layer, where=build_where(a), columns=columns, read_geometry=geometry)
    bbox = getattr(a, "bbox", None)
    if bbox:
        from pyproj import Transformer
        t = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
        x0, y0 = t.transform(bbox[0], bbox[1]); x1, y1 = t.transform(bbox[2], bbox[3])
        kw["bbox"] = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        kw["read_geometry"] = True
        geometry = True
    if geometry:
        import geopandas as gpd
        kw.pop("read_geometry", None)
        df = gpd.read_file(a.gdb, engine="pyogrio", **kw)
    else:
        df = pyogrio.read_dataframe(a.gdb, **kw)
    if df.empty:
        sys.exit("no rows matched the filter (check --state/--county are FIPS codes, e.g. 19 and 19015)")
    return df


def cmd_info(a):
    import pyogrio
    for n, g in pyogrio.list_layers(a.gdb):
        info = pyogrio.read_info(a.gdb, layer=n)
        print(f"layer {n!r}  geometry={g}  features={info['features']:,}  crs={info['crs']}")
        for f, d in zip(info["fields"], info["dtypes"]):
            print(f"   {f:15s} {d}")


def cmd_stats(a):
    ycols = year_cols(pyogrio_fields(a))
    df = read(a, columns=["CSBACRES"] + ycols)
    rows = []
    for c in ycols:
        s = df.groupby(c)["CSBACRES"].agg(["sum", "count"]).reset_index()
        s.columns = ["code", "acres", "polygons"]
        s["year"] = int(c[3:])
        rows.append(s)
    t = pd.concat(rows)
    t["crop"] = t["code"].map(name)
    t["hectares"] = (t["acres"] * AC_TO_HA).round(1)
    t["acres"] = t["acres"].round(1)
    print(f"{len(df):,} polygons, {df['CSBACRES'].sum():,.0f} acres in filter")
    for y, g in t.groupby("year"):
        print(f"\n== {y}: top {a.top} classes by area ==")
        print(g.sort_values("acres", ascending=False).head(a.top)[["code", "crop", "acres", "hectares", "polygons"]].to_string(index=False))
    if a.csv:
        t.sort_values(["year", "acres"], ascending=[True, False]).to_csv(a.csv, index=False)
        print("\nwrote", a.csv)


def pyogrio_fields(a):
    import pyogrio
    return list(pyogrio.read_info(a.gdb, layer=find_layer(a.gdb, a.layer))["fields"])


def cmd_rotation(a):
    ycols = year_cols(pyogrio_fields(a))
    df = read(a, columns=["CSBACRES"] + ycols)
    df["sequence"] = df[ycols].astype(str).agg(">".join, axis=1)
    g = df.groupby("sequence")["CSBACRES"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    g["share_%"] = (100 * g["sum"] / g["sum"].sum()).round(2)
    g["named"] = [">".join(name(x) or "?" for x in s.split(">")) for s in g.index]
    g.columns = ["acres", "polygons", "share_%", "named"]
    print(f"sequence order: {', '.join(c[3:] for c in ycols)}")
    print(g.head(a.top).round({"acres": 0}).to_string())
    # simple rotation flags
    corn, soy = "1", "5"
    flip = df[ycols].astype(str).apply(lambda r: all((r.iloc[i], r.iloc[i + 1]) in {(corn, soy), (soy, corn)} for i in range(len(r) - 1)), axis=1)
    print(f"\nstrict corn<->soy alternation every year: {df.loc[flip, 'CSBACRES'].sum():,.0f} acres "
          f"({100 * df.loc[flip, 'CSBACRES'].sum() / df['CSBACRES'].sum():.1f}%)")
    if a.csv:
        g.to_csv(a.csv); print("wrote", a.csv)


def cmd_export(a):
    gdf = read(a, geometry=True)
    ycols = year_cols(gdf.columns)
    if a.crops:                                    # keep polygons that grew any of these crops in any year
        gdf = gdf[gdf[ycols].isin(a.crops).any(axis=1)]
    if a.min_acres:
        gdf = gdf[gdf["CSBACRES"] >= a.min_acres]
    cent = gdf.geometry.centroid
    cent4326 = gpd_points(cent, gdf.crs)
    gdf = gdf.copy()
    gdf["centroid_lon"] = cent4326.x.round(6)
    gdf["centroid_lat"] = cent4326.y.round(6)
    base = Path(a.out)
    base.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_crs(4326).to_parquet(f"{base}.parquet")
    long = gdf.drop(columns="geometry").melt(
        id_vars=[c for c in gdf.columns if c not in ycols + ["geometry"]],
        value_vars=ycols, var_name="year", value_name="cdl_code")
    long["year"] = long["year"].str[3:].astype(int)
    long["crop"] = long["cdl_code"].map(name)
    keep = ["CSBID", "centroid_lat", "centroid_lon", "CSBACRES", "year", "cdl_code", "crop", "STATEFIPS", "CNTYFIPS", "CNTY"]
    long[[c for c in keep if c in long.columns]].sort_values(["CSBID", "year"]).to_csv(f"{base}_long.csv", index=False)
    if a.geojson:
        gdf.to_crs(4326).to_file(f"{base}.geojson", driver="GeoJSON")
    print(f"{len(gdf):,} fields -> {base}.parquet, {base}_long.csv" + (f", {base}.geojson" if a.geojson else ""))


def gpd_points(cent, crs):
    import geopandas as gpd
    return gpd.GeoSeries(cent, crs=crs).to_crs(4326)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    def common(s, bbox=False):
        s.add_argument("gdb", help="path to CSB*.gdb")
        s.add_argument("--layer")
        s.add_argument("--state", help="state FIPS, e.g. 19")
        s.add_argument("--county", help="county FIPS, e.g. 19015")
        if bbox:
            s.add_argument("--bbox", type=float, nargs=4, metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"))
    i = sp.add_parser("info"); i.add_argument("gdb"); i.set_defaults(fn=cmd_info)
    s = sp.add_parser("stats"); common(s); s.add_argument("--top", type=int, default=10); s.add_argument("--csv"); s.set_defaults(fn=cmd_stats)
    r = sp.add_parser("rotation"); common(r); r.add_argument("--top", type=int, default=15); r.add_argument("--csv"); r.set_defaults(fn=cmd_rotation)
    e = sp.add_parser("export"); common(e, bbox=True)
    e.add_argument("--out", required=True, help="output base name, no extension")
    e.add_argument("--crops", type=int, nargs="*", help="CDL codes; keep fields with any of them in any year")
    e.add_argument("--min-acres", type=float)
    e.add_argument("--geojson", action="store_true")
    e.set_defaults(fn=cmd_export)
    a = p.parse_args()
    if a.cmd in ("stats", "rotation") and not (a.state or a.county):
        print("warning: no --state/--county filter; this scans all ~16 M rows and needs several GB RAM", file=sys.stderr)
    a.fn(a)


if __name__ == "__main__":
    main()
