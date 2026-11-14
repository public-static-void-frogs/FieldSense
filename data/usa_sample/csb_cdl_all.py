"""CDL crop history of every field of the national CSB geodatabase, as one lookup table.

    python -I csb_cdl_all.py <gdb path> <out parquet>

Writes CSBID (15 characters) and CDL<year> (small integers) sorted by CSBID in small row groups,
so one field is found by reading a single row group. CDL labels are satellite estimates.
"""

import sys

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pyogrio

gdb, out = sys.argv[1:3]
tables = []
for layer in pyogrio.list_layers(gdb)[:, 0]:
    info = pyogrio.read_info(gdb, layer=layer)
    columns = [f for f in info["fields"] if f == "CSBID" or f.startswith("CDL")]
    table = pyogrio.read_arrow(gdb, layer=layer, columns=columns, read_geometry=False)[1]
    table = pa.table(
        {
            name: table[name].cast(pa.string())
            if name == "CSBID"
            else pc.cast(table[name], pa.int16(), safe=False)
            for name in sorted(columns, key=lambda n: (n != "CSBID", n))
        }
    )
    print(layer, table.num_rows, table.column_names, flush=True)
    tables.append(table)
table = pa.concat_tables(tables, promote_options="default").sort_by("CSBID")
pq.write_table(table, out, row_group_size=20_000, compression="zstd")
print("wrote", out, table.num_rows, flush=True)
