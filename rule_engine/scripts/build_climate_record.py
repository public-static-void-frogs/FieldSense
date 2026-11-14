"""Build the long weather record: weekly gridMET statistics on a coarse grid, many years.

Field season summaries hold only the few seasons that were assembled per field. This record holds
weather alone, for every node of a regular grid over the contiguous USA, for as many years as
gridMET files are present (gridMET starts in 1979). The engine reads the node nearest to a field.

Input: yearly CONUS netCDF files <cache>/<var>_<year>.nc for tmmx, tmmn, pr and pet, from
http://thredds.northwestknowledge.net:8080/thredds/fileServer/MET/<var>/<var>_<year>.nc

Output under --out:
    grid.json                  origin, step and week layout of the grid
    _years/<year>.parquet      one row per node (kept so that more years can be added later)
    iy=<row>/*.parquet         the same rows grouped by grid row, which is what the engine reads

Weeks cover the whole year and line up with the field summaries: week = day of year // 7, so
week 13 starts on day 91 (1 April). A year has 53 weeks; the last one has one or two days.

    python rule_engine/scripts/build_climate_record.py \
        --cache data/local/usa_sample/cache/gridmet --out data/local/usa_sample/climate_record \
        --years 1996 2025
"""

import argparse
import json
from pathlib import Path

import numpy as np

STRIDE = 6  # every 6th gridMET cell: 0.25 degrees
WEEK0_DOY = 0
WEEKS = 53
VARIABLES = ("tmmx", "tmmn", "pr", "pet")
RYE_BASE_C = 4.4  # base temperature of the cereal rye growth sums


def _read(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(values[day, row, column] as float32 with NaN for missing, node latitudes, longitudes)."""
    import netCDF4

    with netCDF4.Dataset(path) as data:
        data.set_auto_maskandscale(False)
        var = data[next(v for v in data.variables if data[v].ndim == 3)]
        raw = var[:, ::STRIDE, ::STRIDE]
        values = raw.astype("float32") * float(getattr(var, "scale_factor", 1.0)) + float(
            getattr(var, "add_offset", 0.0)
        )
        fill = getattr(var, "_FillValue", None)
        if fill is not None:
            values[raw == fill] = np.nan
        return values, data["lat"][::STRIDE].astype(float), data["lon"][::STRIDE].astype(float)


def weekly_metrics(tmax, tmin, pr, eto) -> dict[str, np.ndarray]:
    """Daily arrays [day, node] in deg C and mm -> weekly arrays [node, week]."""
    days = tmax.shape[0]
    mean = (tmax + tmin) / 2
    daily = {
        "tmax_max": (tmax, np.max, "float32"),
        "tmin_min": (tmin, np.min, "float32"),
        "pr_mm": (pr, np.sum, "float32"),
        "eto_mm": (eto, np.sum, "float32"),
        "gdd0": (np.maximum(mean, 0), np.sum, "float32"),
        "gdd44": (np.maximum(mean - RYE_BASE_C, 0), np.sum, "float32"),
        "tmax_ge35_days": (tmax >= 35, np.sum, "int16"),
        "tmax_ge30_days": (tmax >= 30, np.sum, "int16"),
        "tmin_le0_days": (tmin <= 0, np.sum, "int16"),
        "tmin_lem2_days": (tmin <= -2, np.sum, "int16"),
        "pr_ge25_days": (pr >= 25, np.sum, "int16"),
    }
    out = {
        name: np.full((tmax.shape[1], WEEKS), np.nan if kind == "float32" else 0, kind)
        for name, (_, _, kind) in daily.items()
    }
    out["obs_days"] = np.zeros((tmax.shape[1], WEEKS), "int16")
    for week in range(WEEKS):
        # day of year d sits at index d - 1; the week holds days 7 * week .. 7 * week + 6
        start, end = max(0, 7 * week - 1 + WEEK0_DOY), min(days, 7 * week + 6 + WEEK0_DOY)
        if start >= end:
            continue
        for name, (values, aggregate, _) in daily.items():
            out[name][:, week] = aggregate(values[start:end], axis=0)
        out["obs_days"][:, week] = end - start
    return out


def build_year(cache: Path, year: int, target: Path) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq

    arrays = {}
    for name in VARIABLES:
        arrays[name], lats, lons = _read(cache / f"{name}_{year}.nc")
    days = min(a.shape[0] for a in arrays.values())
    stack = np.stack([arrays[name][:days] for name in VARIABLES])
    valid = np.isfinite(stack).all(axis=(0, 1))  # nodes with every variable on every day
    iy, ix = np.nonzero(valid)
    tmax, tmin, pr, eto = (stack[i][:, valid] for i in range(len(VARIABLES)))
    metrics = weekly_metrics(tmax - 273.15, tmin - 273.15, pr, eto)
    columns = {
        "iy": pa.array(iy.astype("int16")),
        "ix": pa.array(ix.astype("int16")),
        "lat": pa.array(lats[iy].round(4)),
        "lon": pa.array(lons[ix].round(4)),
        "year": pa.array(np.full(len(iy), year, "int16")),
    }
    for name, values in metrics.items():
        flat = pa.array(np.ascontiguousarray(values).reshape(-1))
        columns[name] = pa.FixedSizeListArray.from_arrays(flat, WEEKS)
    pq.write_table(pa.table(columns), target, compression="zstd")
    print(f"{year}: {days} days, {len(iy):,} nodes -> {target}", flush=True)
    return {
        "lat0": float(lats[0]),
        "lon0": float(lons[0]),
        "lat_step": float(lats[1] - lats[0]),
        "lon_step": float(lons[1] - lons[0]),
        "rows": len(lats),
        "columns": len(lons),
    }


def main() -> None:
    import duckdb

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cache", required=True, type=Path, help="folder of gridMET netCDF files")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--years", type=int, nargs=2, required=True, metavar=("FIRST", "LAST"))
    args = parser.parse_args()
    years_dir = args.out / "_years"
    years_dir.mkdir(parents=True, exist_ok=True)
    grid = None
    for year in range(args.years[0], args.years[1] + 1):
        target = years_dir / f"{year}.parquet"
        if target.exists():
            continue
        if not all((args.cache / f"{name}_{year}.nc").exists() for name in VARIABLES):
            print(f"{year}: gridMET files missing, skipped", flush=True)
            continue
        grid = build_year(args.cache, year, target)
    built = sorted(int(path.stem) for path in years_dir.glob("*.parquet"))
    if not built:
        raise SystemExit("no years built")
    for old in args.out.glob("iy=*/*.parquet"):
        old.unlink()
    duckdb.connect().execute(
        f"COPY (SELECT * FROM read_parquet('{years_dir}/*.parquet') ORDER BY iy, ix, year) "
        f"TO '{args.out}' (FORMAT PARQUET, PARTITION_BY (iy), OVERWRITE_OR_IGNORE, "
        "COMPRESSION ZSTD)"
    )
    grid_file = args.out / "grid.json"
    if grid is None:
        grid = {k: v for k, v in json.loads(grid_file.read_text()).items() if k != "years"}
    grid.update(
        week0_doy=WEEK0_DOY,
        weeks=WEEKS,
        years=built,
        source="gridmet",
    )
    grid_file.write_text(json.dumps(grid, indent=2) + "\n")
    print(f"{len(built)} years ({built[0]}-{built[-1]}) -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
