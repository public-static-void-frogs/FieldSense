# Weather and climate data for Field Shift (section 2A)

Research date: 26 Oct 2026. This is the deep-dive for section 2A of the data guide ([`space_apps_2026_data_sources.md`](space_apps_2026_data_sources.md)). New sources are numbered from #57, after the data guide's #1–56, so other files can cite them.

**Tags.** [V]: seen on an official page or in a live API call this session. [S]: secondary or third-party source only. [U]: not verified; check before citing. † marks a link that could not be opened from here.

**Roles.**
- SD: soil-depletion model (RothC/ICBM inputs).
- ROT: rotation recommendation (water index, crop fit).
- CH: crop-history and season context.
- PROJ: future climate (2030/2050 fit).
- SEAS: seasonal and short-term outlook.
- VAL: validation.

**Method.**
- Four parallel search passes; live keyless calls to every API named in section 8.
- A station pilot in the US: 6 USCRN reference stations, 2015–2024 (section 6.3).
- Some official sites block automated access: climatologylab.org, CIMIS, spei.csic.es, the IPCC Atlas. For those, specs come from mirrors (THREDDS, GEE STAC) or from search results, and are tagged accordingly.

## 1. Key findings

1. **NASA POWER daily precipitation has a ×24 bug** [V, reproduced at two points].
   - When a daily request reaches into the GEOS-IT period (currently 1 Oct 2026 onward), `PRECTOTCORR` comes back exactly 24 times too large **for every day in the request**, including the older MERRA-2 days.
   - Example: Iowa, September 2026 requested alone sums to 241 mm. The same days inside a September–October request sum to 5,794 mm.
   - Temperature is not affected.
   - Guard: end requests at the last MERRA-2 month, and check `header.sources` for `GEOSIT`.
2. **POWER is now ~5 days behind real time, not 1–2 months** [V].
   - Meteorology was available to 21 Oct and solar to 19 Oct when checked on 26 Oct.
   - Recent days come from GEOS-IT and FLASHFlux v4C.
   - The CERES SYN1deg delay noted in the audit is over: SYN1deg is back to its normal 3–4 month lag.
3. **POWER has no FAO-56 ET0 parameter** [V, from the AG parameter list, 152 daily parameters]. `EVPTRNS` is actual ET as an energy flux. ET0 must be computed from POWER's T, dew point/RH, 2 m wind and radiation.
4. **AgERA5 is now v2.0** (May 2025) [V].
   - It includes a **FAO-56 ET0** variable, is CC-BY-4.0 and is ~8 days behind.
   - It is the best global default for daily field weather, but needs a free CDS key.
5. **TerraClimate is the simplest RothC driver** [V]: monthly, ~4 km, with Penman-Monteith PET, keyless, CC0, 1950–2025. RothC wants open-pan evaporation, so feed **PET / 0.75** (section 2).
6. **NEX-GDDP-CMIP6 v2.0** (July 2025) is only on S3 and NCCS THREDDS. The GEE and Planetary Computer copies are stale (v1.x, 2 SSPs). CMCC-CM2-SR5 has no temperatures in v2.0 (section 4).
7. **Ready-made future agro-indices exist and need no key:** World Bank CCKP on S3 (#107) has frost days, hot days > 30/35 °C, growing-season length and SPEI-12 per 20-year window, SSP and ensemble percentile, at 0.25°.
8. **US pilot against 6 USCRN reference stations, 2015–2024 (section 6.3).**
   - The station-based US grids (gridMET, Daymet) match closely: monthly T within ±0.1 °C, season GDD within ±2%, frost dates within 1–4 days. The stations are probably among their inputs, so this is optimistic.
   - ERA5, ERA5-Land and POWER run warm at night: Tmin +0.9 to +2.0 °C. That makes the first autumn frost 1–3 weeks late and GDD 7–8% high unless corrected.
   - ERA5 has ~29% too many wet days.
   - FAO-56 ET0 from POWER inputs is unbiased here (median 0%); ERA5 is +6%, gridMET +8%.
   - One cold-air site in California was 2–6 °C colder at night than every grid.
9. **Ukraine is the weak region.**
   - The national station feed to ECA&D stops at 2020-12-31; after that only ~26 GTS (Global Telecommunication System) synoptic stations report.
   - Use ClimUAd (#84) for the 1991–2020 baseline and CERRA (#77, to July 2026) for recent years.
   - Check against GHCN-D and GHCNh stations.
10. **Licence traps.**
    - Non-commercial: E-OBS and ECA&D, WorldClim (also no redistribution), MSWEP/MSWX, WaPOR, the Open-Meteo free tier, JRA-3Q.
    - Paid: Oklahoma Mesonet. Written consent needed for automated use: Kansas Mesonet.
11. **NOAA station products changed.** ISD and GSOD stopped updating after 2025-08-24. Use GHCN-Daily and GHCNh (hourly).

## 2. What the model needs from weather and climate

| Model part | Variables | Step | Period |
|---|---|---|---|
| SD: RothC / ICBM | Mean T, rain, open-pan evaporation | Monthly | ~2008 → now, plus a 30-year climatology for spin-up |
| ROT: water index | ET0 (FAO-56 Penman-Monteith: Tmax, Tmin, humidity, 2 m wind, solar) × Kc from `crop_coefficients.csv` | Daily | Season |
| ROT: crop fit | GDD (crop-specific base), last spring and first autumn frost, heat days at flowering, dry spells, seasonal rain, water deficit | Daily, then per season | 1991–2020 baseline, plus 2021–2040 and 2041–2060 |
| PROJ | Same indices under SSP2-4.5 and SSP5-8.5, bias-adjusted against the baseline | Daily or monthly | 2021–2060 |
| SEAS | Next 1–6 months: warmer or wetter than normal | Monthly | Current season |
| CH | Season windows, rain and temperature anomalies | Daily | 2008 → now |
| VAL | Station series near the field | Daily | Overlap years |

**RothC evaporation input** [V, from the RothC v2.1.1 code and the Rothamsted model description]. RothC takes monthly open-pan evaporation in mm/month and computes the moisture deficit as `rain − 0.75 × pan`. With only PET or ET0, feed **pan = PET / 0.75**. SoilR and FAO GSOCseq expose a factor `pE`; with PET as input they set `pE = 1`. Do not apply both conversions. SILO (#86) gives Class-A pan evaporation directly in Australia.

**ET0 recipe.**
- Use FAO-56 eq. 6 at a daily step.
- 10 m wind to 2 m: multiply by 0.748 (FAO-56 eq. 47).
- No humidity: set Tdew ≈ Tmin (eq. 48).
- No radiation: Hargreaves radiation (eq. 50).
- No wind: 2 m/s. Changing wind to 1 or 3 m/s moves ET0 by about −7% or +6%.
- Use `pyet.pm_fao56` (latitude in **radians**) or `refet`. Do not use `xclim`'s `FAO_PM98`: it assumes 10 m wind and sea-level pressure.
- ERA5 `pev` is not ET0. Never multiply `pev` by Kc.

## 3. Sources

Each row: what it gives, the real resolution, coverage and latency as seen on 26 Oct 2026, access and licence, and the role in the model. Already-numbered sources from the data guide are repeated only where this research changes them.

### 3.1 Global grids (past and current weather)

| # | Source | Variables | Grid | Coverage · latency | Access · licence | Role | ★ | Tag |
|---|---|---|---|---|---|---|---|---|
| 1 | **NASA POWER** (API v2.10.1, data v10). [power.larc.nasa.gov](https://power.larc.nasa.gov/docs/methodology/data/sources/) | T2M, T2M_MAX/MIN, T2MDEW, RH2M, WS2M (2 m), ALLSKY_SFC_SW_DWN, PS, PRECTOTCORR, IMERG_PRECTOT. Monthly GDD and FROST_DAYS. **No ET0** | Meteorology ½° × ⅝° (~50 km); solar 1° | Global. Meteorology 1981→, solar 1984→. Recent ~5 days (GEOS-IT); solar ~7 days (FLASHFlux) | REST (no key); Zarr on `s3://nasa-power`. Open; cite POWER | SD, ROT, CH | ★★★ with the precipitation guard | [V] |
| 47 | **AgERA5 v2.0**. [CDS](https://cds.climate.copernicus.eu/datasets/sis-agrometeorological-indicators) | Tmax/Tmin/Tmean, dew point, vapour pressure, RH (incl. min/max), 10 m wind, solar, rain, snow, cloud, **FAO-56 ET0**, VPD | 0.1° (ERA5 regressed to HRES topography; detail close to ERA5 except in hills) | Global 1979→; ~8 days (catalogue to 18 Oct) | CDS account and key; accept the licence on the web; request `version: "2_0"`. CC-BY-4.0 | SD, ROT, CH | ★★★ | [V] |
| 57 | **ERA5** (incl. preliminary ERA5T). [CDS](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels); ARCO Zarr `gs://gcp-public-data-arco-era5`; `s3://nsf-ncar-era5` | Full set (t2m, d2m, u10/v10, ssrd, tp…) | 0.25° (~31 km) | Global 1940→. ERA5T ~5 days (to 20 Oct); the final version replaces ERA5T after 2–3 months | CDS key; ARCO and NCAR S3 anonymous; Open-Meteo `era5` keyless. CC-BY-4.0 | SD, ROT, CH | ★★ | [V] |
| 58 | **ERA5-Land**. [CDS](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land); GEE `ECMWF/ERA5_LAND/DAILY_AGGR` | t2m, d2m, u10/v10, ssrd, tp, soil, snow | 0.1° grid on 31 km ERA5 forcing, with a lapse-rate correction | Land 1950→; ~5–6 days | CDS or GEE. **Open-Meteo `era5_land` returns temperature and humidity only: no rain, radiation, wind or ET0** (use `era5_seamless`). CC-BY-4.0 | ROT, CH | ★★★ for temperature | [V] |
| 59 | **TerraClimate**. THREDDS `TERRACLIMATE_ALL/data/` | tmax, tmin, ppt, vap, vpd, srad, ws, **pet** (Penman-Monteith), aet, **def** (water deficit), soil, PDSI | 1/24° (~4 km; climatology-aided, anomalies from coarse inputs) | Land 1950–2025 on THREDDS (GEE to 2024-12). Yearly, ~6 months after year end | THREDDS NCSS, keyless (CSV values are packed: × 0.1). CC0 [S] | **SD** (monthly RothC input), CH | ★★★ | [V] files, [S] licence |
| 60 | **CRU TS 4.10**. [crudata.uea.ac.uk](https://crudata.uea.ac.uk/cru/data/hrg/) | tmp, tmn, tmx, pre, **pet** (mm/day: × days in month), vap, cld, wet, frs | 0.5° | Land 1901–2025; released June 2026 | UEA download (CEDA later). ODbL (share-alike) | SD spin-up (the GSOCseq path) | ★★ | [V] |
| 61 | **CHIRPS v3**. [data.chc.ucsb.edu](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/) | Rain; two daily versions ("rnl" split by ERA5, "sat" split by IMERG) | 0.05° | Land **60°S–60°N** (v2 stops at 50°N and misses northern Ukraine), 1981→. Preliminary 2 days after each pentad | HTTPS keyless. GEE `UCSB-CHG/CHIRPS/DAILY` is v2. CC BY 4.0 | ROT, CH | ★★ | [V] |
| 62 | **CHIRTS-ERA5** | Tmax, Tmin, heat index | 0.05° | 60°S–70°N, 1980→; ~5 days | HTTPS. Licence [U] | CH (heat days) | ★ | [V] coverage |
| 63 | **CPC Global Unified** (gauge only). [PSL](https://downloads.psl.noaa.gov/Datasets/cpc_global_temp/) | Rain, Tmax, Tmin | 0.5° | Land 1979→; ~1 day. Gauge network changed in 2006, so not homogeneous [S] | HTTPS keyless. Acknowledge PSL | VAL, ROT | ★★ | [V] |
| 64 | **MSWEP V3 / MSWX**. [gloh2o.org](https://www.gloh2o.org/mswep/) | Rain (MSWEP); bias-corrected meteorology (MSWX) | 0.1°, 3-hourly | Global 1979→; near real time | Form, then Google Drive. **CC BY-NC 4.0** | — | ★ (licence) | [V] |
| 65 | **CHELSA v2.1** (monthly, daily). [chelsa-climate.org](https://chelsa-climate.org/datasets/chelsa_monthly) | Monthly: 13 variables incl. pet. Daily: tas, tasmax, tasmin, pr, rsds, hurs, sfcWind | ~1 km | Monthly 1979–2021; daily 1941 → 2025-08-29 | COG keyless. CC0 | CH, downscaling | ★★ | [V] |
| 66 | **WorldClim 2.1**. [worldclim.org](https://www.worldclim.org/data/worldclim21.html) | 1970–2000 climatology (T, rain, solar, wind, vapour pressure, bioclim). Monthly 1950–2024 (T, rain only) | 30″–10′ | Global land | HTTPS. **Non-commercial, no redistribution** | CH | ★ (licence; use CHELSA) | [V] |
| 67 | **JRA-3Q**. [GDEX](https://gdex.ucar.edu/datasets/d640000/) | Full reanalysis | 0.375° | 1947 → Sep 2026 | Account. CC BY-NC-SA | Cross-check | ★ | [V] |
| 68 | **hPET** (Singer et al. 2021). [data.bris.ac.uk](https://data.bris.ac.uk/data/dataset/qb8ujazzda0s2aykkv0oq0ctp) | Hourly and daily PET (Penman-Monteith on ERA5-Land with model albedo, so PET, not ET0) | 0.1° | Land 1981–2025; updated each January | Download (2.5 TiB total). CC BY 4.0 | SD | ★★ | [V] |
| 69 | **GLEAM 4.3**. [gleam.eu](https://www.gleam.eu/) | Actual ET and components, potential evaporation, evaporative stress, root-zone moisture | 0.1° | 1980–2024 (4.3a) | SFTP after registration. Free; commercial use needs approval | VAL (actual ET) | ★★ | [V] |
| 70 | **FAO WaPOR v3 reference ET**. GEE `FAO/WAPOR/3/L1_RET_D` | Reference ET (Penman-Monteith), daily and dekadal | ~20–30 km | Global 2018→; ~2 weeks | Keyless API. **CC BY-NC-SA 4.0** | ROT cross-check | ★ | [V] |

GPM IMERG (#4) is also served through POWER as `IMERG_PRECTOT` at 0.1°, keyless [V].

### 3.2 Regional and national grids

Finer grids built from dense station networks. Where one exists, prefer it to a global grid: 1–8 km instead of 10–50 km.

| # | Source | Variables | Grid | Coverage · latency | Access · licence | Role | ★ | Tag |
|---|---|---|---|---|---|---|---|---|
| 71 | **gridMET** (US). THREDDS `agg_met_<var>_1979_CurrentYear_CONUS.nc`; GEE `IDAHO_EPSCOR/GRIDMET` | pr, tmmx, tmmn, rmax, rmin, sph, srad, vs (10 m), vpd, **grass ET0** (variable `pet`), etr | 1/24° (~4 km) | CONUS 1979→; to 24 Oct (2 days) | THREDDS NCSS keyless; **CSV returns packed integers** (apply `scale_factor`/`add_offset` from the `.das`). Public domain; cite Abatzoglou 2013 | ROT, SD, CH | ★★★ US | [V] |
| 72 | **Daymet V4R1** (NASA ORNL DAAC). [single-pixel API](https://daymet.ornl.gov/single-pixel/) | tmax, tmin, prcp, srad, vp, dayl, swe. **No wind, no ET0** | 1 km | North America 1980–**2025** (annual release; 2026 arrives mid-2027). 365-day years | REST keyless; GEE `NASA/ORNL/DAYMET_V4`. NASA open; cite DOI 10.3334/ORNLDAAC/2129 | SD, CH | ★★★ North America | [V] |
| 73 | **PRISM** (US). [services.nacse.org](https://prism.oregonstate.edu/) | ppt, tmin, tmax, tmean, tdmean, vpdmin/max; 1991–2020 normals | 800 m, 4 km | CONUS. Daily 1981→ (provisional; stable after 6 months); monthly 1895→. **Day runs 12:00–12:00 UTC** | Web service keyless, one grid per request, 2 downloads per file per day; COG since 1 Oct 2025. Free with attribution; commercial use restricted [S] | CH (800 m normals), VAL | ★★★ US | [V] |
| 74 | **nClimGrid-Daily** (NOAA) | tmax, tmin, tavg, prcp | ~5 km | CONUS 1951→; preliminary 3 days | HTTPS keyless. Public domain [U] | CH, VAL | ★★ | [V] |
| 75 | **NLDAS-3 forcing** (beta). `s3://nasa-waterinsight/NLDAS3/` | All ET0 inputs; hourly, daily, monthly | 0.01° | North and Central America, **2001–2023 only** | S3 keyless. NASA open | Future US option | ★ | [V] |
| 76 | **ECCC MSC GeoMet API + CaPA** (Canada). [api.weather.gc.ca](https://api.weather.gc.ca/) | Station climate-daily and -hourly, normals; CaPA 10 km rain analysis | Stations; 10 km | Canada; 1 day | OGC API keyless. OGL-Canada [U]. Daymet (#72) also covers Canada | VAL, ROT | ★★★ Canada | [V] |
| 77 | **CERRA + CERRA-Land** (Europe). [CDS](https://cds.climate.copernicus.eu/datasets/reanalysis-cerra-single-levels) | t2m, Tmax/Tmin, RH, 10 m wind, solar, rain. CERRA rain is a forecast field: prefer the CERRA-Land analysis | 5.5 km | Europe incl. **Ukraine** (east to the Urals). CERRA 1984-09 → 2026-07; CERRA-Land to 2025-12. ~3 months behind | CDS key. CC-BY-4.0 | SD, CH, ROT (historical) | ★★★ EU, Ukraine | [V] |
| 78 | **E-OBS v33.0e** | tg, tn, tx, rr, pp, hu, fg, qq, plus ensemble spread | 0.1°, 0.25° | Europe 1950→ (end date [U]). Sparse stations in the east (Ukraine ~24 after 2020) | CDS or ECA&D. **Non-commercial research and education only** | CH, VAL | ★★ (licence) | [V] |
| 79 | **HadUK-Grid v1.3.2** (UK). [CEDA](https://catalogue.ceda.ac.uk/uuid/4dc8450d889a491ebb20e724debe2dfb) | Daily tasmax, tasmin, tas, rain; monthly sun, humidity, wind | 1 km | UK 1836–2025 (annual) | CEDA login. OGL v3 | CH, SD | ★★★ UK | [V] |
| 80 | **DWD Climate Data Center** (Germany). [opendata.dwd.de](https://opendata.dwd.de/climate_environment/CDC/) | HYRAS-DE v6-1 daily tasmax, tasmin, tas, pr, hurs; **daily FAO grass ET0 grid**; radiation 5 km only to 2020 | 1 km | Germany; 1 day | HTTPS keyless (list directories: version tags change). CC BY 4.0 | ROT, SD, CH, VAL | ★★★ DE | [V] |
| 81 | **Météo-France SIM2 (SAFRAN-ISBA)**. [data.gouv.fr](https://www.data.gouv.fr/datasets/donnees-changement-climatique-sim-quotidienne) | Full surface meteorology, Penman-Monteith ETP, soil water index | ~8 km | France, ~1958→ [U]; last 60 days updated daily | csv.gz keyless. Licence Ouverte 2.0 | SD, ROT, CH | ★★★ FR | [V] |
| 82 | **GeoSphere Austria**: SPARTACUS v3, WINFORE v2. [dataset.api.hub.geosphere.at](https://dataset.api.hub.geosphere.at/v1/) | Daily TX, TN, TM, RR, sunshine; **daily ET0** and SPEI | 1 km | Austria 1961 → 1 day | API keyless. CC BY 4.0 | ROT, SD, CH, VAL | ★★★ AT | [V] |
| 83 | **Other European services** | AEMET OpenData (ES; free key; grids 1951–2022 only); KNMI Data Platform (NL; key, shared anonymous key valid to 2027-08-01); DMI Climate Data API (DK); SMHI (SE); FMI (FI); CHMI (CZ); SHMU (SK) | Stations, some grids | Mostly 1 day | DK, SE, FI, CZ, SK keyless. CC BY 4.0 mostly [U] | VAL | ★★ | [V] endpoints |
| 84 | **ClimUAd** (Ukrainian Hydrometeorological Institute). [uhmi.org.ua](https://uhmi.org.ua/) | Daily Tmin, Tmax, Tmean, rain from 178 stations | 0.1° | Ukraine **1946–2020** | Free download for research; licence not stated. Cite DOI 10.15407/uhmi.report.03 | CH (1991–2020 baseline) | ★★★ Ukraine | [V] site, [S] paper |
| 85 | **BR-DWGD v3.2.4** (Brazil). [GitHub](https://github.com/AlexandreCandidoXavier/BR-DWGD) | pr, Tmax, Tmin, Rs, RH, u2, **ETo** | 0.1° | Brazil 1961 → 2025-12 | Google Drive, GEE asset. No licence stated; cite Xavier et al. 2022 | SD, ROT, CH | ★★★ BR | [V] |
| 86 | **SILO** (+ AGCD) (Australia). [longpaddock.qld.gov.au](https://www.longpaddock.qld.gov.au/silo/) | Rain, Tmax, Tmin, solar, vapour pressure, RH at Tmax/Tmin, **Class-A pan evaporation**, FAO-56 ET0 (`et_short_crop`). No wind | 0.05° | Australia 1889 → yesterday | S3 `silo-open-data` keyless; API takes an email as username. CC BY 4.0 | **SD** (pan evaporation feeds RothC as is), ROT | ★★★ AU | [V] |
| 87 | **IMD gridded** (India). [imdpune.gov.in](https://www.imdpune.gov.in/) | Rain (0.25°, 1901–2025); Tmax/Tmin (1°, 1951→) | 0.25°, 1° | India | GrADS binary, no registration. Cite Pai et al. 2014 | CH (rain). The 1° temperature grid is too coarse for fields | ★★ | [V] rain |
| 88 | **ENACTS** (IRI; KMD Kenya, BMD Bangladesh) | Daily and dekadal rain, Tx, Tn | ~4–5 km | Kenya (last updated Nov 2025; daily rain possibly only to 2023 [S]); Bangladesh 1981→ [S] | IRI Data Library per country; the BMD library did not respond † | CH | ★★ | [V] KMD, [S] BMD |
| 89 | **TAMSAT v3.1 + ARC2** (Africa) | Rain (TAMSAT also soil moisture) | ~4 km; ~10 km | Africa 1983→; ARC2 2 days | HTTP keyless. Licence [U] | ROT, CH | ★★★ SSA | [V] |

### 3.3 Stations and flux towers (ground truth)

| # | Source | Variables | Network | Latency | Access · licence | Role | ★ | Tag |
|---|---|---|---|---|---|---|---|---|
| 90 | **USCRN** (US Climate Reference Network). [daily01](https://www.ncei.noaa.gov/pub/data/uscrn/products/daily01/) | Daily Tmax, Tmin, Tavg, rain, **solar**, **RH max/min**, soil moisture and temperature 5–100 cm; **wind at 1.5 m** in the 5-min files (`subhourly01`) | ~157 reference-grade sites | 1–2 days | Text files, keyless. Public domain | **VAL (reference)** | ★★★ | [V] |
| 91 | **GHCN-Daily v3.35** + NCEI Access Data Service | TMAX, TMIN, PRCP, SNOW (+ AWND, EVAP at some) | ~100k stations worldwide. Active (2025+) TMAX stations: Ukraine 32, India 162, Bangladesh 9, Kenya 8 | Daily | ADS keyless (service degraded 2–30 Oct 2026 during a cloud migration); the old CDO v2 API needs a token. Public domain | VAL | ★★★ | [V] |
| 92 | **GHCNh** (hourly; replaces ISD/GSOD). [NCEI](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly) | Hourly T, dew point, pressure, wind, rain, with QC flags | Global | ~2 days | PSV or Parquet, keyless. Public domain | VAL (humidity and wind for ET0) | ★★★ | [V] |
| 93 | **RCC-ACIS** (US). [data.rcc-acis.org](https://data.rcc-acis.org/) | Station daily T, rain, GDD at any base, frost-date reductions; PRISM-based grids | US | 1 day | JSON, keyless | VAL, CH | ★★★ US | [V] |
| 94 | **Iowa Environmental Mesonet** (+ state mesonets). [mesonet.agron.iastate.edu](https://mesonet.agron.iastate.edu/) | ASOS/COOP daily, ISU ag stations, IEMRE grid | National, densest in Iowa | 1 day | Keyless. Other mesonets: **Kansas needs written consent for automated use, Oklahoma is paid** (redistribution forbidden), Illinois WARM daily includes PET | VAL | ★★★ US | [V] |
| 95 | **NRCS SCAN** | T, rain, RH, wind, solar, soil moisture | ~200 sites [U] | 1 day | REST keyless. Public domain | VAL | ★★ | [V] |
| 96 | **NOAA US Climate Normals 1991–2020** | GDD normals (°F bases), freeze and frost dates by probability, growing-season length; ~4 km gridded monthly and daily | > 7,300 stations | Static | ADS keyless | CH, VAL | ★★★ US | [V] |
| 97 | **CIMIS** (California) | Station ASCE ET0, solar, RH, wind; Spatial CIMIS 2 km ET0 | California | 1 day | Free AppKey; the site refused connections from here † | VAL (ET0 truth) | ★★ | [S] |
| 98 | **Flux towers**: AmeriFlux, FLUXNET Shuttle (launched 2026, > 700 sites), ICOS, OzFlux | Measured latent heat (actual ET), net radiation, meteorology | Towers | Rolling | Account or licence acceptance. CC BY 4.0 mostly; mixing AmeriFlux CC-BY and Legacy sites puts all under Legacy | VAL (actual ET, not ET0) | ★★ | [V] |
| 99 | **ECA&D**. [ecad.eu](https://www.ecad.eu/) | Daily TX, TN, TG, RR (blended, homogenised) | Europe incl. 142 Ukrainian stations. Ukrainian Hydromet series end 2020-12-31; ~26 Ukrainian GTS series run to 2026-09-30 | Monthly | Keyless zip. **Non-commercial research and education** | VAL (EU, Ukraine) | ★★ | [V] |
| 100 | **Meteostat** 2.1.5 | Station hourly and daily, with a source column per value | Global | Varies | Bulk files keyless; JSON API through RapidAPI key. CC BY 4.0. **Fills gaps with model data**: filter on the source columns | VAL after filtering | ★★ | [V] |
| 101 | **Station portals outside Europe**: INMET (Brazil, annual zips 2000–2026), SMN (Argentina, rolling ~365 days, no rain in the daily file), OGIMET (raw SYNOP gap filler) | Daily or hourly station data | National | 1 day | Keyless. Archive SMN yourself | VAL | ★ | [V] |

Also relevant from the data guide: OpenET (#22, field ET for the US; MAE 17% on cropland against 152 towers, Volk et al. 2024 [V]).

### 3.4 Ready-made indices of past climate

| # | Source | Gives | Grid | Coverage · latency | Access · licence | Role | ★ | Tag |
|---|---|---|---|---|---|---|---|---|
| 102 | **JRC Drought Observatories** (EDO Europe, GDO global). [data directory](https://drought.emergency.copernicus.eu/data/Drought_Observatories_datasets/) | Combined Drought Indicator, SPI 1–48 (from ERA5, E-OBS, CHIRPS, GPCC…), SPEI, soil-moisture anomaly, fAPAR anomaly, heat and cold waves, GDO "risk of drought impacts for agriculture" | ~5 km (CDI) | Europe, global; dekadal, ~10 days | HTTP directory, keyless. CC BY 4.0 | ROT (drought, heat) | ★★★ EU, ★★ global | [V] |
| 103 | **SPEIbase v2.11** + SPEI Global Drought Monitor | SPEI 1–48 months (base: Penman-Monteith on CRU; the monitor uses Thornthwaite, temperature only) | 0.5° | 1901–2024; monitor monthly | GEE `CSIC/SPEI/2_11`; site † | ROT (drought climatology) | ★★ | [V] GEE |
| 104 | **US index layers**: GEE `GRIDMET/DROUGHT` (SPI, SPEI, EDDI, PDSI); USA-NPN accumulated GDD (base 32 and 50 °F); US Drought Monitor (#23) | Drought and GDD | ~4 km | CONUS; 1–7 days | GEE; WMS keyless | ROT (US) | ★★ | [V] |
| 105 | **NOAA STAR blended VHP** (VHI, VCI, TCI) | Vegetation and thermal stress | 4 km and 16 km from 1981; VIIRS 1 km from 2019 | Weekly | Keyless | CH (past crop stress) | ★ | [V] |
| 106 | **HadEX3 / CLIMDEX** | ETCCDI climate-extreme indices | 1.875° × 1.25° | 1901–2018 | Free. OGL | Context only (too coarse) | ★ | [V] |

POWER's climatology endpoint also returns GDD and frost days per month [V].

### 3.5 Future climate

| # | Source | Gives | Grid | Coverage | Access · licence | Role | ★ | Tag |
|---|---|---|---|---|---|---|---|---|
| 3 | **NEX-GDDP-CMIP6 v2.0**. [NCCS](https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6); `s3://nex-gddp-cmip6` | Daily hurs, huss, pr, rlds, rsds, sfcWind, tas, tasmax, tasmin. **No ET0** | 0.25° | 90°N–60°S. Historical 1950–2014 and SSPs 2015–2100 (SSP1-2.6/2-4.5/3-7.0/5-8.5). 35 configurations (34 GCMs; GFDL-CM4 on two grids). v2.0 put on S3 on 1 Jul 2025 | S3 and NCCS THREDDS, keyless (filter on `_v2.0.nc`). **GEE and Planetary Computer are stale** (≤ v1.2, 2 SSPs). CC0 on AWS; the tech note says research use | PROJ | ★★★ | [V] |
| 107 | **World Bank CCKP CMIP6 0.25°**. `s3://wbg-cckp/data/cmip6-x0.25/` | ~90 pre-computed indices: frost days, ice days, hot days > 30/35/40 °C, tropical nights, growing-season length, start and end, CDD, CWD, Rx1day, SPEI-12; a daily subset | 0.25° (from NEX-GDDP) | Global. 20-year windows 1995–2014, 2020–39, 2040–59, 2060–79, 2080–99. SSP1-1.9 to 5-8.5. Per model and ensemble p10/median/p90 | S3 keyless (~8 MB per layer); API gives country and sub-national aggregates only. Licence statements disagree (ODbL, CC BY, CC0): attribute the World Bank | PROJ (zero-compute demo layer) | ★★★ | [V] |
| 108 | **ISIMIP3b bias-adjusted**. [files.isimip.org](https://files.isimip.org/ISIMIP3b/) | 11 daily variables incl. tasmax, tasmin, pr, hurs, rsds, sfcWind | 0.5° | Global 1850–2100. 5 primary GCMs × SSP1-2.6/3-7.0/5-8.5; SSP2-4.5 for 14 GCMs (added June 2026). Reference W5E5 v2.0 | HTTPS keyless. CC0 | PROJ (cross-check with a different method and reference) | ★★ | [V] |
| 109 | **CHELSA v2.1 CMIP6 climatologies** | Monthly tas/tasmax/tasmin/pr; bioclim incl. **gdd0, gdd5, gdd10**, first and last GDD day, growing-season length | ~1 km | 1981–2010, 2011–40, 2041–70, 2071–2100; SSP1-2.6/3-7.0/5-8.5; the 5 ISIMIP GCMs | COG keyless (~490 MB per global layer; read points with `/vsicurl/`). CC BY 4.0 [S] | PROJ (1 km map layer) | ★★ | [V] |
| 110 | **WorldClim 2.1 CMIP6** | Monthly tn, tx, pr, bioclim | 30″–10′ | 2021–2100 in 20-year windows; 4 SSPs; up to 23 GCMs | Keyless. **Non-commercial, no redistribution** | Map only | ★ | [V] |
| 111 | **CIL-GDPCIR**. Planetary Computer `cil-gdpcir-cc-by`, `-cc0` | Daily tasmax, tasmin, pr | 0.25° | Global; 25 GCMs; 4 SSPs; quantile delta mapping against **ERA5**; noleap calendar | STAC (Zarr). CC0 or CC BY by model | PROJ (ERA5-consistent tails) | ★★ | [V] |
| 112 | **LOCA2** (US) | Daily tasmax, tasmin, pr | ~6 km | CONUS; 27 GCMs; SSP2-4.5/3-7.0/5-8.5; trained on Livneh | Download (loca.ucsd.edu †). Public [U] | PROJ (US check) | ★★ US | [S] |
| 113 | **C3S European climate indicators** (`sis-ecde-climate-indicators`) | GDD base 5 °C, frost days, hot days > 30/35/40 °C, growing-season start, end and length, CDD, drought | 0.25° | Europe; ERA5 1940→ plus bias-adjusted EURO-CORDEX RCP4.5/8.5 to 2100 | CDS key. CC-BY | PROJ (EU cross-check) | ★★ EU | [V] |
| 114 | **EURO-CORDEX** (CDS) | T, Tmax/Tmin, rain, RH, solar, wind | 0.11° | Europe; RCP2.6/4.5/8.5 (CMIP5 drivers). CMIP6-driven runs are not yet on the CDS [S] | CDS key. Some RCMs non-commercial [U] | Optional | ★ | [V] |
| 115 | **C3S agroclimatic indicators** (`sis-agroclimatic-indicators`) | 26 indicators (BEDD, frost days, GSL, CDD…). No crop-base GDD, frost dates or ET0 | 0.5° | **CMIP5** (RCPs), 5 GCMs, 30-year periods | CDS. CC-BY | Sanity check only | ★ | [V] |
| 116 | **C3S CMIP6 extreme indices** (`sis-extreme-indices-cmip6`) | 27 ETCCDI indices plus heat stress; a bias-adjusted version | GCM grids 0.5–2.8° | 4 SSPs, ~27 GCMs | CDS. CICERO licence | Cross-check | ★ | [V] |
| 117 | **C3S Atlas / IPCC WGI Interactive Atlas** | Monthly T, rain, frost days, hot days, SPI | 1° (CMIP6); CORDEX | SSP1-1.9 to 5-8.5 | CDS; web app (interactive-atlas.ipcc.ch †) | Communication | ★ | [V] CDS |
| 118 | **Open-Meteo Climate API** | Daily T, RH, rain, wind, solar, ET0 | 10 km (downscaled to ERA5-Land, monthly linear correction) | 1950–2050 only; 7 HighResMIP models; one high-forcing scenario, no SSP choice | Keyless. Free tier non-commercial | Demo only | ★ | [V] |

GAEZ v5 (#43) uses the five ISIMIP3b GCMs with an AgERA5 baseline [S]. **CMIP7:** as of 26 Oct 2026, 10 models have published some data but there is no bias-adjusted or downscaled product, so CMIP7 is not usable yet [S].

### 3.6 Seasonal and short-term forecasts

| # | Source | Gives | Grid | Coverage · issue | Access · licence | Role | ★ | Tag |
|---|---|---|---|---|---|---|---|---|
| 119 | **C3S multi-system seasonal**. [CDS](https://cds.climate.copernicus.eu/datasets/seasonal-monthly-single-levels) | Monthly T2m, Tmax/Tmin, rain; ensemble means and terciles | 1° | Global; leads 1–6 months; hindcasts 1993–2016; ECMWF SEAS5.1 plus ~9 other centres; issued on the 6th (ECMWF) and 10th | CDS key. CC-BY plus an extra licence for non-European systems | SEAS (authoritative) | ★★ | [V] |
| 120 | **Open-Meteo Seasonal API** (SEAS5, EC46) | Monthly T and rain anomalies; daily ET0 and soil moisture | ~36 km | 6–7 months; 51 members; **not bias-corrected** | Keyless. Free tier non-commercial | SEAS (demo) | ★★★ demo | [V] |
| 121 | **NOAA NMME** | Monthly T2m, rain | 1° [U] | Global; up to ~12 months [U]; membership changed in 2026 | IRI Data Library, CPC FTP, keyless | SEAS (US cross-check) | ★★ | [V] |
| 122 | **NOAA CPC outlooks** | Tercile probabilities: 6–10 days, 8–14 days, weeks 3–4, monthly, 3-month | US polygons | US; monthly and weekly | Shapefile and KML, keyless | SEAS (US) | ★★★ US | [V] |
| 123 | **NASA GMAO GEOS-S2S-3** | Coupled sub-seasonal to seasonal forecasts | [U] | Global; released March 2026 | [U] | NASA-branded seasonal context | ★ | [V] release |
| 124 | **ECMWF Open Data** (IFS, AIFS). [data.ecmwf.int](https://data.ecmwf.int/forecasts/) | 2 m T, rain, 10 m wind, radiation… | IFS 0.25° and 0.1° (from 20 Oct 2026); AIFS 0.25° | 4 runs per day to 15 days; only the last ~12 runs kept. **No seasonal products yet** | HTTPS and cloud mirrors, keyless. CC BY 4.0, commercial use allowed | SEAS (short-term) | ★★ | [V] |
| 125 | **NOAA GFS** | Full fields | 0.25° [U] | 16 days [U] | NOMADS, S3, keyless. Public domain | Short-term backup | ★ | [V] |
| 126 | **Open-Meteo Forecast API** | Daily T, rain, ET0; many models | Model-dependent | ~16 days | Keyless. Free tier non-commercial | Demo | ★★★ demo | [V] |

Seasonal skill for rain in mid-latitudes is low (section 6.4). Show seasonal temperature with confidence and seasonal rain as low-confidence. Never feed seasonal output into the 2030/2050 fit score.

### 3.7 Access tools

| Tool | What it gives | Auth | Notes | Tag |
|---|---|---|---|---|
| POWER API v2.10.1 | Point and regional, hourly to climatology | None | Pin `community=AG` (units change with community). Max 20 parameters per request; HTTP 429 on overload. Daily values are in local solar time by default | [V] |
| Open-Meteo archive / climate / seasonal / forecast | ERA5, ERA5-Land (T, RH only), `era5_seamless`, ECMWF IFS 9 km (2017→), CERRA (Europe, to June 2021), `et0_fao_evapotranspiration` | None | Free tier is non-commercial: 600 calls/min, 5,000/hour, 10,000/day; long multi-variable requests count as several calls. `best_match` switches to IFS from 2017, which breaks long-term consistency | [V] |
| `cdsapi` 0.7.7 (new CDS since Sep 2024) | AgERA5, ERA5, ERA5-Land, CERRA, seasonal | Personal token in `~/.cdsapirc` | Accept each dataset's licence on its web page first; the API cannot. Daily-statistics products omit accumulated variables (no rain) | [V] |
| `earthaccess` 0.19.0 | NASA CMR search and download (MERRA-2, IMERG, GLDAS, SMAP) | Earthdata Login | — | [V] |
| Google Earth Engine | `ECMWF/ERA5_LAND/DAILY_AGGR` (to 2026-10-17), `IDAHO_EPSCOR/GRIDMET`, `IDAHO_EPSCOR/TERRACLIMATE` (to 2024-12), `NASA/ORNL/DAYMET_V4`, `UCSB-CHG/CHIRPS/DAILY` (v2), `NASA/GDDP-CMIP6` (stale), `CSIC/SPEI/2_11`, `FAO/WAPOR/3/L1_RET_D`, OpenET | Cloud project | AgERA5 and POWER are not in the official catalogue | [V] |
| ARCO-ERA5 (Google Cloud), NSF NCAR ERA5 (AWS) | Analysis-ready ERA5 Zarr; final to 2026-06-30, ERA5T to 2026-10-19 | Anonymous | Use for bulk regional pulls | [V] |
| Microsoft Planetary Computer | STAC still live, but **climate collections stopped updating** in 2020–2021 (gridMET, Daymet, TerraClimate, ERA5) | None | Do not use for current data | [V] |
| `xclim` 0.62.0 | GDD, frost days, last spring frost, frost-free season, heat spells, CDD, SPI, SPEI | — | Its `FAO_PM98` ET0 is not FAO-56 (10 m wind, sea-level pressure) | [V] |
| `xsdba` / `ibicus` | Bias adjustment: delta change, quantile delta mapping, ISIMIP method | — | `xclim.sdba` is deprecated: use `xsdba` | [V] |
| `pyet` 1.5.0; `refet` 0.5.0 | FAO-56 / ASCE ET0 and ~20 other PET methods | — | `pyet` latitude in radians | [V] |
| `meteostat` 2.1.5 | Station data; v2 API breaks v1 code | None | Filter model-filled rows | [V] |

## 4. Corrections to earlier docs

These supersede the matching lines in the data guide (#1–3, #47) and in `data_sources_audit.md` (rows A1–A3, B3, B13, B16, C "ERA5-Land / AgERA5", C "CHIRPS v3", D7).

1. **#1 POWER.**
   - Latency is ~5 days for meteorology and ~7 days for solar, not 1–2 months. After the MERRA-2 segment ends (now 30 Sep 2026), POWER fills from GEOS-IT. The methodology page still says "GEOS 5.12.4 FP-IT".
   - The CERES delay is over: SYN1deg runs to July 2026 and FLASHFlux was upgraded to v4C on 10 Apr 2025. Solar for 1984–2000 is GEWEX SRB 4.0-IP, not CERES.
   - **There is no ET0 parameter**, which closes audit item B16.
   - New precipitation ×24 bug (section 1).
   - Data v10 (2025-01-02), API v2.10.1. No resolution change.
2. **#2 MERRA-2.** Still produced (data through September 2026). No successor has been released: MERRA-21C and MERRA-3 are not out [S]. Keep it as "use through POWER".
3. **#3 NEX-GDDP-CMIP6.**
   - Coverage is 90°N–60°S, not global.
   - **v2.0** (tech note May 2025, data July 2025) is a full re-release. It reprocessed tasmax and tasmin against a corrected GMFD; a bad patch over central Canada (50–71°N, 100–103°W, Prairie wheat) had leaked into v1.1 and v1.2. It also swaps days where Tmax < Tmin.
   - hurs can reach 105%: clip it to 100% before computing ET0.
   - Bias correction is BCSD against GMFD (1960–2014), not ERA5.
   - Model count: 35 configurations, 34 models (GFDL-CM4 twice). Count it once in ensembles.
   - **Variable gaps in v2.0** [V, from the S3 index]:
     - CMCC-CM2-SR5 has no tas, tasmax or tasmin (old v1.x files still sit in the same folders).
     - CESM2, CESM2-WACCM and IITM-ESM have no tasmax/tasmin.
     - BCC-CSM2-MR and NESM3 have no hurs.
     - Several models miss SSP3-7.0.
   - **Usable models for 1981–2060** with pr, tasmax and tasmin:
     | SSP | Models | Models that also allow Penman-Monteith ET0 |
     |---|---|---|
     | SSP1-2.6 | 29 | 26 |
     | SSP2-4.5 | 30 | 27 |
     | SSP3-7.0 | 25 | 24 |
     | SSP5-8.5 | 31 | 29 |
   - Units: pr is kg m⁻² s⁻¹ (× 86,400 for mm/day). Temperatures are in K. Longitudes run 0–360.
   - Calendars vary: some models use 360- or 365-day years, and IITM-ESM drops a day in years divisible by 5.
4. **#47 AgERA5.** v2.0 (May 2025) replaces v1.1, which is deprecated and no longer updated. v2.0 adds FAO-56 ET0, derived RH min/max and VPD, and fixes rogue Tmin values. Licence is CC-BY-4.0. Wind is still only at 10 m. Latency is ~8 days.
5. **Audit C, CHIRPS.** CHIRPS v3 covers 60°S–60°N, so all of Ukraine is inside. CHIRPS v2 stops at 50°N, which excludes Kyiv and the north.
6. **Audit C, ERA5-Land and AgERA5 "~5× finer than POWER".** Both are 0.1° grids, but both come from 31 km ERA5. Real detail is better than POWER mainly through the topography correction, not five times finer.
7. **Audit D7 risk list.** Replace "CERES delay in POWER solar" with "POWER near-real-time precipitation ×24 bug".

## 5. Recommended stack

### 5.1 By model part

| Need | Global default | US (validated in section 6.3) | Keyless fallback (hackathon) | Why |
|---|---|---|---|---|
| **SD:** monthly T, rain, pan evaporation for RothC | TerraClimate (#59) tmax, tmin, ppt, pet to 2025, then AgERA5 (#47) monthly sums. pan = PET / 0.75. Use the regional station grid instead where one exists (5.2) | gridMET (#71) or Daymet (#72) T and rain. ET0 from FAO-56 on POWER inputs, or gridMET ET0 × ~0.92 | POWER daily (end before GEOS-IT) aggregated to months; FAO-56 ET0 from POWER inputs | POWER and ERA5 monthly T run +0.7 to +1.0 °C warm. In RothC, +1 °C speeds decomposition by ~5% at 25 °C and ~20% at 5 °C (from the RothC temperature function). The bias mostly cancels when rotations are compared on the same field, but not in absolute SOC |
| **ROT:** daily ET0 | AgERA5 v2.0 ET0 (#47) | FAO-56 on POWER inputs (pilot bias ~0%), or gridMET ET0 corrected down 8–10% | Open-Meteo `era5_seamless` ET0 (ERA5 ET0 +6% in the pilot) | gridMET over-reads ET0 (pilot +8%; +10–20% over irrigated cropland in Volk et al. 2026) |
| **ROT:** frost dates, GDD, heat days | Station-based regional grid where one exists (5.2). Elsewhere AgERA5 or ERA5 with a monthly Tmin and Tmax bias correction against the nearest GHCN-D stations | gridMET or Daymet (frost within 1–4 days, GDD within ±2%) | POWER with the same Tmin correction | Uncorrected ERA5, ERA5-Land and POWER Tmin is +0.9 to +2.0 °C warm: first autumn frost 1–3 weeks late, GDD +7–8%. AgERA5 is ERA5-based and likely shares this [U, not tested] |
| **ROT:** seasonal rain, dry spells | Regional station grid. Else CHIRPS v3 (#61, 60°S–60°N; not tested in the pilot); ERA5 last | gridMET, Daymet, PRISM (monthly r 0.98) | POWER (monthly r 0.89) | ERA5 daily rain r 0.64, ~29% too many wet days |
| **ROT:** solar radiation | POWER (#1), best in the pilot (r 0.97) | Same | Same | ERA5 and gridMET read +1.5 MJ m⁻² d⁻¹ high |
| **CH:** current season | ERA5T (~5 days) via ARCO or Open-Meteo; CHIRPS v3 preliminary; POWER temperature (with the rain guard) | gridMET (2 days), PRISM early (1 day) | Open-Meteo `best_match` (IFS, 1 day), display only | — |
| **PROJ:** 2030 and 2050 | NEX-GDDP-CMIP6 v2.0 (#3): monthly deltas per model (additive for T, multiplicative for rain and ET0) on the observed 1991–2020 baseline. Use all usable models (25–31), SSP2-4.5 and SSP5-8.5, 2021–2040 and 2041–2060. Report the median, 10–90% range and model agreement. CCKP (#107) as a zero-compute layer; ISIMIP3b (#108) as a cross-check | Add LOCA2 (#112) | CCKP indices on S3 | Compute indices per model, then aggregate. Use quantile delta mapping (`xsdba`) only where dry-spell structure matters |
| **SEAS** | C3S multi-system (#119) | CPC outlooks (#122) | Open-Meteo seasonal (#120) | Rain is low-confidence in mid-latitudes |
| **VAL** | GHCN-D, GHCNh, ECA&D, national services | USCRN, ACIS, IEM, SCAN; AmeriFlux and OpenET for ET | Same (all keyless except ECA&D terms) | Section 6 |

### 5.2 By country

Best open source per country in `GT/ground_truth_by_country.md`. "Baseline" is the 1991–2020 climatology used for crop fit; "Recent" is 2008 → last month; "Stations" are the validation truth. Future climate is NEX-GDDP-CMIP6 v2.0 (#3) everywhere, with the extra cross-check listed.

| Country / region | Baseline grid | Recent and in-season | ET0 | Stations (VAL) | Future cross-check | Notes |
|---|---|---|---|---|---|---|
| **US** | PRISM 800 m normals (#73); Daymet 1 km (#72) | gridMET (#71, 2 days); PRISM daily | gridMET ET0 (bias-correct) or FAO-56 from gridMET inputs | USCRN (#90), ACIS (#93), IEM (#94), SCAN (#95), GHCN-D (#91); CIMIS, AmeriFlux, OpenET for ET | LOCA2 (#112) | Densest data; the validation region |
| Canada | Daymet (#72) | ECCC stations and CaPA (#76); AgERA5 | AgERA5 | ECCC GeoMet (#76) | — | NEX v2.0 fixed a Prairie temperature artifact |
| Netherlands | E-OBS (#78, non-commercial) or CERRA (#77) | AgERA5; KNMI stations | AgERA5; KNMI Makkink EV24 [U] | KNMI (#83), ECA&D | ECDE (#113) | KNMI key needed |
| Denmark | CERRA (#77) | AgERA5; DMI | AgERA5 | DMI API (#83) | ECDE | DMI keyless |
| Austria | SPARTACUS 1 km (#82) | SPARTACUS (1 day) | WINFORE 1 km (#82) | GeoSphere stations (#82) | ECDE | Best national service in the list |
| France | SIM2 8 km (#81) | SIM2 (daily) | SIM2 Penman-Monteith ETP | Météo-France via data.gouv.fr [U] | ECDE | Licence Ouverte |
| Germany | HYRAS-DE 1 km (#80) | HYRAS (1 day) | DWD FAO ET0 grid 1 km (#80) | DWD CDC daily KL (#80) | ECDE | Radiation grid only to 2020 |
| Spain | AEMET grids to 2022 (#83) or CERRA | AgERA5 | AgERA5 | AEMET OpenData (key) | ECDE | AEMET grids are stale |
| Sweden, Finland, Czechia, Slovakia | CERRA (#77) | AgERA5 | AgERA5 | SMHI, FMI, CHMI, SHMU (#83), all keyless | ECDE | — |
| UK | HadUK-Grid 1 km (#79) | AgERA5 (HadUK-Grid is annual) | AgERA5 | MIDAS Open (CEDA) [U] | ECDE | CEDA login |
| **Ukraine** | ClimUAd 0.1° (#84, to 2020) | CERRA (#77, to Jul 2026), then AgERA5 or ERA5T | AgERA5 | GHCN-D (32 active), GHCNh (Kyiv `UPI0000UKKK`), ECA&D (~26 GTS series) | ECDE (domain coverage [U]); ISIMIP3b | No open feed from Ukrhydrometcenter; E-OBS sparse after 2020 |
| Brazil | BR-DWGD 0.1° (#85, to 2025) | AgERA5, CHIRPS v3 | BR-DWGD ETo; AgERA5 | INMET (#101) | ISIMIP3b | BR-DWGD has no stated licence |
| Argentina | AgERA5, CHIRPS v3 | AgERA5, CHIRPS v3 | AgERA5 | SMN (#101, rolling 365 days) | ISIMIP3b | No open national grid |
| Australia | SILO 0.05° (#86) | SILO (yesterday) | SILO FAO-56 and **pan evaporation** | SILO patched points | ISIMIP3b | Pan evaporation feeds RothC directly |
| India | IMD rain 0.25° (#87); AgERA5 for T | AgERA5, CHIRPS v3 | AgERA5 | GHCN-D (162 active) | ISIMIP3b | IMD 1° temperature too coarse |
| Bangladesh | ENACTS-BMD (#88) [S]; AgERA5 | AgERA5, CHIRPS v3 | AgERA5 | GHCN-D (9 active) | ISIMIP3b | BMD library unreachable |
| Kenya / East Africa | ENACTS-KMD (#88); TAMSAT (#89) | TAMSAT, ARC2, CHIRPS v3 | AgERA5 | GHCN-D (8 active) | ISIMIP3b | Thin station network |
| Any other country | AgERA5 (#47) for T; CHIRPS v3 (#61) for rain inside 60°S–60°N | ERA5T (~5 days) via Open-Meteo or ARCO | AgERA5 | GHCN-D, GHCNh, Meteostat (filtered) | ISIMIP3b | Global default |

### 5.3 Drop or demote

- MERRA-2 directly: use it through POWER.
- WorldClim: non-commercial. Use CHELSA (CC0).
- MSWEP/MSWX and JRA-3Q: non-commercial.
- C3S agroclimatic indicators and EURO-CORDEX on the CDS: CMIP5 only.
- Open-Meteo Climate API beyond a demo: one scenario, 7 HighResMIP models.
- NLDAS-3 until it runs past 2023.
- Planetary Computer and GEE copies of NEX-GDDP, gridMET, Daymet and TerraClimate: stale.
- GSOD and ISD: frozen since August 2025.
- ERA5 `pev` as ET0.
- `xclim` `FAO_PM98` as FAO-56.
- HadEX3: too coarse.

## 6. Validation

The US has the densest open ground truth, so it is the first validation region. The same protocol then runs wherever station data exist.

### 6.1 Ground truth by region

| Region | Weather truth | ET truth | Notes |
|---|---|---|---|
| US | USCRN (#90, reference grade, with solar, RH and wind), GHCN-D (#91), ACIS (#93), IEM (#94), SCAN (#95), NOAA normals (#96) | CIMIS station ET0 (#97), AmeriFlux (#98), OpenET (#22) | Mesonet terms: Kansas needs consent, Oklahoma is paid |
| Canada | ECCC GeoMet (#76) | Canadian AmeriFlux sites in the FLUXNET Shuttle (#98) | — |
| Europe | ECA&D (#99, non-commercial); DWD, GeoSphere, DMI, SMHI, FMI, CHMI, SHMU (#80–83) | ICOS (#98) | National services are keyless and CC BY in most cases |
| Ukraine | GHCN-D (32 active), GHCNh, ECA&D GTS series, OGIMET | None open | Synoptic Tmax/Tmin are not true extremes; synoptic rain can be under-reported [V, NCEI note] |
| Brazil, Argentina | INMET, SMN (#101) | FLUXNET Shuttle [U] | SMN rolls over after ~365 days |
| Australia | SILO patched points (#86), BoM | OzFlux (#98) | — |
| India, Bangladesh, Kenya | GHCN-D (162, 9, 8 active) | — | Too thin for more than a sanity check |

### 6.2 Protocol

1. For each station, take the grid cell (or nearest cell centre) of each candidate product.
2. Align the day definition. USCRN days are local standard time. POWER is local solar time by default. PRISM runs 12:00–12:00 UTC. Some products shift rain by a day. Test daily rain at lags −1, 0 and +1.
3. Compare daily Tmax, Tmin, solar, RH and wind: bias, RMSE and r.
4. Compare what the model actually uses:
   - monthly mean T and monthly rain totals (RothC);
   - season GDD (May–Sep, corn 86/50 °F method);
   - last spring and first autumn frost dates (Tmin ≤ 0 °C);
   - FAO-56 ET0, from station inputs against each product's ET0.
5. Report the median and range across stations, not one site.
6. For future climate, compare the 1995–2014 model distribution with the observed one, never year to year.
7. Outside the US, run the same scripts on GHCN-D, ECA&D or national station data.

### 6.3 US pilot results (USCRN, 2015–2024)

**Setup**
- **Stations:** six USCRN sites in crop regions: Des Moines IA, Champaign IL, Lincoln NE, Oakley KS, Jamestown ND, Merced CA.
- **Candidates,** each at the grid cell of the station, pulled keyless on 26 Oct 2026:
  - POWER (daily API, MERRA-2 period only);
  - ERA5 and ERA5-Land (Open-Meteo archive, local standard time);
  - Daymet V4R1 (single-pixel API);
  - gridMET (THREDDS).
- **Truth:**
  - USCRN daily files for temperature, rain, solar and RH.
  - Station ET0 is FAO-56 (`pyet`) from station Tmax, Tmin, RH max/min and solar, plus daily-mean wind from the 5-minute files (1.5 m, converted to 2 m). Only 2023–2024 were pulled because those files are large.
- **Products' own ET0:**
  - ERA5: Open-Meteo `et0_fao_evapotranspiration`.
  - gridMET: `pet`.
  - POWER: FAO-56 computed from its own inputs.
  - The last row also recomputes every product with wind fixed at 2 m/s, which isolates temperature, humidity and solar errors.
- **Metrics:**
  - Daily rain r is the best of lags −1, 0, +1.
  - GDD uses the corn 86/50 °F method, May–September.
  - Frost dates use Tmin ≤ 0 °C, in years when the station has ≥ 95% of days (7–9 years per site).
  - Months count only when the station has ≥ 90% of days.

**Corn Belt and Plains (IA, IL, NE, KS, ND): median across 5 sites (min to max)**

| Metric | POWER | ERA5 | ERA5-Land | Daymet | gridMET |
|---|---|---|---|---|---|
| Daily Tmax bias, °C | +0.4 (−0.3 to +1.4) | +0.1 (−0.1 to +0.5) | −0.2 (−0.5 to +0.0) | +0.1 (−0.0 to +0.4) | +0.1 (+0.0 to +0.3) |
| Daily Tmax RMSE, °C | 2.1 (1.7 to 2.6) | 1.2 (1.1 to 1.7) | 1.5 (1.4 to 1.9) | 0.8 (0.7 to 1.1) | 1.3 (1.2 to 1.9) |
| Daily Tmin bias, °C | +0.9 (+0.5 to +2.4) | +1.3 (+1.3 to +2.6) | **+2.0** (+1.5 to +3.6) | +0.0 (−0.5 to +0.6) | −0.3 (−0.4 to +1.0) |
| Daily Tmin RMSE, °C | 2.1 (1.8 to 3.5) | 2.0 (1.8 to 3.2) | 2.7 (2.2 to 4.3) | 1.8 (1.5 to 2.1) | 2.2 (2.1 to 2.5) |
| Monthly mean T bias, °C (RothC input) | +0.7 (+0.3 to +1.5) | +0.8 (+0.6 to +1.2) | +1.0 (+0.6 to +1.6) | +0.1 (−0.2 to +0.5) | −0.1 (−0.2 to +0.6) |
| Season GDD bias, % | +7 (+6 to +15) | +8 (+5 to +9) | +8 (+8 to +10) | +2 (−1 to +5) | +0 (−1 to +6) |
| Last spring frost, days (− = too early) | −3 (−8 to −2) | −7 (−8 to −3) | −9 (−11 to −6) | −4 (−6 to +0) | −1 (−10 to −1) |
| First autumn frost, days (+ = too late) | +13 (+2 to +16) | +7 (+2 to +13) | **+18** (+16 to +22) | +2 (+2 to +5) | +1 (−0 to +5) |
| Daily rain r | 0.78 (0.61 to 0.83) | 0.64 (0.54 to 0.72) | — | 0.85 (0.79 to 0.98) | 0.78 (0.75 to 0.83) |
| Monthly rain r | 0.89 (0.81 to 0.94) | 0.82 (0.75 to 0.84) | — | 0.98 (0.89 to 0.98) | 0.98 (0.94 to 0.99) |
| Rain total bias, % | +1 (−5 to +12) | +11 (+3 to +13) | — | +6 (+1 to +12) | +9 (+3 to +11) |
| Wet days (≥ 1 mm), ratio to station | 1.31 (1.27 to 1.38) | 1.29 (1.25 to 1.32) | — | 1.08 (0.99 to 1.12) | 1.06 (1.02 to 1.14) |
| Daily solar bias, MJ m⁻² d⁻¹ | +0.9 (+0.6 to +1.2) | +1.6 (+1.3 to +1.8) | — | −0.1 (−0.7 to +0.3) | +1.5 (+0.9 to +1.8) |
| Daily solar r | 0.97 (0.92 to 0.98) | 0.94 (0.90 to 0.95) | — | 0.88 (0.85 to 0.89) | 0.88 (0.87 to 0.91) |
| Daily wind (2 m) r | 0.88 (0.80 to 0.91) | 0.85 (0.81 to 0.91) | — | — | 0.82 (0.72 to 0.87) |
| ET0 (product's own or FAO-56 on its inputs), bias %, 2023–24 | +0 (−7 to +4) | +6 (−7 to +11) | — | — | +8 (−1 to +14) |
| ET0 RMSE, mm/d, 2023–24 | 0.64 (0.51 to 0.75) | 0.55 (0.42 to 0.80) | — | — | 0.67 (0.57 to 0.76) |
| ET0 with wind fixed at 2 m/s, monthly bias % | −5 (−6 to +2) | +5 (+1 to +11) | — | +1 (−4 to +5) | +9 (+4 to +15) |

"—" means the product has no such variable: ERA5-Land through Open-Meteo has no rain, solar or wind, and Daymet has no wind.

**Merced, California (a cold-air site in the Central Valley).** Every grid is too warm at night, so frost-based indices fail:

| Metric | POWER | ERA5 | ERA5-Land | Daymet | gridMET |
|---|---|---|---|---|---|
| Daily Tmin bias, °C | +4.4 | +5.9 | +5.4 | +3.4 | +2.4 |
| Season GDD bias, % | +21 | +30 | +27 | +16 | +13 |
| Last spring frost, days | −48 | −51 | −48 | −53 | −42 |
| First autumn frost, days | +36 | +40 | +55 | +44 | +23 |

Frost dates here rest on 1–3 years, because frost is rare in the grids.

**What it means**
1. **Temperature indices need a station-based source or a Tmin correction.** ERA5, ERA5-Land and POWER nights are 1–2 °C too warm, matching the literature (ERA5 Tmin too high, diurnal range too small). That moves the first autumn frost by 1–3 weeks and GDD by 7–8%. ERA5-Land's finer 0.1° grid does not help: it is worse than ERA5 for Tmin.
2. **For daily and monthly rain, use station-based grids where they exist.** ERA5 is the weakest (daily r 0.64, ~29% too many wet days). POWER's corrected rain is better (monthly r 0.89) but drizzles too.
3. **POWER is the best solar source** of the five (r 0.97, +0.9 MJ). With FAO-56 on its own inputs, its ET0 is unbiased at these sites.
4. **gridMET ET0 reads ~8% high** even at these grassland sites; the literature finds 10–20% over irrigated cropland. Correct it, or compute FAO-56 from its inputs.
5. **Microclimate is beyond every grid.** At Merced, night-time cold-air pooling makes the station 2–6 °C colder than all products. Frost-pocket fields need a farmer's input or a local station.

**Caveats**
- **Daymet and gridMET are partly in-sample.** USCRN stations are in GHCN-Daily and PRISM's network, so they were probably inputs. Daymet's own cross-validation (out of sample) gives a daily MAE of 1.5 °C for Tmax and 1.8 °C for Tmin [V]; here it was 0.6 and 1.3 °C.
- **Not tested:**
  - AgERA5 and CERRA, which need a CDS key.
  - CHIRPS, TerraClimate and PRISM, for time.
- **The sites are grassland, not irrigated fields.** Gridded ET0 errors over irrigated cropland are larger.
- **One cell against one point.** Rain at a point is noisier than over a field, so daily rain r understates how well a product describes a field's rain.
- **POWER requests ended on 2024-12-31,** so the ×24 rain bug did not apply.

The scripts and raw downloads are kept outside the repo. Every input URL pattern is in section 8, so the run can be repeated for any other station network.

### 6.4 Published accuracy

| Comparison | Result | Source | Tag |
|---|---|---|---|
| POWER (older GEOS-4) vs 855 US COOP stations | Tmax r² 0.88, RMSE 4.1 °C; Tmin r² 0.88, RMSE 3.7 °C. Averages of 8+ days: RMSE < 2.7 °C | White et al. 2008, AFM | [S] |
| POWER solar vs 295 US stations | r 0.85–0.95; 1.1 MJ m⁻² d⁻¹ low on average | White et al. 2011, Agron. J. 103:1242 | [V] abstract |
| POWER vs Brazilian stations (daily) | Tmax R² 0.57, Tmin 0.72, solar 0.71; much better at 10-day scale | Monteiro et al. 2018, IJC 38:1571 | [V] abstract |
| FAO-56 ET0 from POWER, Portugal | RMSE up to 1.41 mm/d (overestimates); ≤ 0.77 after local bias correction | Rodrigues & Braga 2021, Agronomy 11:2077 | [V] abstract |
| ERA5 rain vs 5,637 stations | General wet bias; misses the highest totals | Lavers et al. 2022, QJRMS | [V] |
| ERA5 temperature vs GHCN | Tmax too low, Tmin too high, so the diurnal range is too small | Atmosphere 2024, 15:93 | [V] |
| ERA5-Land ET0 | Sicily (39 stations): daily RMSE 0.4–1.3 mm/d. Greece: ~35% below station ET0 | Ippolito et al. 2024 (AWM); Geographies 2023, 3:26 | [V] |
| E-OBS, ERA5, ERA5-Land in Ukraine (178 stations, 1950–2014) | Similar heat-wave skill; heat-wave counts differ by up to 6 events per year between datasets | Atmosphere 2025, 16:289 | [V] |
| Daymet V4 cross-validation | Daily MAE: Tmax 1.52 °C, Tmin 1.78 °C, rain 1.2–1.6 mm/d | Thornton et al. 2021, Sci. Data 8:190 | [V] |
| gridMET ET0 vs 793 agricultural stations | **+10–20% at most cropland sites**, mainly from wind | Volk et al. 2026, AWM 110647 | [S] abstract |
| OpenET vs 152 towers | Cropland MAE 15.8 mm/month (17%), r² 0.9 | Volk et al. 2024, Nature Water 2:193 | [V] |
| Rain products vs 76,086 gauges; CONUS radar-gauge | Products that ingest daily gauges (CPC, MSWEP) do best; ERA5 is the best uncorrected product over CONUS | Beck et al. 2017, HESS 21:6201; 2019, HESS 23:207 | [V] |
| CHIRPS vs ~1,200 East African gauges | Better than ARC2 and slightly better than TAMSAT at dekadal and monthly scales; TAMSAT better daily | Dinku et al. 2018, QJRMS | [V] |
| Eight US gridded products | The best product varies by ecoregion; finer grid ≠ more accurate | Behnke et al. 2016, Ecol. Appl. 26(5) | [S] |
| Seasonal forecast reliability | Summer dry-event forecasts for northern Europe and parts of North America are in the lowest category ("dangerously useless"); temperature is mostly category 4 of 5 | Weisheimer & Palmer 2014, J. R. Soc. Interface 11:20131162 | [V] |
| Ensemble size | ≥ 13 models are needed to capture > 80% of the CMIP range in 75% of regions and seasons | McSweeney & Jones 2016, Climate Services | [S] |
| CMIP6 crop signal | Global maize at the end of the century under SSP5-8.5: −24% (CMIP5-based: +1%); wheat +18% | Jägermeyr et al. 2021, Nature Food 2:873 | [S] |

### 6.5 What to claim

**Credible**
- **A 1991–2020 climatology of temperature indices** where a station-based grid exists (US, Germany, Austria, France, UK, Brazil, Australia; Ukraine to 2020): GDD within a few percent, frost dates within about a week.
- **Monthly T and rain as RothC inputs for comparing rotations on the same field.** A shared climate bias mostly cancels between rotations.
- **Future change as an ensemble range** (median, 10–90%, model agreement) for 2021–2040 and 2041–2060.
- **ET0 within ~10%** after a bias check against stations.

**Not credible**
- **Field microclimate:** frost pockets, cold-air drainage, slope and aspect. The Merced station was 2–6 °C colder at night than every grid.
- **Daily rain on a specific field.** Daily r is 0.64–0.87 even in the US.
- **Frost dates or GDD from uncorrected reanalysis.** They are 1–3 weeks and 7–8% off.
- **Absolute SOC trends driven by uncorrected reanalysis temperature.** +1 °C changes RothC decomposition by ~5–20%, more in cool months.
- **Seasonal rain outlooks in mid-latitudes; single-model projections; any CMIP6 value for a specific past year.**
- **POWER rain from any request that touches GEOS-IT days.**

## 7. Pitfalls checklist

1. **POWER precipitation ×24** for any request that touches GEOS-IT days. End requests at the last MERRA-2 month and check `header.sources`.
2. **POWER monthly endpoint** gives PRECTOTCORR as a mean in mm/day, not a monthly total. Month "13" is the annual value.
3. **POWER units depend on `community`** (solar in MJ for AG, kWh for RE, W/m² for SB).
4. **Packed values.** gridMET and TerraClimate NCSS CSV return packed integers: apply `scale_factor`/`add_offset` from the `.das`. Example: gridMET Tmax "633 K" is 283.3 K.
5. **Open-Meteo `era5_land`** returns no rain, radiation, wind or ET0. Use `era5_seamless`.
6. **Day definitions differ.** USCRN uses local standard time, POWER local solar time, PRISM 12:00–12:00 UTC, gridMET follows PRISM-style days for rain [U], and Daymet uses 365-day years. Daily rain correlations depend on this; monthly totals barely do.
7. **Wind height.** gridMET, AgERA5, ERA5 and NEX-GDDP wind is at 10 m (× 0.748 for 2 m). POWER WS2M is at 2 m but is a poor input (Portugal and Mexico studies).
8. **ET0 sources do not mix.** AgERA5 ET0, gridMET ET0 and your own FAO-56 differ by 10–20%. Pick one per series, and bias-correct gridMET over cropland.
9. **RothC evaporation.** Feed pan = ET0 / 0.75 in mm/month, or PET with `pE = 1`, not both. CRU `pet` is mm/day.
10. **Version mixing.** Do not mix AgERA5 v1.x with v2.0, CHIRPS v2 with v3, IMERG V06 with V07, or NEX-GDDP v1.x with v2.0. NEX S3 folders hold all versions side by side.
11. **ERA5T is preliminary.** It can change; for example, July–October 2024 was revised after a snow-depth fix.
12. **CMIP6 historical runs and 2015–2026 are simulations**, with no year-to-year match to reality. Never use them for past seasons. Compute indices per model, then aggregate; never count heat days on an ensemble-mean series.
13. **Grid spacing is not real resolution.** A 10–100 ha field is smaller than any cell. TerraClimate, CHELSA and WorldClim at 1–4 km are statistical downscaling. Correct temperature for elevation (~6.5 °C/km) when the field differs from the cell elevation; POWER returns the cell's mean elevation.
14. **Monthly climatologies underestimate GDD and the frost-free season** when mean T is near the base. Use daily data.
15. **Ready-made indices are not crop-specific.** Fixed bases (5 °C in ECDE, 0/5/10 °C in CHELSA) and annual counts, not counts in the flowering window.
16. **Seasonal hindcast climatology (1993–2016)** differs from the 1991–2020 baseline. Compute anomalies against the model's own hindcast.
17. **Station feeds roll over or get remapped.** SMN keeps ~365 days and DWD "recent" ~500 days [U], so archive them. NCEI moved Kyiv from GHCN-D `UPM00033345` (ends 2025-08-24) to GHCNh `UPI0000UKKK`.
18. **Meteostat fills gaps with model forecasts.** Its Kyiv 2026 file contains only DWD MOSMIX rows.
19. **Keys and limits.** CDS needs a token and licence acceptance per dataset. KNMI's anonymous key expires 2027-08-01. AEMET daily requests are capped at 6 months. PRISM allows 2 downloads per file per day. Open-Meteo's free tier is non-commercial.
20. **NOAA service churn.** NCEI ADS was degraded through 30 Oct 2026. GSOD and global-hourly queries for dates after August 2025 return an empty list, not an error.

## 8. Access recipes

All tested keyless on 26 Oct 2026 unless marked.

```text
# NASA POWER daily point (end before the GEOS-IT period to avoid the ×24 rain bug)
https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M,T2M_MAX,T2M_MIN,T2MDEW,RH2M,WS2M,ALLSKY_SFC_SW_DWN,PS,PRECTOTCORR&community=AG&longitude=-93.29&latitude=41.55&start=20150101&end=20260930&format=JSON
# POWER 1991–2020 climatology, and the parameter list
https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=T2M,PRECTOTCORR&community=AG&longitude=-93.29&latitude=41.55&start=1991&end=2020&format=JSON
https://power.larc.nasa.gov/api/system/manager/parameters?community=AG&temporal=daily

# Open-Meteo archive (ERA5 and ERA5-Land; local standard time via a fixed-offset zone)
https://archive-api.open-meteo.com/v1/archive?latitude=41.55&longitude=-93.29&start_date=2015-01-01&end_date=2024-12-31&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,shortwave_radiation_sum,et0_fao_evapotranspiration&models=era5,era5_land&timezone=Etc%2FGMT%2B6
# Open-Meteo seasonal (SEAS5 monthly anomalies) and climate (HighResMIP; dates after 2050 return HTTP 400)
https://seasonal-api.open-meteo.com/v1/seasonal?latitude=40.0&longitude=-88.2&monthly=temperature_2m_anomaly,precipitation_anomaly
https://climate-api.open-meteo.com/v1/climate?latitude=40.0&longitude=-88.2&start_date=2041-01-01&end_date=2050-12-31&models=EC_Earth3P_HR,MRI_AGCM3_2_S,MPI_ESM1_2_XR&daily=temperature_2m_max,temperature_2m_min,precipitation_sum

# Daymet single pixel (North America)
https://daymet.ornl.gov/single-pixel/api/data?lat=41.55&lon=-93.29&vars=tmax,tmin,prcp,srad,vp,dayl&start=2015-01-01&end=2024-12-31&format=csv

# gridMET point (values are packed: read scale_factor/add_offset from the .das)
http://thredds.northwestknowledge.net:8080/thredds/ncss/agg_met_pet_1979_CurrentYear_CONUS.nc?var=daily_mean_reference_evapotranspiration_grass&latitude=41.55&longitude=-93.29&time_start=2024-01-01T00:00:00Z&time_end=2024-12-31T00:00:00Z&accept=csv
http://thredds.northwestknowledge.net:8080/thredds/dodsC/agg_met_pet_1979_CurrentYear_CONUS.nc.das

# TerraClimate monthly point (× 0.1)
http://thredds.northwestknowledge.net:8080/thredds/ncss/TERRACLIMATE_ALL/data/TerraClimate_pet_2025.nc?var=pet&latitude=50.45&longitude=30.52&temporal=all&accept=csv

# USCRN daily file and the 5-min file with wind (column header in HEADERS.txt)
https://www.ncei.noaa.gov/pub/data/uscrn/products/daily01/2024/CRND0103-2024-IA_Des_Moines_17_E.txt
https://www.ncei.noaa.gov/pub/data/uscrn/products/subhourly01/2024/CRNS0101-05-2024-IA_Des_Moines_17_E.txt

# GHCN-Daily via NCEI ADS; GHCNh hourly
https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations=UPM00033429&startDate=2025-01-01&endDate=2026-10-26&dataTypes=TMAX,TMIN,PRCP&units=metric&format=json
https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2026/psv/GHCNh_UPI0000UKKK_2026.psv

# RCC-ACIS station data with GDD base 50 °F; US normals with frost dates
https://data.rcc-acis.org/StnData?sid=USW00014939&sdate=2024-06-01&edate=2024-06-03&elems=maxt,mint,pcpn,gdd50&output=json
https://www.ncei.noaa.gov/access/services/data/v1?dataset=normals-annualseasonal-1991-2020&stations=USW00014939&format=json

# NEX-GDDP-CMIP6 v2.0: point CSV from NCCS THREDDS (lon 0–360), file pattern on S3, version index
https://ds.nccs.nasa.gov/thredds/ncss/grid/AMES/NEX/GDDP-CMIP6/ACCESS-CM2/ssp245/r1i1p1f1/tasmax/tasmax_day_ACCESS-CM2_ssp245_r1i1p1f1_gn_2040_v2.0.nc?var=tasmax&latitude=40.0&longitude=271.8&time_start=2040-01-01&time_end=2040-12-31&accept=csv
s3://nex-gddp-cmip6/NEX-GDDP-CMIP6/{model}/{scenario}/{variant}/{var}/{var}_day_{model}_{scenario}_{variant}_{grid}_{year}_v2.0.nc
https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com/index_v2.0_md5.txt

# World Bank CCKP: frost-day anomaly 2040–2059, SSP2-4.5, ensemble median
https://wbg-cckp.s3.us-west-2.amazonaws.com/data/cmip6-x0.25/fd/ensemble-all-ssp245/anomaly-fd-annual-mean_cmip6-x0.25_ensemble-all-ssp245_climatology_median_2040-2059.nc

# Europe: DWD daily FAO ET0 grid, GeoSphere WINFORE ET0, ECA&D station source list
https://opendata.dwd.de/climate_environment/CDC/grids_germany/daily/evaporation_fao/grids_germany_daily_evaporation_fao_2026_v1.1.nc
https://dataset.api.hub.geosphere.at/v1/timeseries/historical/winfore-v2-1d-1km?parameters=ET0&start=2026-10-15&end=2026-10-25&lat_lon=48.2,16.37&output_format=csv
https://knmi-ecad-assets-prd.s3.amazonaws.com/download/ECA_blend_source_tx.txt

# Australia: SILO FAO-56 ET0 grid (S3)
https://silo-open-data.s3.ap-southeast-2.amazonaws.com/Official/annual/et_short_crop/2026.et_short_crop.nc
```

AgERA5 through the CDS (needs a token; request fields match the API form, not run here):

```python
import cdsapi
cdsapi.Client().retrieve("sis-agrometeorological-indicators", {
    "variable": "reference_evapotranspiration", "version": "2_0",
    "year": "2024", "month": "06", "day": ["01", "02"],
    "area": [41, -97, 40.5, -96.5]}, "et0.zip")
```

## 9. Sources

Grouped by provider. Section 6.4 gives the papers.

- **NASA:** POWER (power.larc.nasa.gov docs, release guide, parameter manager API, live calls); NCCS NEX-GDDP-CMIP6 page and v2 tech note (nccs.nasa.gov/wp-content/uploads/2025/06/NEX-GDDP-CMIP6-v2-Tech_Note.pdf); S3 index; Daymet (daymet.ornl.gov, cross-validation PDF); NLDAS-3 (ldas.gsfc.nasa.gov/nldas/v3, `s3://nasa-waterinsight`); GMAO MERRA-2 and GEOS-S2S-3 pages.
- **Copernicus / ECMWF:**
  - CDS catalogue and process API (AgERA5, ERA5, ERA5-Land, CERRA, E-OBS, seasonal, ECDE, agroclimatic and CMIP6 indices, Atlas).
  - ECMWF forum note on AgERA5 v1.1 deprecation; ERA6 announcement (climate.copernicus.eu, 6 Mar 2026); ECMWF parameter 228251 (`pev`).
  - ECMWF open data (data.ecmwf.int); ARCO-ERA5 metadata.
- **NOAA:**
  - NCEI: USCRN, GHCN-Daily status and inventory, GHCNh, Access Data Service docs and alerts, US normals, nClimGrid-Daily.
  - NESDIS notices on ISD and GSOD (2026-06-23); CPC NMME, outlooks and FTP; PSL CPC Unified; GFS on S3.
- **Other US:** gridMET THREDDS and GEE page; PRISM notices (2025-03-27, 2025-10-01) and web-service PDF; RCC-ACIS; Iowa Environmental Mesonet; NRCS SCAN API; Kansas and Oklahoma mesonet terms; AmeriFlux data policy; FLUXNET Shuttle (data.fluxnet.org).
- **Europe:** ECA&D data policy and S3 metadata; DWD CDC; GeoSphere data hub; data.gouv.fr SIM2; CEDA HadUK-Grid; AEMET, KNMI, DMI, SMHI, FMI, CHMI and SHMU open-data endpoints; JRC drought observatories directory and licence.
- **Ukraine:** uhmi.org.ua (ClimUAd); meteo.gov.ua.
- **Other regions:** BR-DWGD (GitHub, project site); INMET; SMN; SILO (longpaddock.qld.gov.au, `silo-open-data` S3); AGCD (NCI THREDDS); IMD Pune; TAMSAT; ARC2; KMD ENACTS.
- **Global products:** TerraClimate THREDDS; CRU TS 4.10; CHC (CHIRPS v3, CHIRTS); GloH2O (MSWEP, MSWX); CHELSA; WorldClim; GDEX JRA-3Q; hPET (data.bris.ac.uk); GLEAM; FAO WaPOR API; SPEI on GEE; HadEX3.
- **Projections:** World Bank CCKP (S3, GitHub, API); ISIMIP (fact sheet, files.isimip.org); CHELSA CMIP6 object store; Planetary Computer STAC (CIL-GDPCIR); LOCA2 [S]; Open-Meteo docs and terms; CMIP7 availability tracker (climate-resource.com) [S].
- **RothC and FAO-56:** Rothamsted RothC description (Feb 2024) and data-requirements summary; RothC v2.1.1 code (Zenodo 17454357); FAO GSOCseq scripts (github.com/FAO-SID/GSOCseq); FAO-56 chapters 3–4 (fao.org/4/x0490e/x0490e07.htm, x0490e08.htm).
- **Libraries:** PyPI pages for cdsapi, earthaccess, xclim, xsdba, ibicus, pyet, refet, meteostat, openmeteo-requests.
