"""Daily gridMET weather at each sampled field point (nearest 4 km cell), one parquet per year.

Reads the yearly CONUS netCDF files (tmmx, tmmn, pr, pet) already downloaded from
http://thredds.northwestknowledge.net:8080/thredds/fileServer/MET/<var>/<var>_<year>.nc

    python data/usa_sample/gridmet.py --fields data/local/usa_sample/fields.csv \
        --cache data/local/usa_sample/cache/gridmet --out data/local/usa_sample/gridmet \
        --years 2021 2022 2023 2024 2025

Output columns: CSBID, year, doy, gridmet_tmax_c, gridmet_tmin_c, gridmet_pr_mm,
gridmet_eto_grass_mm. Points outside the grid (none expected in CONUS) are dropped.
"""

import argparse
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd

# file prefix -> (output column, offset added after scaling)
VARIABLES = {
    "tmmx": ("gridmet_tmax_c", -273.15),
    "tmmn": ("gridmet_tmin_c", -273.15),
    "pr": ("gridmet_pr_mm", 0.0),
    "pet": ("gridmet_eto_grass_mm", 0.0),
}


def sample(
    path: Path, lon: np.ndarray, lat: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """(values[day, point] as float32 with NaN for missing, in-grid mask[point])."""
    with netCDF4.Dataset(path) as data:
        data.set_auto_maskandscale(False)
        lats, lons = data["lat"][:], data["lon"][:]
        iy = np.abs(lats[:, None] - lat[None, :]).argmin(axis=0)
        ix = np.abs(lons[:, None] - lon[None, :]).argmin(axis=0)
        inside = (np.abs(lats[iy] - lat) < 0.05) & (np.abs(lons[ix] - lon) < 0.05)
        name = next(v for v in data.variables if data[v].ndim == 3)
        var = data[name]
        raw = var[:][:, iy, ix]
        fill = getattr(var, "_FillValue", None)
        values = raw.astype("float32") * float(
            getattr(var, "scale_factor", 1.0)
        ) + float(getattr(var, "add_offset", 0.0))
        if fill is not None:
            values[raw == fill] = np.nan
    return values, inside


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fields", required=True)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    fields = pd.read_csv(args.fields, dtype={"CSBID": str})
    lon, lat = fields["centroid_lon"].to_numpy(), fields["centroid_lat"].to_numpy()
    for year in args.years:
        columns, inside, days = {}, None, None
        for prefix, (column, offset) in VARIABLES.items():
            values, inside = sample(args.cache / f"{prefix}_{year}.nc", lon, lat)
            days = values.shape[0] if days is None else min(days, values.shape[0])
            columns[column] = values + offset
        frame = pd.DataFrame(
            {
                "CSBID": np.tile(fields["CSBID"].to_numpy(), days),
                "year": year,
                "doy": np.repeat(np.arange(1, days + 1, dtype="int16"), len(fields)),
                **{c: v[:days].reshape(-1).round(2) for c, v in columns.items()},
            }
        )
        frame = frame[np.tile(inside, days)].dropna(subset=["gridmet_tmax_c"])
        frame.to_parquet(args.out / f"{year}.parquet", index=False)
        print(
            f"{year}: {days} days, {frame['CSBID'].nunique():,} fields, "
            f"tmax {frame['gridmet_tmax_c'].min():.1f}..{frame['gridmet_tmax_c'].max():.1f} C, "
            f"mean annual pr {frame['gridmet_pr_mm'].sum() / frame['CSBID'].nunique():.0f} mm",
            flush=True,
        )


if __name__ == "__main__":
    main()
