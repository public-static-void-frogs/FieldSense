# GPM IMERG dataset: column descriptions

Produced by `csb_imerg.py`. Source: GPM IMERG Final Precipitation L3 1 day 0.1° × 0.1° V07 (`GPM_3IMERGDF`), NASA GES DISC.
Collection page: https://www.earthdata.nasa.gov/data/catalog/ges-disc-gpm-3imergdf-07 , DOI: https://doi.org/10.5067/GPM/IMERGDF/DAY/07

**Read this first**
- One row of `imerg_daily.parquet` = one **0.1° grid cell** (about 10 km) and one **day**. It is a satellite-based estimate for the cell, not a gauge measurement at the field. Fields in the same cell share the same values.
- The daily product is derived by NASA from the half-hourly Final run. Do not rebuild daily totals by summing half-hourly rates yourself.
- Use one stream (Final / Late / Early) and one version for a consistent series. This dataset uses Final V07 unless `--stream` was changed.
- Final Daily has a latency of roughly 3.5 months, so recent days are not available yet.
- Cells with a zero observation count have the fill value in the source file; here they are NaN.

## 1. `imerg_daily.parquet`: one row per cell per day

| Column | Type | Description |
|---|---|---|
| `cell_id` | string | Grid cell identifier, `"<lat>_<lon>"` of the cell centre in degrees, e.g. `+33.35_-98.75`. Join key to `field_cell_map.parquet` and `cells.parquet`. |
| `date` | datetime64 | The day the daily file covers (taken from the file name `IMERG.YYYYMMDD`). |
| `precipitation` | float32 | Daily mean precipitation rate, **mm/day** (the 24-hour mean rate, which for a daily product equals the daily accumulation in mm). Main variable. |
| `randomError` | float32 | Estimate of the random error of `precipitation`, mm/day. Larger values mean less reliable estimates, typically for light or sparse rain. |
| `probabilityLiquidPrecipitation` | float32 | Probability that precipitation is liquid (rain, not snow), %. Use it to judge snow-affected cells. |
| `precipitation_cnt` | float32 | Count of half-hourly values that contributed to `precipitation` that day (a count, up to 48). |
| `precipitation_cnt_cond` | float32 | Count variant for the conditional rate (half-hours with precipitation, per the GES DISC variable list; confirm in the product documentation before relying on its exact definition). |

Optional columns, present only if you passed them in `--variables`:

| Column | Description |
|---|---|
| `MWprecipitation` | Precipitation from passive microwave observations only, mm/day. |
| `MWprecipitation_cnt`, `MWprecipitation_cnt_cond` | Counts for the microwave estimate. |
| `randomError_cnt` | Count for the random error estimate. |

Variables requested but missing from a file are skipped (the script prints a warning). Time dimension variables of the source file (`time`, `time_bnds`) are not stored; `date` replaces them.

## 2. `field_cell_map.parquet`: one row per field

| Column | Type | Description |
|---|---|---|
| `CSBID` | string | Crop Sequence Boundaries polygon ID (chars 1–2 state FIPS, 3–6 year window, last 9 sequence number). |
| `cell_id` | string | IMERG cell containing the field's centroid. |

## 3. `cells.parquet`: one row per cell

| Column | Type | Description |
|---|---|---|
| `cell_id` | string | Cell identifier. |
| `cell_lat`, `cell_lon` | float | Cell centre, degrees (WGS84). |
| `i`, `j` | integer | Zero-based row (latitude) and column (longitude) index in the 1800 × 3600 grid: `lat = -89.95 + 0.1·i`, `lon = -179.95 + 0.1·j`. |
| `n_fields` | integer | Number of selected fields in the cell. |

## 4. Getting weather per field

```python
m = pd.read_parquet("imerg/field_cell_map.parquet")
w = pd.read_parquet("imerg/imerg_daily.parquet")
fw = m[m.CSBID == "<id>"].merge(w, on="cell_id")      # one field x days
```

## 5. Notes

- The grid layout (1800 × 3600, centres offset by 0.05°) is an assumption the script checks against each file and stops on mismatch.
- Missing days (not published yet or not downloaded) simply have no rows; re-running `extract` retries them.
- Derived values such as rainy-day counts or dry spells are not in the data; compute them from `precipitation` (choose your own threshold, for example 1 mm/day).
