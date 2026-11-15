"""Build steps for the weather-cell sample (sample_weather_cells.py), one chunk of counties at a time.

    python rule_engine/planner/scripts/build_cell_chunks.py chunks --root data/local/usa_sample_v3 \
        --cdl data/local/usa_sample_v2/cdl_history_all.parquet
    python rule_engine/planner/scripts/build_cell_chunks.py gridmet --root data/local/usa_sample_v3 \
        --cache <dir with tmmx_<year>.nc ...> [<another dir>] --years 1981 2025
    python rule_engine/planner/scripts/build_cell_chunks.py merge --root data/local/usa_sample_v3

`chunks` writes <root>/chunks/<n>/fields.csv and cdl_history.parquet, the layout that
build_history_summaries.py reads as --sample. `gridmet` reads each yearly gridMET file once and
writes <root>/chunks/<n>/work/gridmet/<year>.parquet for every chunk. `merge` moves the chunks'
season summaries to <root>/season_summary/<year>/<county>.parquet (a county is in one chunk).
"""

import argparse
import shutil
from pathlib import Path

import duckdb

TYPES = "types={'CSBID': 'VARCHAR', 'STATEFIPS': 'VARCHAR', 'CNTYFIPS': 'VARCHAR'}"
# file prefix -> (output column, offset added after scaling)
VARIABLES = {
    "tmmx": ("gridmet_tmax_c", -273.15),
    "tmmn": ("gridmet_tmin_c", -273.15),
    "pr": ("gridmet_pr_mm", 0.0),
    "pet": ("gridmet_eto_grass_mm", 0.0),
}


def chunks(args) -> None:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW f AS SELECT * FROM read_csv('{args.root}/fields.csv', {TYPES})")
    for (chunk,) in con.execute("SELECT DISTINCT chunk FROM f ORDER BY chunk").fetchall():
        out = args.root / "chunks" / f"{chunk:02d}"
        out.mkdir(parents=True, exist_ok=True)
        con.execute(f"""
            COPY (SELECT * EXCLUDE (chunk) FROM f WHERE chunk = {chunk} ORDER BY CSBID)
            TO '{out}/fields.csv' (HEADER)
        """)
        con.execute(f"""
            COPY (SELECT c.*, f.CSBACRES, f.STATEFIPS, f.CNTYFIPS
                  FROM read_parquet('{args.cdl}') c JOIN f USING (CSBID)
                  WHERE f.chunk = {chunk} ORDER BY CSBID)
            TO '{out}/cdl_history.parquet' (FORMAT PARQUET)
        """)
        print(f"chunk {chunk:02d}: {out}", flush=True)


def gridmet(args) -> None:
    import netCDF4
    import numpy as np
    import pandas as pd

    fields = pd.read_csv(args.root / "fields.csv", dtype={"CSBID": str})
    lon, lat = fields["centroid_lon"].to_numpy(), fields["centroid_lat"].to_numpy()
    groups = {chunk: rows.index.to_numpy() for chunk, rows in fields.groupby("chunk")}

    def find(prefix: str, year: int) -> Path:
        for cache in args.cache:
            if (cache / f"{prefix}_{year}.nc").exists():
                return cache / f"{prefix}_{year}.nc"
        raise FileNotFoundError(f"{prefix}_{year}.nc")

    for year in range(args.years[0], args.years[-1] + 1):
        last = args.root / "chunks" / f"{max(groups):02d}" / "work" / "gridmet" / f"{year}.parquet"
        if last.exists():
            continue
        columns, inside, days = {}, None, None
        for prefix, (column, offset) in VARIABLES.items():
            with netCDF4.Dataset(find(prefix, year)) as data:
                data.set_auto_maskandscale(False)
                lats, lons = data["lat"][:], data["lon"][:]
                # the grid is regular, so the nearest cell is a rounded offset
                iy = np.clip(np.rint((lat - lats[0]) / (lats[1] - lats[0])), 0, len(lats) - 1)
                ix = np.clip(np.rint((lon - lons[0]) / (lons[1] - lons[0])), 0, len(lons) - 1)
                iy, ix = iy.astype(int), ix.astype(int)
                inside = (np.abs(lats[iy] - lat) < 0.05) & (np.abs(lons[ix] - lon) < 0.05)
                var = data[next(v for v in data.variables if data[v].ndim == 3)]
                raw = var[:][:, iy, ix]
                values = raw.astype("float32") * float(getattr(var, "scale_factor", 1.0))
                values += float(getattr(var, "add_offset", 0.0)) + offset
                fill = getattr(var, "_FillValue", None)
                if fill is not None:
                    values[raw == fill] = np.nan
            days = values.shape[0] if days is None else min(days, values.shape[0])
            columns[column] = values
        written = 0
        for chunk, index in groups.items():
            keep = index[inside[index]]
            frame = pd.DataFrame(
                {
                    "CSBID": np.tile(fields["CSBID"].to_numpy()[keep], days),
                    "year": year,
                    "doy": np.repeat(np.arange(1, days + 1, dtype="int16"), len(keep)),
                    **{c: v[:days, keep].reshape(-1).round(2) for c, v in columns.items()},
                }
            ).dropna(subset=["gridmet_tmax_c"])
            out = args.root / "chunks" / f"{chunk:02d}" / "work" / "gridmet"
            out.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(out / f"{year}.parquet.tmp", index=False)
            (out / f"{year}.parquet.tmp").rename(out / f"{year}.parquet")
            written += frame["CSBID"].nunique()
        print(f"{year}: {days} days, {written:,} of {len(fields):,} fields", flush=True)


def merge(args) -> None:
    moved = 0
    for source in sorted(args.root.glob("chunks/*/work/season_summary/*/*.parquet")):
        target = args.root / "season_summary" / source.parent.name
        target.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), target / source.name)
        moved += 1
    print(f"moved {moved:,} county files to {args.root}/season_summary")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    steps = parser.add_subparsers(dest="step", required=True)
    step = steps.add_parser("chunks")
    step.add_argument("--root", required=True, type=Path)
    step.add_argument("--cdl", required=True)
    step.set_defaults(run=chunks)
    step = steps.add_parser("gridmet")
    step.add_argument("--root", required=True, type=Path)
    step.add_argument("--cache", required=True, type=Path, nargs="+")
    step.add_argument("--years", required=True, type=int, nargs=2)
    step.set_defaults(run=gridmet)
    step = steps.add_parser("merge")
    step.add_argument("--root", required=True, type=Path)
    step.set_defaults(run=merge)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
