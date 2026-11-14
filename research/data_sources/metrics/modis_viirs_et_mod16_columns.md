# MODIS / VIIRS evapotranspiration (MOD16A2GF, VNP16): column descriptions

Source: LP DAAC, https://lpdaac.usgs.gov/product_search/ ; user guide https://www.earthdata.nasa.gov/s3fs-public/2025-04/MOD16_User_Guide_V61.pdf
Basis: `sources-descriptions.md` §10.

**Read this first**
- `MOD16A2GF.061`: HDF-EOS2/HDF4, 500 m, sinusoidal tiles, **8-day composites**, gap-filled at end of year. `VNP16A2`, `VNP16A2GF`, `VNP16A3GF` are separate VIIRS products (500 m, 8-day, HDF5): verify their layer names and scales.
- Model-based ET, not a field measurement.
- Remove fill/reserved codes **before** applying the scale factor.
- The last composite of a year is shorter than 8 days: for a daily average divide by the real number of days.
- Earth Engine uses shorter names (`ET`, `LE`, `PET`, `PLE`, `ET_QC`); these are not the native SDS names.

## 1. Native layers `[y,x]` (MOD16A2GF)

| Layer | Type | Scale / unit | Description |
|---|---|---|---|
| `ET_500m` | int16 | × 0.1 → kg/m² per composite | Total evapotranspiration over the composite. |
| `LE_500m` | int16 | × 10000 → J/m²/day | Average latent heat flux. |
| `PET_500m` | int16 | × 0.1 → kg/m² per composite | Potential evapotranspiration. |
| `PLE_500m` | int16 | × 10000 → J/m²/day | Potential latent heat flux. |
| `ET_QC_500m` | uint8 | bitmask | Quality control. |

`1 kg/m² = 1 mm` of water depth. ET and PET are sums over the composite; LE and PLE are mean daily energy fluxes.

## 2. Logical table `EvapotranspirationComposite`

| Column | Type | Description |
|---|---|---|
| `product_id`, `version` | string | e.g. `MOD16A2GF`, `061`. |
| `tile_id` | string | Sinusoidal tile (e.g. h10v04). |
| `period_start`, `period_end` | date | Composite period. |
| `row`, `col` | int | Pixel indices. |
| `et_mm` | float? | ET over the composite. |
| `potential_et_mm` | float? | PET over the composite. |
| `latent_heat_j_m2_day` | float? | LE. |
| `potential_latent_heat_j_m2_day` | float? | PLE. |
| `qc` | int | `ET_QC_500m` bits. |
