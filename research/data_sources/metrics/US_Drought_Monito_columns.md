# U.S. Drought Monitor dataset: column descriptions

Per-point weekly table (`csb_drought.py weekly`): one row per point per week

| Column | Type | Description |
|---|---|---|
| `CSBID` | string | Field ID from `csb_bounds` (or your `id` when `--points` is used). |
| `valid_date` | datetime64 | Date the map is valid for (the Tuesday in the file name). |
| `dm` | Int8 (nullable) | Drought class of the polygon containing the point's centroid: 0 = D0 … 4 = D4. **Null** = the centroid is in no drought polygon. If several polygons contain the point (nested maps), the highest value is used. |
| `category` | string | Label for `dm`: `D0`, `D1`, `D2`, `D3`, `D4`, or `None`. |
| `release_date_est` | datetime64 | **Estimate**, not from USDM: `valid_date` + 2 days (the Thursday release after a Tuesday valid date). Use it to avoid using information before it was public. Verify against the USDM timetable. |

Notes
- `None` / null means "no drought category here". It is also produced for points **outside USDM coverage** (outside the mapped US areas); the script cannot distinguish the two.
- With `--drop-none`, rows with null `dm` are not written. A missing (point, week) row then means "no drought or outside coverage", but also covers weeks whose map could not be loaded, so check the script's warning about missing weeks.
- Rows with `dm = 0` are not the same as `None`.
- Polygons are generalized regional boundaries, so a field near a boundary can be misclassified by a few kilometres.
- Source maps: shapefile attribute `DM` (integer 0–4) in the USA Contiguous Albers Equal Area projection (per USDM metadata). Points are reprojected to the file's CRS before testing.