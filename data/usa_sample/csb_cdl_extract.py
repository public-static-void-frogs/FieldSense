"""From the national CSB geodatabase: (1) CSBID + CDL<year> attributes for a list of CSBIDs,
(2) field counts and acres per state, year and CDL code over every field (2021-2025).
usage: python -I csb_cdl_extract.py <gdb path> <ids csv with CSBID column> <out parquet> <state stats parquet>"""

import sys

import pandas as pd
import pyogrio

gdb, ids_path, out, stats_out = sys.argv[1:5]
ids = set(pd.read_csv(ids_path, dtype=str)["CSBID"])
layers = pyogrio.list_layers(gdb)
print("layers", layers.tolist(), flush=True)
parts, stats = [], []
for layer in layers[:, 0]:
    info = pyogrio.read_info(gdb, layer=layer)
    fields = [
        f
        for f in info["fields"]
        if f == "CSBID"
        or f.startswith("CDL")
        or f in ("CSBACRES", "STATEFIPS", "CNTYFIPS")
    ]
    print(layer, info["features"], fields, flush=True)
    frame = pyogrio.read_arrow(gdb, layer=layer, columns=fields, read_geometry=False)[
        1
    ].to_pandas()
    frame["CSBID"] = frame["CSBID"].astype(str)
    parts.append(frame[frame["CSBID"].isin(ids)])
    print("  matched", len(parts[-1]), flush=True)
    for year in range(2021, 2026):
        column = f"CDL{year}"
        if column in frame:
            g = (
                frame.groupby(["STATEFIPS", column], dropna=False)
                .agg(fields=("CSBID", "size"), acres=("CSBACRES", "sum"))
                .reset_index()
            )
            g = g.rename(columns={column: "cdl"})
            g["year"] = year
            stats.append(g)
result = pd.concat(parts, ignore_index=True)
result.to_parquet(out, index=False)
pd.concat(stats, ignore_index=True).to_parquet(stats_out, index=False)
print("wrote", out, len(result), "of", len(ids), flush=True)
