# NASA Space Apps 2026: Data Source Guide

Prepared 18 Oct 2026 for two challenges (updated 23 Oct 2026: added section 2E for soil-depletion reconstruction and corrected rows 1, 5–7, 9, 12, 15, 17, 19 and 22; updated 26 Oct 2026: section 2A rewritten from [`weather_climate.md`](weather_climate.md), which adds sources #57–126, and row 47 corrected):
1. **Harmonization of MODIS and VIIRS Hot Spots**
2. **Field Shift: Adapting Farms with NASA Data**

**Read this first**
- The Space Apps challenge pages block automated access, so I could not read the official briefs. Everything below is built from the challenge titles, NASA/Earthdata documentation and search results. Check each list against the official "Resources" section on the challenge pages.
- **Sizes are rough order-of-magnitude estimates**, mostly from my own knowledge of product structure. They are not taken from catalog listings. Verify before planning a bulk download.
- Almost every NASA archive below needs a free **Earthdata Login** account: https://urs.earthdata.nasa.gov
- Priority: ★★★ = start here, ★★ = very useful, ★ = nice to have. Non-NASA sources are marked **(non-NASA)**.

---

## Part 1. Harmonization of MODIS and VIIRS Hot Spots

### Context that shapes the data choice
- **FIRMS** distributes active fire detections from MODIS (about 1 km pixels) and VIIRS (375 m pixels), and as of the sources I found also Landsat (30 m). MODIS Collection 6.1 runs from Nov 2000 to present. VIIRS S-NPP 375 m runs from Jan 2012, NOAA-20 from Apr 2018, and NOAA-21 from Jan 2024.
- **Overlap of MODIS and VIIRS is 2012 to 2026.** That makes it the natural window for calibrating one sensor against the other.
- **Orbit drift matters.** Terra and Aqua stopped orbit maintenance. Aqua's equatorial crossing time was projected to reach roughly 15:30 by August 2026, so the afternoon sampling of MODIS changed over the years. Detection counts and times are therefore not stationary.
- **End of mission.** NASA planning documents projected Aqua instrument shutdown on 26 Aug 2026, with Terra expected to run to roughly late 2026. I could not confirm what has actually happened since, so check the Aqua and Terra status pages before assuming 2026 data are complete.
- **Differences to harmonize:** pixel size (1 km vs 375 m, and pixel growth toward the scan edge), overpass times, detection thresholds and confidence schemes, and FRP definitions. MODIS confidence is numeric (0 to 100), while VIIRS 375 m confidence is categorical (low, nominal, high).

### 1A. Core fire detection data

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 1 | **FIRMS Archive Download** (MODIS C6.1, VIIRS S-NPP/NOAA-20/NOAA-21, Landsat) | https://firms.modaps.eosdis.nasa.gov/download/ | Point detections (lat/lon, brightness temps, FRP, confidence, day/night) by area and date, as CSV, Shapefile or JSON. Standard-quality data replace NRT data after a lag of a few months. | CSV for a country/year: MB to a few hundred MB. Global MODIS ~0.3 to 0.5 GB/yr; global VIIRS 375 m ~2 to 5 GB/yr (my estimate) | Main dataset. Build matched detection pairs, compare counts and FRP, derive conversion or harmonization factors | ★★★ |
| 2 | **FIRMS API** (Area, Country, Data-availability endpoints) | https://firms.modaps.eosdis.nasa.gov/api/ (key: https://firms.modaps.eosdis.nasa.gov/api/map_key/) | REST access to the same detections in CSV. Free MAP_KEY. Documented limit of 5,000 transactions per 10 minutes. Returns CSV only. The per-request day range is capped (documented as 1 to 5 days for the near-real-time area endpoint), so use the Archive Download for long histories. | KB to MB per call | Live demos, dashboards, apps that update automatically | ★★★ |
| 3 | **FIRMS text-file archive (LANCE)** | https://nrt3.modaps.eosdis.nasa.gov/archive/FIRMS (Earthdata Login required) | Daily global and regional text files of MODIS and VIIRS active fire | ~1 to 10 MB/day for global files | Scripted bulk download of NRT data | ★★ |
| 4 | **FIRMS FAQ and user guides** | https://www.earthdata.nasa.gov/data/tools/firms/faq | Official explanation of the NRT vs standard difference, attribute definitions, geolocation accuracy, and why MODIS and VIIRS differ | Docs only | Methodology section, attribute mapping | ★★★ |
| 5 | **MODIS Active Fire L2: MOD14 (Terra) / MYD14 (Aqua), and MCD14ML** | https://search.earthdata.nasa.gov/search?q=MOD14 (also MYD14, MCD14ML) via LAADS DAAC: https://ladsweb.modaps.eosdis.nasa.gov | Swath-level fire mask and detection tables. Source of the FIRMS points, with per-granule detail such as the fire mask, FRP and ambient-pixel statistics. | ~1 to 3 MB per 5-min granule. Daily global ~0.5 to 1 GB per sensor. Full record: multiple TB | Pixel-level, footprint-aware comparison with VIIRS. Study scan-angle effects | ★★ |
| 6 | **VIIRS 375 m Active Fire L2: VNP14IMG (S-NPP), VJ114IMG (NOAA-20), VJ214IMG (NOAA-21)** | https://search.earthdata.nasa.gov/search?q=VNP14IMG | Swath-level 375 m I-band fire detections. 750 m M-band VNP14 is also available. | A few MB per granule. Global daily ~1 to 2 GB per satellite. Full record: multiple TB | Same as above for VIIRS. Aggregate 375 m detections to a MODIS 1 km footprint | ★★ |
| 7 | **MODIS/VIIRS gridded fire products: MOD14A1/MYD14A1, VNP14A1** | https://search.earthdata.nasa.gov/search?q=MOD14A1 | Daily 1 km tiled (sinusoidal) fire masks and max FRP | ~1 to 2 MB per tile-day. Global year of tiles ~hundreds of GB | Gridded comparison without handling swaths, and easy rasterization | ★★ |

### 1B. Inputs for pixel-level and radiometric harmonization

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 8 | **MODIS L1B radiances + geolocation (MOD021KM/MYD021KM, MOD03/MYD03)** | https://ladsweb.modaps.eosdis.nasa.gov | Calibrated radiances (including 4 µm and 11 µm fire bands) | ~100 to 400 MB per granule. Daily global: tens of GB per sensor | Compare band radiances directly to see whether differences arise from the sensor or the algorithm. Use only for small regions or case studies | ★ |
| 9 | **VIIRS L1B (VNP02IMG, VNP02MOD, VNP03IMG / VJ1 equivalents)** | https://ladsweb.modaps.eosdis.nasa.gov | VIIRS I-band (375 m) and M-band (750 m) radiances and geolocation | ~100 to 500 MB per granule | Same as above | ★ |
| 10 | **Fire product algorithm docs (UMD MODIS/VIIRS fire team)** | https://modis-fire.umd.edu | Algorithm theoretical basis, user guides, validation papers. User guides are linked from FIRMS FAQ too. | Docs only | Explain thresholds, confidence logic, differences to be corrected | ★★★ |
| 11 | **MODIS Land team news and collection status** | https://modis-land.gsfc.nasa.gov/news.html | Orbit drift information, collection (C6.1/C7) status | Docs only | Handling of data after orbit drift | ★★ |

### 1C. Validation, burned area and masks

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 12 | **MODIS burned area MCD64A1 / VIIRS burned area VNP64A1** | https://search.earthdata.nasa.gov/search?q=MCD64A1 (VNP64A1 via UMD, see FIRMS archive page: https://firms.modaps.eosdis.nasa.gov/download/) | Monthly 500 m burned area. The VIIRS version keeps the MODIS grid for compatibility. | ~Tens of GB per global year. Full record ~100+ GB | Independent proxy of "true" fire extent to check which sensor's hot spots match burned scars | ★★ |
| 13 | **Landsat 8/9 and Sentinel-2 active fire / imagery, plus HLS** | HLS: https://www.earthdata.nasa.gov/data/projects/hls ; Landsat/Sentinel-2 via https://earthexplorer.usgs.gov | 30 m reference imagery and fire detections (Landsat 30 m fire is in FIRMS). HLS gives 30 m analysis-ready reflectance every few days. | HLS ~100 to 200 MB per tile-date. Use regional subsets | High-resolution "truth" for individual fire events | ★★ |
| 14 | **Land cover MCD12Q1 (MODIS)** | https://search.earthdata.nasa.gov/search?q=MCD12Q1 | Annual 500 m land cover | A few GB per year globally | Stratify differences by land type (forest, crop, grass) and flag false alarms | ★★ |
| 15 | **Persistent heat sources / gas flaring: VIIRS Nightfire (Earth Observation Group, Colorado School of Mines)** **(non-NASA)** | https://eogdata.mines.edu/products/vnf/ | Nightly detections of industrial and flare heat sources | MB to low GB per year for a region | Mask non-vegetation fires and industrial hot spots | ★ |

### 1D. Geostationary and other-agency context data

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 16 | **GOES-R ABI Fire (FDC) on AWS** **(non-NASA: NOAA)** | https://registry.opendata.aws/noaa-goes/ | Geostationary fire detections every 5 to 15 min over the Americas | ~Tens of MB/day per region | Fill gaps between polar overpasses and compare diurnal fire cycle | ★ |
| 17 | **Himawari AHI** **(non-NASA: JMA/NOAA)** | https://registry.opendata.aws/noaa-himawari/ | Geostationary imagery for Asia-Pacific | Large (GB/day) | Same, for Asia-Pacific | ★ |
| 18 | **Sentinel-3 SLSTR active fire and EFFIS** **(non-NASA: ESA/Copernicus)** | https://dataspace.copernicus.eu ; https://effis.jrc.ec.europa.eu | Independent fire detections and European burned-area and perimeter products | MB to GB regionally | Third-sensor cross-check and a morning-orbit option now that Terra is ending | ★ |
| 19 | **US wildfire perimeters (NIFC/WFIGS)** **(non-NASA: US government)** | https://data-nifc.opendata.arcgis.com | Official incident perimeters | MB | Ground-truth footprints for US case studies | ★★ |

### Suggested starter stack for Challenge 1
1. FIRMS Archive Download (MODIS C6.1 + VIIRS S-NPP/NOAA-20) for 2–3 regions, 2018 to 2025 (a few hundred MB total).
2. FIRMS FAQ and the UMD fire docs to interpret attributes.
3. Burned area (MCD64A1) and land cover (MCD12Q1) for validation and stratification.
4. HLS or Landsat imagery for a handful of well-known fires as case studies.
5. Optionally GOES or Sentinel-3 for a third reference.

---

## Part 2. Field Shift: Adapting Farms with NASA Data

The title and event coverage describe this as a climate-resilient agriculture challenge. The list below is built around the usual building blocks: **weather, water (soil moisture, rain, groundwater), plant condition, and future climate**.

### 2A. Weather and climate (agroclimatology)

The full list is in [`weather_climate.md`](weather_climate.md): 70 more sources (#57–126) by region, station ground truth, a US validation pilot against reference stations, and a per-country stack. The rows below are the ones to start with.

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 1 | **NASA POWER** (Agroclimatology) | https://power.larc.nasa.gov ; API: https://power.larc.nasa.gov/docs/services/api/ ; cloud copy: https://registry.opendata.aws/nasa-power/ | Analysis-ready parameters (temperature, rain, humidity, 2 m wind, solar radiation) at hourly, daily, monthly and climatology scales; API v2.10.1, data v10. Daily meteorology from 1981 on a ~0.5° × 0.625° grid: MERRA-2, then GEOS-IT for recent days, so ~5 days behind real time. Solar from 1984 on a 1° grid (SRB, CERES SYN1deg, FLASHFlux), ~7 days behind. Free, no key. **No FAO-56 ET0 parameter:** compute it from POWER's inputs. **Bug seen 26 Oct 2026:** a daily request that reaches GEOS-IT days returns precipitation ×24 for every day in the request; end requests at the last MERRA-2 month | Single-point daily series: KB. Full archive: hundreds of GB to TB | Keyless 40-year baseline; best solar of five products in the US pilot; FAO-56 inputs. Nights run ~1 °C warm, so correct Tmin before frost dates and GDD | ★★★ |
| 2 | **MERRA-2 reanalysis** | https://gmao.gsfc.nasa.gov/reanalysis/MERRA-2/ (data via GES DISC: https://disc.gsfc.nasa.gov) | Global atmospheric reanalysis, 1980 to present, ~50 km. Still produced (data through Sep 2026); no successor released | Very large (hundreds of TB total). Use subsets | Source dataset behind POWER. Use through POWER | ★ |
| 3 | **NASA NEX-GDDP-CMIP6 v2.0** | https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6 ; S3: `s3://nex-gddp-cmip6` ; NCCS THREDDS | Downscaled (BCSD against GMFD) 0.25° daily projections, 1950–2100, 90°N–60°S, SSP1-2.6/2-4.5/3-7.0/5-8.5, 35 configurations of 34 GCMs. v2.0 (Jul 2025) is only on S3 and THREDDS; the GEE and Planetary Computer copies are stale v1.x. No ET0; some models lack variables (CMCC-CM2-SR5 has no temperatures) | Tens of TB total. One variable, one model and scenario: a few GB | The "adapting" part: monthly deltas on an observed baseline for 2021–2040 and 2041–2060 | ★★★ |
| 57 | **ERA5 / ERA5T** **(non-NASA: Copernicus)** | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels ; ARCO Zarr `gs://gcp-public-data-arco-era5` | Hourly reanalysis, 0.25°, 1940 to ~5 days ago | Point series: MB | Current-season weather. Nights ~1.3 °C warm and ~29% too many wet days in the US pilot | ★★ |
| 59 | **TerraClimate** **(non-NASA)** | THREDDS: http://thredds.northwestknowledge.net:8080/thredds/catalog/TERRACLIMATE_ALL/data/catalog.html | Monthly ~4 km T, rain, Penman-Monteith PET, water deficit, 1950–2025. Keyless, CC0 | KB per point | Simplest RothC driver: pan evaporation = PET / 0.75 | ★★★ |
| 61 | **CHIRPS v3** **(non-NASA)** | https://data.chc.ucsb.edu/products/CHIRPS/v3.0/ | Rain 0.05°, 1981→, 60°S–60°N (v2 stops at 50°N) | MB per region | Gauge-blended rain where no national grid exists | ★★ |
| 71 | **gridMET** **(non-NASA)** | THREDDS: http://thredds.northwestknowledge.net:8080/thredds/ ; GEE `IDAHO_EPSCOR/GRIDMET` | US daily 4 km: T, rain, RH, solar, wind, grass ET0; 1979 to 2 days ago. Keyless | KB per point | US daily weather. ET0 reads ~8% high in the pilot | ★★★ |
| 72 | **Daymet V4R1** (NASA ORNL DAAC) | https://daymet.ornl.gov/single-pixel/ | North America daily 1 km: T, rain, solar, vapour pressure; 1980–2025. No wind | KB per point | US and Canada baseline: frost dates within days in the pilot | ★★★ |
| 77 | **CERRA** **(non-NASA: Copernicus)** | https://cds.climate.copernicus.eu/datasets/reanalysis-cerra-single-levels | European reanalysis, 5.5 km, incl. Ukraine; 1984-09 to 2026-07 | Point series: MB | Europe and Ukraine recent years | ★★★ |
| 84 | **ClimUAd** **(non-NASA: UHMI)** | https://uhmi.org.ua/ | Ukraine daily 0.1° T and rain from 178 stations, 1946–2020 | MB | Ukraine 1991–2020 baseline | ★★ |
| 90 | **USCRN** **(non-NASA: NOAA)** | https://www.ncei.noaa.gov/pub/data/uscrn/products/ | ~157 US reference stations: T, rain, solar, RH, wind (5-min) | KB per station-year | Ground truth for the US validation | ★★★ |
| 91, 92 | **GHCN-Daily / GHCNh** **(non-NASA: NOAA)** | https://www.ncei.noaa.gov/access/services/data/v1 ; https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly | Global station daily and hourly data, keyless. ISD and GSOD stopped updating in Aug 2025 | KB per station | Validation everywhere else | ★★★ |
| 107 | **World Bank CCKP CMIP6** **(non-NASA)** | `s3://wbg-cckp/data/cmip6-x0.25/` | Pre-computed 0.25° future indices from NEX-GDDP: frost days, hot days > 30/35 °C, growing-season length, SPEI-12; 20-year windows, all SSPs, ensemble percentiles | ~8 MB per layer | Zero-compute future-climate layer for the demo | ★★★ |
| 120, 126 | **Open-Meteo** (seasonal, forecast and archive APIs) **(non-NASA)** | https://open-meteo.com/en/docs | Keyless ERA5, ECMWF IFS and SEAS5 data, incl. FAO-56 ET0. Free tier is non-commercial | KB per call | Hackathon demo: current season and seasonal outlook | ★★ |

### 2B. Water: rain, soil moisture, groundwater, evapotranspiration

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 4 | **GPM IMERG** (precipitation) | https://gpm.nasa.gov/data/imerg (data via GES DISC) | Global satellite rainfall, 0.1°, half-hourly, daily and monthly products, 2000 to present | Half-hourly: ~100–200 GB/yr globally. Daily/monthly: far smaller | Rainfall totals, dry spells, flood risk for fields | ★★★ |
| 5 | **SMAP L4 soil moisture (SPL4SMGP)** | https://nsidc.org/data/spl4smgp | 3-hourly, 9 km surface (0–5 cm) and root-zone (0–100 cm) soil moisture, from 2015 to present. **Model output** (land model with SMAP radiometer data assimilated); it does not represent irrigation. The catalog shows ~2,900 files per year. Also on Earth Engine. | ~Hundreds of GB per global year (my estimate). Use regional subsets via Earthdata Search/AppEEARS | Root-zone moisture is the key irrigation and drought signal | ★★★ |
| 6 | **SMAP L3 (SPL3SMP_E) enhanced 9 km soil moisture** | https://nsidc.org/data/spl3smp_e | Daily satellite-observed soil moisture, **surface (0–5 cm) only**. The basic L3 product (SPL3SMP) is 36 km; do not mix the two | ~10–20 GB/yr globally | Observation-based alternative to the model-based L4 | ★★ |
| 7 | **GRACE-FO groundwater and soil moisture drought indicators** | https://nasagrace.unl.edu | Weekly surface, root-zone and groundwater wetness percentiles (GRACE/GRACE-FO assimilated into a land model, from 2003). Delivered on a 0.25° grid, but the true GRACE resolution is hundreds of km | Small (MB per file) | Groundwater stress for irrigation planning | ★★ |
| 8 | **Land data assimilation: GLDAS, NLDAS, FLDAS** | https://ldas.gsfc.nasa.gov (FLDAS: https://ldas.gsfc.nasa.gov/fldas) | Model-based soil moisture, evapotranspiration, runoff. FLDAS is built for food-security monitoring in data-scarce regions. | Monthly products: small. 3-hourly/hourly: tens to hundreds of GB | Long consistent soil-moisture and ET histories | ★★ |
| 9 | **ECOSTRESS evapotranspiration and water-stress products** | https://ecostress.jpl.nasa.gov ; via LP DAAC https://lpdaac.usgs.gov | 70 m thermal-based ET and evaporative stress from the ISS, from 2018, clear-sky only. V1 ET products were decommissioned on 30 Jan 2026; use the V2 collection | ~Tens to 100+ MB per scene | Field-level crop water stress. Irregular revisit | ★★ |
| 10 | **MODIS/VIIRS ET (MOD16A2GF, VNP16)** | https://lpdaac.usgs.gov/product_search/ | 500 m, 8-day evapotranspiration | ~100 GB/yr globally. Small for one region | Seasonal water use and deficit | ★★ |

### 2C. Crop and vegetation condition

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 11 | **Harmonized Landsat and Sentinel-2 (HLS) v2.0** | https://www.earthdata.nasa.gov/data/projects/hls ; https://lpdaac.usgs.gov | 30 m surface reflectance, observations every few days (cloud-optimized GeoTIFF). Documented as the most-downloaded NASA product in FY2024. | ~100–200 MB per tile-date (all bands). A year of one tile: tens of GB | Field-scale NDVI/EVI, crop phenology, within-field variability | ★★★ |
| 12 | **MODIS/VIIRS vegetation indices (MOD13Q1/MYD13Q1, VNP13A1)** | https://lpdaac.usgs.gov/product_search/ | 250 m–500 m NDVI/EVI 16-day composites (Terra and Aqua offset by 8 days), record back to 2000. Terra and Aqua are expected to be decommissioned around late 2026 or early 2027; VIIRS continues the record | ~10 GB per global composite; ~200 GB/yr. A single region: MB | Long-term greenness trends and drought anomalies | ★★★ |
| 13 | **MODIS/VIIRS GPP/NPP (MOD17)** | https://lpdaac.usgs.gov/product_search/ | 500 m productivity | ~50–100 GB/yr globally | Yield proxy | ★★ |
| 14 | **MODIS/VIIRS land surface temperature (MOD11, VNP21)** | https://lpdaac.usgs.gov/product_search/ | Daily 1 km land surface temperature | ~hundreds of GB/yr globally | Heat stress on crops | ★★ |
| 15 | **NISAR (L-band and S-band SAR)** | https://nisar.jpl.nasa.gov ; data via ASF DAAC https://asf.alaska.edu | Radar measurements, which see through clouds, for crop structure and soil moisture. Calibrated, provisional L-band data have been public since 20 Jul 2026, for observations from 17 Jun 2026. There is no earlier record, so NISAR cannot help reconstruct past seasons. | Large (SAR scenes are GB each) | Cloud-free crop monitoring and flood mapping | ★ |
| 16 | **NASA Harvest** | https://nasaharvest.org | NASA's food security and agriculture consortium: tools, labelled crop datasets, case studies | Varies | Crop type and yield context, plus ideas on what users need | ★★ |

### 2D. Ground truth, land cover and context (mostly non-NASA)

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 17 | **USDA Cropland Data Layer / CropScape** **(non-NASA: USDA)** | https://nassgeodata.gmu.edu/CropScape/ | Crop type map for the contiguous US, yearly from 2008. 30 m up to 2023, 10 m from 2024. Accuracy for major crops 85–95% | ~1–2 GB per year nationally | Crop masks and training labels (US only) | ★★ |
| 18 | **USDA NASS Quick Stats API** **(non-NASA)** | https://quickstats.nass.usda.gov/api | County-level yields, acreage, and prices | MB | Yield validation | ★★ |
| 19 | **ESA WorldCover** **(non-NASA: ESA)** | https://esa-worldcover.org | 10 m global land cover. Only two years (2020, 2021), made with different algorithms so not directly comparable, and one cropland class with no crop types | Tiles: ~tens of MB each. Global: ~100+ GB | Global cropland mask when no national crop map exists | ★★ |
| 20 | **MODIS land cover MCD12Q1** | https://search.earthdata.nasa.gov/search?q=MCD12Q1 | Annual 500 m land cover | A few GB per year | Cropland mask from NASA data | ★ |
| 21 | **SoilGrids (ISRIC)** **(non-NASA)** | https://soilgrids.org | Global soil properties (texture, organic carbon, pH) at 250 m | Tiles via API or ~tens of GB total | Soil context for water-holding capacity | ★★ |
| 22 | **OpenET** **(non-NASA, NASA-supported)** | https://openetdata.org | Field-scale evapotranspiration, US only (started with the western states; the team report says CONUS, so check coverage for your field) | Via API | Irrigation water accounting | ★ |
| 23 | **US Drought Monitor** **(non-NASA)** | https://droughtmonitor.unl.edu | Weekly drought classification maps | Small | Validation of drought indicators | ★ |
| 24 | **ASAP Early Warning (EU JRC)** **(non-NASA)** | https://mars.jrc.ec.europa.eu/asap/ | Crop-season anomaly monitoring for food-insecure regions | Small | Benchmark against a hotspot-of-concern product | ★ |
| 25 | **NASA SEDAC** | https://sedac.ciesin.columbia.edu | Population, hazards, agriculture-related gridded datasets | Varies | Who is affected: population exposed to drought or heat | ★ |

### 2E. Soil-depletion reconstruction: crop history, yields, fertilizer, nutrient removal, crop calendars, soil carbon models, validation

Nothing in 2A–2D can say how far a field has been drained. Satellites see crops and weather, not nutrient stocks. Depletion therefore has to be **reconstructed with a model**:

1. **Crop history:** the crop grown on the field each year.
2. **Removal:** for each year, crop × yield × removal coefficient gives the N, P2O5 and K2O taken off the field.
3. **Inputs:** fertilizer, manure and legume N are unknown for a single field, so they are sampled from regional priors as ranges (Monte Carlo), not fixed numbers.
4. **Soil carbon:** a soil carbon model (RothC or ICBM) driven by climate, clay content and residue inputs gives the trend in soil organic carbon (SOC).
5. **Anchor (optional):** if the farmer has a soil test, it is used to pin the estimate.

The sources below feed those steps. Show the output as **relative, modelled ranges** (rotation A drains more than rotation B), not as a measured soil test.

† = link not opened in this research pass; check it before relying on it.

**E1. Crop history (what was planted each year)**

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 26 | **USDA Crop Sequence Boundaries (CSB)** **(non-NASA: USDA)** | Metadata (2025 edition): https://data.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/metadata_Crop-Sequence-Boundaries-2025.htm ; GeoParquet copy: https://source.coop/fiboa/us-usda-cropland ; also in the Earth Engine community catalog | Field polygons for the contiguous US, each with the crop grown in each of the last 8 years (built from CDL). Editions from 2008 onward; the latest is the 2025 edition | A few GB nationally (estimate). One state: hundreds of MB | Crop history per field with no classification work. The core input for the US | ★★★ |
| 27 | **Fields of The World: harmonized field data** **(non-NASA)** | https://source.coop/ftw/harmonized-field-data | 67 collections of national and regional parcel data in fiboa GeoParquet. 51 of them give the crop per parcel per year, for example the Netherlands, Denmark, France, Austria and Sweden | Per country: hundreds of MB to a few GB (estimate) | Crop history outside the US, in the same format as #26 | ★★★ |
| 28 | **National parcel registers (direct)** **(non-NASA)** | Netherlands BRP crop parcels 2009–2025, CC0: https://api.pdok.nl † ; France RPG: https://geoservices.ign.fr/rpg † ; EuroCrops (harmonized EU crop names): https://github.com/maja601/EuroCrops † | Farmer-declared crop per parcel per year from EU subsidy claims. Denmark has 2008–2026 under CC0 | Per country per year: tens to hundreds of MB | Newer years than #27, and the original source when a collection needs checking | ★★ |
| 29 | **AAFC Annual Crop Inventory (Canada)** **(non-NASA)** | https://open.canada.ca (search "Annual Crop Inventory") † | 30 m crop-type raster, 2009–2025 | ~GB per year nationally (estimate) | Crop history for Canada (no field polygons; overlay the user's polygon) | ★ |
| 30 | **EU Crop Map 2022 (JRC)** **(non-NASA)** | Earth Engine: `JRC/D5/EUCROPMAP/V1` ; paper: https://doaj.org/article/a5f52dfdb57a46eb8dbf6166d0c3b33d | 10 m, 19 crop types, 2022 only (a 2018 version covers the EU only). Includes Ukraine. Overall accuracy 70.6% in the EU; Ukraine not reported separately | Earth Engine (no download needed) | One labelled year for EU or Ukraine fields that have no parcel register | ★★ |
| 31 | **ESA WorldCereal 2021 + reference data** **(non-NASA: ESA)** | Earth Engine: `ESA/WorldCereal/2021/MODELS/v100` ; https://esa-worldcereal.org † | Global 10 m maps for 2021: temporary crops, maize, winter and spring cereals. Also harmonized ground-truth points from 2017 on (licences vary; some subsets are non-commercial) | Earth Engine; points on Zenodo | Training labels for a crop classifier where no parcel register exists | ★ |

**E2. Yields and inputs (how much was removed, how much was put back)**

County yields for the US come from **Quick Stats (#18)**: crop × county yield × removal coefficient (#37) gives removal per year.

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 32 | **GDHY global gridded yields** **(non-NASA)** | https://doi.pangaea.de/10.1594/PANGAEA.909132 † | 0.5° yearly yields for maize, rice, wheat and soybean, 1981–2016 (extended to 2020 on DIAS). No barley, sunflower or rapeseed | Tens of MB | Yield per year outside the US for the main crops | ★★ |
| 33 | **SPAM2020** **(non-NASA: IFPRI)** | https://www.mapspam.info † | ~10 km harvested area and yield for 46 crops, around 2020 (one static year) | Hundreds of MB | Default yield where no yearly data exist | ★ |
| 34 | **FAOSTAT Cropland Nutrient Budget** **(non-NASA: FAO)** | FAOSTAT domain ESB: https://www.fao.org/faostat/en/#data/ESB † ; paper: https://essd.copernicus.org/articles/16/525/2024/ ; data: https://datadryad.org/dataset/doi:10.5061/dryad.hx3ffbgkh | Country-level N, P and K budgets for cropland: mineral fertilizer, manure, biological fixation, deposition, crop removal, balance and use efficiency. 205 countries, 1961–2020 (Ludemann et al. 2024) | MB | Country default inputs, and a check that the field-level balance is plausible | ★★ |
| 35 | **IFA Fertilizer Use by Crop (FUBC)** **(non-NASA)** | https://www.ifastat.org/consumption/fertilizer-use-by-crop ; data: https://datadryad.org/dataset/doi:10.5061/dryad.2rbnzs7qh | N, P2O5 and K2O rates by crop and country. The latest survey is mostly 2017/18 (covering 2016/17–2018/19, report May 2022); history back to 1992 | MB | Prior range for fertilizer per crop in the Monte Carlo. Dated, so use wide ranges | ★★ |
| 36 | **NuGIS (The Fertilizer Institute)** **(non-NASA)** | https://nugis.tfi.org/ | US county nutrient balances: fertilizer and manure inputs against crop removal | MB | US prior for inputs. Also a validation pair with #54 | ★★ |

**E3. Crop coefficients and calendars (how draining each crop is, and when it grows)**

These coefficients are compiled per crop in `crop_coefficients.csv` (24 crops). Keep removal, humus balance, water and erosion as **separate indices**; do not merge them into one score.

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 37 | **Nutrient removal per tonne of harvest** **(non-NASA)** | Germany DüV Anlage 7: https://www.gesetze-im-internet.de/d_v_2017/anlage_7.html ; OMAFRA: https://fieldcropnews.com/?p=28952 ; Iowa PM 1688: https://store.extension.iastate.edu/Product/5232-pdf ; Minnesota: https://mda.state.mn.us/sites/default/files/2018-05/nutmantables.pdf ; UK PDA: https://www.pda.org.uk/wp/wp-content/uploads/2020/03/pda-pprc.pdf ; SaskCanola: https://www.saskcanola.com/s/Final-Report-Revising-the-crop-nutrient-uptake.pdf | kg N, P2O5 and K2O removed per tonne of grain and of straw; straw-to-grain ratios | KB (tables) | Turns crop × yield into nutrients removed. Gaps: cotton, rice, sorghum, lentil, chickpea; K2O for canola, sunflower and pulses | ★★★ |
| 38 | **Humus balance coefficients (VDLUFA)** **(non-NASA)** | LfL Bayern: https://www.lfl.bayern.de/mam/cms07/iab/dateien/humusbilanz_beratung_bleistift-version_nov_2014_2.pdf | Humus equivalents per ha per year by crop. Examples: grain maize −800, cereals −400 to −520, sugar beet −1300, potato −1000, grain legumes +160, alfalfa or clover +800, straw returned +7 per dt | KB | A simple "how draining is each crop" score for rotations, and a cross-check on RothC | ★★★ |
| 39 | **Legume N credits** **(non-NASA)** | Wisconsin A3591: https://corn.aae.wisc.edu/Management/pdfs/A3591.pdf ; Nebraska: https://cropwatch.unl.edu/giving-proper-nitrogen-credit-legumes-corn-and-milo-rotations | N credited to the next crop after soybean, alfalfa or clover | KB | The positive side of the N balance in rotations | ★★ |
| 40 | **FAO-56 crop coefficients** **(non-NASA: FAO)** | https://www.fao.org/4/x0490e/x0490e0b.htm | Kc for the initial, mid and end stages, and stage lengths per crop | KB | Water demand per crop (separate index) | ★★ |
| 41 | **RUSLE crop cover factors (C)** **(non-NASA)** | OMAFRA: https://files.ontario.ca/omafra-universal-soil-loss-equation-23-005-en-2023-03-02.pdf | Cover-management factor per crop and tillage | KB | Erosion risk per crop (separate index), combined with slope from a DEM | ★ |
| 42 | **Crop calendars** **(non-NASA)** | Sacks et al. 2010 (SAGE): https://sage.nelson.wisc.edu/data-and-models/datasets/crop-calendar-dataset/ ; USDA NASS Crop Progress (in Quick Stats, #18) | SAGE: planting and harvest dates for 19 crops on 5′ and 0.5° grids (static, around 2000; the site asks downloaders to email the author). Crop Progress: weekly % planted and harvested by US state | 0.5° files: KB per crop | Season windows for the multi-year plan, monthly C inputs for RothC, and whether a cover crop fits | ★★★ |
| 43 | **GAEZ v5 (FAO/IIASA)** **(non-NASA)** | https://gaez.fao.org † | Suitability and attainable yield for ~280 crops under historical and future climates; ~1 km for key outputs (v5, April 2025) | Per layer: tens of MB | Which crops can grow on the field at all: the candidate list for the recommender | ★★ |

**E4. Soil carbon models and their inputs**

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 44 | **RothC soil carbon model** **(non-NASA: Rothamsted)** | Code: https://github.com/Rothamsted-Models/RothC_Code ; https://www.rothamsted.ac.uk/rothamsted-carbon-model-rothc ; Python ports: pyRothC (PyPI) †, CoolFarm: https://coolfarm.org/from-theory-to-practice-the-4-key-advantages-of-implementing-two-soc-models-in-python/ | Monthly SOC turnover model. Inputs: monthly temperature, rain and evaporation, clay %, starting SOC, plant carbon input, months with soil cover | KB | SOC trajectory from crop history, residues and climate | ★★★ |
| 45 | **ICBM** **(non-NASA)** | https://rdrr.io/cran/SoilR/man/ICBMModel.html | Two-pool yearly SOC model with few parameters | KB | Simpler cross-check on RothC | ★★ |
| 46 | **GSOCseq (FAO GSP)** **(non-NASA: FAO)** | https://www.fao.org/soils-portal/data-hub/soil-maps-and-databases/global-soil-organic-carbon-sequestration-potential-map-gsocseq/en/ ; RothC recipe: https://www.fao.org/fileadmin/user_upload/soils/Joint_trainings/Dec2022-OCB_GSP/4._GSOCseq_Running_the_RothC_Model.pdf | 1 km maps of 0–30 cm SOC stock and 20-year sequestration under business-as-usual and three better-management scenarios, built with RothC | Per country: tens of MB | Benchmark for our RothC runs, plus a ready RothC workflow | ★★ |
| 47 | **AgERA5 v2.0** **(non-NASA: Copernicus)** | https://cds.climate.copernicus.eu/datasets/sis-agrometeorological-indicators | Daily temperature, rain, radiation, vapour pressure, RH, 10 m wind and **FAO-56 ET0** at 0.1°, 1979 to present, ~8-day lag. v2.0 (May 2025) replaces the deprecated v1.1. Free CDS account and API key; CC-BY-4.0 | A few MB per point series | Global default for daily field weather and ET0. ERA5-based, so correct Tmin before frost dates (see `weather_climate.md`) | ★★★ |
| 48 | **SSURGO / gSSURGO** **(non-NASA: USDA NRCS)** | Soil Data Access: https://sdmdataaccess.nrcs.usda.gov † | Mapped soil survey units (1:12k–1:24k) with clay, SOC, water capacity and pH per horizon | Query per polygon: KB | US soil inputs at field scale (far finer than SoilGrids, #21) | ★★★ |
| 49 | **ISRIC WoSIS** **(non-NASA)** | https://www.isric.org/explore/wosis † | ~228k quality-checked soil profiles in 174 countries (Dec 2023 snapshot): SOC, N, P, pH, CEC, texture, bulk density | ~GB total | Nearest measured profiles to check SoilGrids and the RothC starting SOC | ★★ |
| 50 | **HWSD v2.0 (FAO/IIASA)** **(non-NASA)** | https://www.fao.org/soils-portal/data-hub/soil-maps-and-databases/harmonized-world-soil-database-v20/en/ † | ~1 km soil units with properties at 7 depths | ~GB | Fallback and cross-check for SoilGrids | ★ |

**E5. Validation ground truth (to test the reconstruction, not to drive it)**

| # | Source | Link | Description | Rough size | Application | Priority |
|---|---|---|---|---|---|---|
| 51 | **LUCAS topsoil (EU JRC ESDAC)** **(non-NASA)** | 2022: https://esdac.jrc.ec.europa.eu/content/lucas-2022-topsoil-data ; SOC change 2009–2018: https://esdac.jrc.ec.europa.eu/content/SOC-changes-2009-18 | Lab-measured SOC, N, P, K and pH. Rounds in 2009, 2015, 2018 and 2022; the 2022 round has ~19k samples, ~17k at revisited points. Registration required; data are noisy | Tens of MB | Compare modelled SOC, P and K trends with repeat measurements | ★★ |
| 52 | **Rothamsted long-term experiments (e-RA)** **(non-NASA)** | https://www.era.rothamsted.ac.uk/info/RLTEdatavailable ; access: https://era.rothamsted.ac.uk/info/howtoaccessdata | 150+ years of yields, inputs and soil C and N under known treatments (open tier) | MB | Check that RothC plus the nutrient balance reproduces known depletion and recovery | ★★ |
| 53 | **KBS LTER (Michigan)** **(non-NASA)** | https://lter.kbs.msu.edu/datasets/27 | Long-term US row-crop trial yields and soil data. Redistribution needs permission | MB | US validation plot | ★ |
| 54 | **TFI soil test summary** **(non-NASA)** | https://soiltest.tfi.org/about | US soil test P and K levels by state, in periodic summaries | MB | Compare NuGIS (#36) county surpluses with measured soil-test trends. Published correlation of county P surplus with soil-test P is only ~0.45–0.65 | ★★ |
| 55 | **France RMQS (INRAE)** **(non-NASA)** | https://app.inrae.fr/en/partnerships/monitoring-soils-for-better-protection/ | 16 km grid of repeat soil sampling | MB | French validation | ★ |
| 56 | **Ukrstat SDG 15.3.1** **(non-NASA)** | https://sdg.ukrstat.gov.ua/15-3-1 | National humus averages (e.g. 3.16% in 2015, 3.07% in 2020) | KB | Coarse sanity check for Ukraine only; no field-level data | ★ |

**Accuracy to expect (say this in the demo)**
- CDL crop labels, which feed CSB, are 85–95% accurate, so some history years will be wrong.
- Field-scale satellite yield estimates reach R² ≈ 0.45 (county scale ≈ 0.69). Use county yields unless the farmer gives their own.
- Calibrated RothC still errs by 3–25%. Published humus-balance validations range from R² 0.06 to 0.64. The smallest SOC change detectable by resampling is 6–31% of the mean.
- **Credible:** nutrient removal history, relative comparison of rotations with ranges, and the direction of the SOC trend.
- **Not credible:** the field's current P or K level, absolute SOC, and any "depleted" claim that ignores fertilizer.

### Suggested starter stack for Challenge 2
1. Daily weather: AgERA5 v2.0 (#47) globally; gridMET or Daymet (#71–72) in the US. NASA POWER (#1) is the keyless fallback: end requests before the GEOS-IT days. Details in `weather_climate.md`.
2. SMAP L4 root-zone soil moisture + GPM IMERG rainfall for water status.
3. HLS (or MODIS/VIIRS NDVI for larger areas) for crop condition.
4. NEX-GDDP-CMIP6 v2.0 (#3) from S3 or THREDDS for future climate, as monthly deltas on the observed baseline. CCKP indices (#107) give a zero-compute layer.
5. A cropland mask (CDL in the US, WorldCover elsewhere) and SoilGrids for context.
6. AppEEARS to pull point/polygon time series without large downloads.
7. For soil-depletion reconstruction (US first):
   - CSB crop history (#26).
   - Quick Stats county yields (#18) multiplied by removal coefficients (#37).
   - Input ranges from NuGIS and IFA (#35–36).
   - RothC (#44), driven by monthly TerraClimate or AgERA5 climate (#59, #47; pan evaporation = PET / 0.75) and SSURGO clay (#48).
   - Validation against e-RA and LUCAS (#51–52).

---

## Practical notes
- **Hackathon time budget:** 48 hours means prefer APIs (FIRMS, POWER, AppEEARS) and small regional subsets over global bulk downloads.
- **Cite data properly:** each Earthdata product page lists a recommended citation and DOI.
- **Mission status:** Terra/Aqua and S-NPP are aging. For Challenge 1 especially, check the date coverage of each sensor, since NOAA-20/21 continue VIIRS. For Challenge 2 the same applies to MOD13, MOD16, MOD17 and MOD11: prefer the VIIRS equivalents or HLS for anything after 2026.
- **Futures prices:** redistributing CME settlement data needs a CME licence. Show delayed, attributed prices for display only.

## Sources consulted
- FIRMS Archive Download: https://firms.modaps.eosdis.nasa.gov/download/
- FIRMS Active Fire Data page: https://firms.modaps.eosdis.nasa.gov/content/usfs/active_fire
- FIRMS API OpenAPI description (third-party profile): https://github.com/api-evangelist/nasa-firms
- FIRMS Q&A 2025 (NASA Applied Sciences): https://appliedsciences.nasa.gov/sites/default/files/2025-05/Part%203%20FIRMS%202025%20Q&A%20Session.docx.pdf
- LANCE FIRMS text files README: https://nrt3.modaps.eosdis.nasa.gov/archive/FIRMS/README.pdf
- MODIS Land news (orbit drift): https://modis-land.gsfc.nasa.gov/news.html
- Aqua status: https://aqua.gsfc.nasa.gov/sites/default/files/AquaStatus_November.pdf
- HLS overview (Earthdata): https://www.earthdata.nasa.gov/data/projects/hls
- HLS v2.0 article (NASA Landsat): https://landsat.gsfc.nasa.gov/article/a-new-and-improved-harmonized-landsat-and-sentinel-2-dataset
- NASA POWER on AWS: https://aws.amazon.com/marketplace/pp/prodview-agetvmpkkzb7a
- NASA POWER release note: https://www.nasa.gov/news-release/nasa-power-project-powers-up-with-new-version/
- SMAP L4 file counts (CMR): https://cmr.earthdata.nasa.gov/virtual-directory/collections/C3480440870-NSIDC_CPRD/temporal
- SMAP L4 on Earth Engine: https://developers.google.cn/earth-engine/datasets/catalog/NASA_SMAP_SPL4SMGP_008
- Space Apps 2026 overview (challenge list): https://www.therecursive.com/nasa-space-apps-challenge-2026-where-to-join-it-in-cee/
- Section 2E (reconstruction) sources: links are given in the 2E tables. Key papers: Ludemann et al. 2024, ESSD 16:525 (https://essd.copernicus.org/articles/16/525/2024/); Ludemann et al. 2022, Sci Data 9:501 (https://doi.org/10.1038/s41597-022-01592-z); Sacks et al. 2010, crop calendars (https://sage.nelson.wisc.edu/data-and-models/datasets/crop-calendar-dataset/); FAO GSOCseq (https://www.fao.org/soils-portal/data-hub/soil-maps-and-databases/global-soil-organic-carbon-sequestration-potential-map-gsocseq/en/); JRC EU Crop Map 2022 (https://doaj.org/article/a5f52dfdb57a46eb8dbf6166d0c3b33d).
