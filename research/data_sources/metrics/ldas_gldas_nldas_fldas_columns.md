# GLDAS / NLDAS / FLDAS land data assimilation: column descriptions

Source: NASA LDAS, https://ldas.gsfc.nasa.gov ; https://ldas.gsfc.nasa.gov/fldas ; GLDAS output dictionary https://ldas.gsfc.nasa.gov/gldas/model-output ; NLDAS https://ldas.gsfc.nasa.gov/nldas/v2/models ; FLDAS https://ldas.gsfc.nasa.gov/fldas/specifications
Basis: `sources-descriptions.md` §8. These are **three families** with several models and versions; do not carry one resolution or variable list to all.

**Read this first**
- All are **land-model outputs** (forced by meteorology, with or without assimilation), not measurements.
- Variable suffixes: `inst` = instantaneous, `tavg` = time average, `acc` = accumulation over the interval. Check the collection before combining.
- Noah soil moisture is **water mass per area (kg/m²)** per layer, not volumetric moisture. To get m³/m³: `water_mass / (1000 × layer_thickness_m)`.

## 1. GLDAS (example collection `GLDAS_NOAH025_3H.2.1`: 0.25°, 3-hourly, NetCDF)

| Variable | Unit | Description |
|---|---|---|
| `SoilMoi0_10cm_inst` | kg/m² | Soil moisture, 0–10 cm. |
| `SoilMoi10_40cm_inst` | kg/m² | Soil moisture, 10–40 cm. |
| `SoilMoi40_100cm_inst` | kg/m² | Soil moisture, 40–100 cm. |
| `SoilMoi100_200cm_inst` | kg/m² | Soil moisture, 100–200 cm. |
| `SoilTMP0_10cm_inst` | K | Soil temperature, 0–10 cm. |
| `RootMoist_inst` | kg/m² | Root-zone soil moisture. |
| `Evap_tavg` | kg/m²/s | Evapotranspiration (time average). |
| `Qs_acc` | kg/m² | Storm surface runoff over the interval. |
| `Qsb_acc` | kg/m² | Baseflow/groundwater runoff over the interval. |
| `Rainf_f_tavg` | kg/m²/s | Rainfall rate. |
| `Tair_f_inst` | K | Air temperature. |
| `Qair_f_inst` | kg/kg | Specific humidity. |
| `Wind_f_inst` | m/s | Wind speed. |
| `Psurf_f_inst` | Pa | Surface pressure. |
| `SWdown_f_tavg`, `LWdown_f_tavg` | W/m² | Downward shortwave / longwave radiation. |
| `SWE_inst` | kg/m² | Snow water equivalent. |

Monthly GLDAS is a different collection with a different variable set.

## 2. NLDAS (North America, 1/8°, hourly, from 1979)

Separate forcing and Noah / Mosaic / VIC output products. The historical GRIB-1 stream stopped updating on 2024-08-01: use the current NetCDF collections. Native names differ by model and layer, so the table below is a **normalized** schema.

| Column | Type | Description |
|---|---|---|
| `timestamp` | datetime | Hour of the value. |
| `location` | coordinates | Cell centre. |
| `model` | enum | Noah, Mosaic or VIC. |
| `collection_version` | string | Collection and version. |
| `soil_layer_top_cm`, `soil_layer_bottom_cm` | float? | Layer depth limits. |
| `soil_water_kg_m2` | float? | Soil water in the layer. |
| `soil_temperature_k` | float? | Soil temperature. |
| `evapotranspiration` | float? | ET (unit from the collection). |
| `surface_runoff`, `baseflow` | float? | Runoff terms. |
| `snow_water_equivalent` | float? | SWE. |
| `units_by_variable` | map | Units per variable. |

## 3. FLDAS (NetCDF)

- Global Noah: 0.1°, from 1982, monthly and daily outputs depending on the collection.
- Central Asia: separate domain, 0.01°, daily.
- A forecast product exists: needs `issued_date`, `lead_month` and ensemble/model fields, and is not historical data.

| Column | Type | Description |
|---|---|---|
| `collection_id`, `model` | string | Collection and model. |
| `period_start`, `period_end` | datetime | Interval the value covers. |
| `location` | coordinates | Cell centre. |
| `soil_layer` | enum | 0–10 / 10–40 / 40–100 / 100–200 cm (Noah). |
| `soil_moisture`, `soil_moisture_units` | float?, string | Value and its unit (depends on the collection). |
| `evapotranspiration_rate`, `rainfall_rate`, `runoff` | float? | Fluxes (check units). |
| `air_temperature_k` | float? | Air temperature. |
| `is_preliminary` | boolean? | Optional; set from run metadata. |

## 4. Notes
- GLDAS/NLDAS/FLDAS soil water in kg/m² is not directly comparable with SMAP m³/m³.
- Fluxes are rates (per second); accumulations are totals for the interval.
