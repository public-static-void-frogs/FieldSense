# SMAP L3 SPL3SMP_E (enhanced radiometer soil moisture): column descriptions

Source: NSIDC DAAC, https://nsidc.org/data/spl3smp_e/versions/6 ; spec: https://nsidc.org/sites/default/files/d5629220smap20l3_sm_p_e20psd_version2050_final.pdf
Basis: `sources-descriptions.md` §6.

**Read this first**
- **Observed** (satellite retrieval) surface soil moisture, not a model analysis. Surface layer only; there is **no root-zone** soil moisture here.
- HDF5, daily composite, 9 km EASE-Grid 2.0, from 2015-03-31, version 6 on the checked page. The 9 km posting is not an independent 9 km microwave footprint.
- AM and PM retrievals live in **separate groups**. PM datasets may carry a `_pm` suffix, so do not assume identical HDF paths.
- Retrieval gaps (frozen ground, dense vegetation, water, RFI) are normal; do not fill them with zero.

## 1. Native variables, groups `Soil_Moisture_Retrieval_Data_AM` / `..._PM` (`[y,x]`)

| Variable | Type | Unit | Description |
|---|---|---|---|
| `latitude`, `longitude` | float | degrees | Cell centre coordinates. |
| `soil_moisture` | float | m³/m³ | Retrieved surface soil moisture. |
| `soil_moisture_error` | float | m³/m³ | Retrieval uncertainty. |
| `retrieval_qual_flag` | uint16 bitmask | – | Retrieval quality bits. Not a boolean. |
| `surface_flag` | uint16 bitmask | – | Surface conditions (water, freeze, etc.). Not a boolean. |
| `surface_temperature` | float | K | Surface temperature used in the retrieval. |
| `vegetation_water_content` | float | kg/m² | Vegetation water content. |
| `vegetation_opacity` | float | – | Vegetation opacity. |
| `soil_moisture_scah`, `soil_moisture_scav`, `soil_moisture_dca` | float? | m³/m³ | Alternative algorithm retrievals (single-channel H/V, dual-channel). |

Further possible: brightness temperatures, water/freeze fractions, grid indices, observation time. Check the version's specification.

## 2. Logical table `SoilMoistureObservation`

| Column | Type | Description |
|---|---|---|
| `date` | date | Composite day. |
| `orbit_pass` | enum | `AM` or `PM`. |
| `row`, `col` | int | EASE-Grid indices. |
| `location` | coordinates | Cell centre. |
| `moisture_m3_m3` | float? | `soil_moisture`. |
| `uncertainty_m3_m3` | float? | `soil_moisture_error`. |
| `retrieval_quality` | int | `retrieval_qual_flag` bits. |
| `surface_flags` | int | `surface_flag` bits. |

## 3. Notes
- Decode the flag bits per the version's specification before filtering; algorithm and bit meaning can change between versions.
- Missing retrieval is not zero moisture.
