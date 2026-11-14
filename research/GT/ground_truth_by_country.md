# Open ground truth by country (research date 2026-10-23)
Legend: VERIFIED = seen on a fetched/search-returned primary or catalog page this session. UNVERIFIED = from background knowledge or not confirmed. Searches were shallow (one pass); download URLs for national portals need a click-through check.

## Key global catalogue (biggest find)
Fields of The World "harmonized-field-data" on Source Cooperative: https://source.coop/ftw/harmonized-field-data
67 collections (51 crop-field collections with declared crop per parcel per year, 16 field-block only). fiboa GeoParquet. License = original provider's. VERIFIED table (fetched):
- NL `nl` 2009-2026 CC0 | DK `dk` 2008-2026 CC0 | AT `at` 2015-2025 CC-BY-4.0 | SE `se` 2015-2025 CC0 | FR `fr` 2015-2024 ("other" licence; Licence Ouverte presumed) | BE-Flanders 2008-2026 | BE-Wallonia 2015-2023 CC-BY | FI 2020-2025 | EE 2015-2024 | LV 2015-2025 | CZ 2019-2026 CC0 | SK 2018-2026 CC0 | SI 2019-2024 | HR 2011-2024 | IE 2022-2024 + LPIS 2017-2025 | PT 2017-2023,2025 | CH 2017-2026 | LT 2024-25 | PL 2025-26 | IT Tuscany 2016-2022 (gaps), South Tyrol
- Germany by state: Brandenburg/Berlin crop fields 2010-2023,2026 (DL-DE-BY-2.0); Baden-Wurttemberg 2018-2022; Lower Saxony crop fields 2025 only; Saarland, Bavaria 2026; field-blocks only (no crop) for NRW, Hesse, Saxony, SH, Saxony-Anhalt, Thuringia, MV
- Spain: national `es` declared crops 2021,2022,2023,2025 (CC-BY-4.0); many autonomous regions mostly single recent years; Cantabria 2010-2025, Galicia 2014-2026
- Outside EU: US California (LandIQ/CA SCM) 2014-2024 CC0; US USDA-cropland-derived 2017-2024; Japan 2021-2026; NZ 2017, 2020; Brazil CONAB 2026 only (CC-BY-NC)
- No collection for UK, Ukraine, Canada, Australia, Argentina, India, Bangladesh, Africa.
Other global:
- FTW benchmark (24 countries, 70k Sentinel-2 chips w/ field masks, no crop type): https://source.coop/kerner-lab/fields-of-the-world ; paper arXiv 2409.16252. Separate "Global FTW" model-predicted ~3.2B field polygons, 195 countries, 2024-25 (AI predicted, not crop type) https://source.coop/ftw/global-data (VERIFIED via search snippet).
- fiboa data repo: https://github.com/fiboa/data (older listing; moved to FTW org)
- EuroCrops v1: 16 EU countries, mostly 2021 only, HCAT taxonomy (https://arxiv.org/pdf/2302.10202). EuroCrops v2.0 (ESSD preprint essd-2025-752, https://essd.copernicus.org/preprints/essd-2025-752/): 18 paying agencies, min 3 years each, 2008-2023, ~47M parcels, 21 Mha, HCAT4. Final per-country year list not confirmed.
- WorldCereal harmonized reference data (point/polygon labels, 2017+; CC-BY/CC-BY-SA/CC-BY-NC subsets): https://zenodo.org/records/7593734 ; extended 2025 version DOI 10.5281/zenodo.17288873 (licence UNVERIFIED).
- GEOGLAM / CropHarvest (crop labels, Kenya etc.): not fetched, UNVERIFIED.

## Summary table
| Region | Crop history (field level) | Soil incl. repeat monitoring | Yields | Futures | GT score |
|---|---|---|---|---|---|
| US | CDL 30m 2008+, CSB 8-yr polygons | SSURGO; NRCS lab data (known) | NASS county | CBOT/CME corn, soy, wheat, KC/MGEX | 5 |
| Netherlands | BRP crop parcels 2009-2025, CC0, PDOK API | BIS/Bodemkaart (UNVERIFIED), LUCAS | CBS (UNVERIFIED) | Euronext (wheat, corn, rapeseed); NL not main | 4.5 |
| Denmark | Marker/IMK parcels 2008-2026 CC0 | Danish SOC maps (Adhikari 2014 paper; AU Peat2022 10m); farm-level soil tests not open | Stat. Denmark (UNVERIFIED) | Euronext | 4 |
| Austria | INVEKOS 2015-2025 CC-BY | eBod soil map (UNVERIFIED) | Statistik Austria (UNVERIFIED) | Euronext, Vienna n/a | 4 |
| France | RPG 2015-2024 parcels/ilots (Licence Ouverte; crop group per island, not per field) | RMQS 2,240 sites 16km grid, 15-yr cycle (RMQS1 open on Gis Sol dataverse; RMQS2 in progress); BDAT canton nutrient analyses (UNVERIFIED) | Agreste (UNVERIFIED) | Euronext MATIF home market | 4.5 |
| Germany | Patchwork: BB 2010-2023, BW 2018-22, others block-only or single year | BZE-LW agricultural soil inventory 3,104 sites 8x8km 2009-2018 (open, CC-BY, OpenAgrar), repeat inventory underway (no data released found) | Destatis/Landkreis (UNVERIFIED) | Euronext, EEX | 3.5 |
| Spain | Declared crops 2021-23,25 national + regions | LUCAS; national soil map coarse (UNVERIFIED) | MAPA (UNVERIFIED) | Euronext/MEFF olive no | 3 |
| Sweden/Finland/Czechia/Slovakia | 2015-2025 (SE CC0) | LUCAS | national | Euronext | 3.5-4 |
| UK (England) | CROME 2016-2024 hex cells, OGL, ~50 crops | Countryside Survey, NSI (UNVERIFIED) | Defra farm stats (UNVERIFIED) | ICE UK feed wheat (UNVERIFIED) | 3 |
| Canada | AAFC ACI 30m 2009-2025, OGL | SLC v3.2/2.2 polygons (OGL); 100m soil grids (under review) | StatCan (UNVERIFIED) | ICE canola, MGEX/ICE wheat | 4 |
| Ukraine | No official open; Kussul-method 2019-2024 10m rasters (World Bank package, host UNVERIFIED); Zenodo 2020 10m map; WorldCereal 2021 | Agrochemical certification rounds (humus 3.16% 2015, 3.07% 2020 national averages; raw data not open) | Ukrstat oblast (UNVERIFIED) | no domestic; CBOT/Euronext proxy | 2.5 |
| Brazil | MapBiomas Col.10 30m soybean/crops annual (verify); CONAB 2026 fields (NC licence) | EMBRAPA (UNVERIFIED) | IBGE PAM municipal annual via SIDRA | B3 soy/corn (UNVERIFIED) | 3.5 |
| Argentina | INTA Mapa Nacional de Cultivos 2018/19-2022/23 (5 campaigns; INTA.GEO, repository, Zenodo) | INTA soil maps (UNVERIFIED) | MAGyP dept-level (UNVERIFIED) | Matba-Rofex (UNVERIFIED) | 3.5 |
| Australia | CLUM 50m land use (not crop type), CC-BY; 2023 update | SLGA 90m grids (UNVERIFIED) | ABARES (UNVERIFIED) | ASX wheat (UNVERIFIED) | 2.5 |
| India | AgriFieldNet 4 states labels only | Soil Health Card nutrient dashboard 12 params, village-level, 2023-25 (mirror: India Data Portal; official https://soilhealth.dac.gov.in/nutrient-dashboard) | District via DES (UNVERIFIED) | NCDEX (UNVERIFIED) | 2.5 |
| Bangladesh | none found | SRDI Upazila Nirdeshika PDFs only | BBS (UNVERIFIED) | none | 1.5 |
| Kenya/SSA | PlantVillage W. Kenya 2019 field polygons; Lacuna EotG (8 counties, crop mgmt/yield); Lacuna Africa field polygons 42k 2017-23 | iSDA/ISRIC (UNVERIFIED) | KNBS (UNVERIFIED) | none (NCPB; AFEX) | 2 |

## Notes per country
### US
Already known. Add: FTW also hosts USDA-cropland-derived fiboa 2017-2024 and California 2014-2024.
### Netherlands (strongest EU)
BRP gewaspercelen by RVO, one dataset/yr (reference date 15 May), 2009-2025 final + 2026 concept. API https://api.pdok.nl/rvo/gewaspercelen/ogc/v1/collections ; fiboa mirror https://source.coop/ftw/harmonized-field-data/nl ; licence CC0 on mirror, PDOK says Public Domain Mark (minor discrepancy). Crop code per parcel incl. fine crop detail. Soil: BRO/BIS NL not verified.
### Denmark
fiboa `dk` 2008-2026 CC0 (VERIFIED). Soil: Adhikari et al. 2014 PLOS ONE https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4138211/ SOC maps 5 depths; AU peat/topsoil OC map 10 m. Livestock-heavy, N-balance data (Danish N norms) UNVERIFIED.
### Austria
fiboa `at` 2015-2025 CC-BY-4.0 (AMA INVEKOS). Good decade history.
### France
fiboa `fr` 2015-2024; data.gouv RPG https://www.data.gouv.fr/datasets/rpg-2020-registre-parcellaire-graphique/informations (national, Licence Ouverte 2.0). Note: RPG is anonymised "ilots" with majority crop group; per-parcel detailed crop (2015+). Soil: RMQS https://eng-info-et-sols.val-de-loire.hub.inrae.fr/projects-of-the-unit/programmes-of-the-gis-sol/rmqs — 2,240 sites, resampled every ~15 years (RMQS2 campaign 2016-~2028), measured SOC, N, pH, P, etc. Best repeat soil monitoring that is actually open (RMQS1; RMQS2 partial).
### Germany
Fragmented (federal). Soil: Thuenen BZE-LW https://www.thuenen.de/en/thuenen-topics/soil/profilviewer-der-bze-landwirtschaft ; core data on OpenAgrar; agris record https://agris.fao.org/search/en/records/67a0c70120478411b0271ae4; repeat inventory running, data not released.
### Spain
Declared crops national dataset 2021-2023, 2025 (fiboa `es`), regions with single years. Recent years only: rotation inference weak.
### Other EU
Best multi-year: Belgium-Flanders (2008-2026), Sweden, Estonia, Latvia, Czechia, Slovakia, Croatia, Finland, Lithuania. EuroCrops v2 consolidates 2008-2023 for 18 agencies.
### UK
CROME England 2016- (Sentinel-1/2 classified, hexagon cells, OGL; data.gov.uk e.g. https://www.data.gov.uk/dataset/crop-map-of-england-crome-2017-complete ; 2019 on Defra DSP). Ground observation points released too. Wales/Scotland/NI not checked.
### Canada
AAFC Annual Crop Inventory https://open.canada.ca/data/en/dataset/ba2645d5-4458-414d-b196-6303ac06c1c9 ; 30 m (56 m 2009-10); GEE AAFC_ACI 2009-2025; OGL-Canada. Soil: SLC https://open.canada.ca/data/en/dataset/5ad5e20c-f2bb-497d-a2a2-440eec6e10cd (polygon-level attributes incl. organic C by layer, not repeated). Strong second demo after US.
### Ukraine
Kussul-method annual winter/summer crop maps 2019-2024 referenced in World Bank reproducibility package (https://reproducibility.worldbank.org/catalog/375 ; WB dataset 0066913; CC-BY 3.0 IGO linked; maps hosting is Google Drive/GEE: UNVERIFIED accessibility). Zenodo 2020 10 m map https://zenodo.org/records/11065080. Soil: certification humus averages https://sdg.stat.gov.ua/15-3-1 (2 values only publicly).
### Brazil
MapBiomas Collection 10 (annual 30 m; soybean class 39, second-crop info: ~95% of 2nd-crop corn follows soy; 65% of 2024 agriculture = first-crop soy) https://brasil.mapbiomas.org/en/ ; GEE project mapbiomas-public brazil_lulc_v1. Third-party Source.coop copy https://data.source.coop/tristangruppwri/mapbiomas/mapbiomas-brazil/AGENTS.md. Caveat: a JAXA paper finds double-crop regions poorly represented. Yields: IBGE PAM municipal via SIDRA https://sidra.ibge.gov.br/pesquisa/pam/tabelas . CONAB mapping per crop/state (portal; licence UNVERIFIED).
### Argentina
INTA MNC 5 campaigns 2018/19-2022/23, 5th: https://www.argentina.gob.ar/noticias/presentan-el-quinto-mapa-nacional-de-cultivos-extensivos ; report https://repositorio.inta.gob.ar/handle/20.500.12123/16522 ; STAC mirror https://data.source.coop/nlebovits/pergamino-ide/ambiente-y-agro/inta_mnc_2022_invierno/collection.json (exists, inta_mnc_2022). Summer+winter seasons separate = seasonal rotation signal.
### Australia
CLUM 50 m https://data.gov.au/data/dataset/clumc-dec2020 CC-BY 4.0 (land use, "cropping" class; not crop type). No open crop-type annual map found. SLGA not confirmed.
### India
AgriFieldNet (Radiant/IDinsight, 4 states, 2022) https://source.coop/radiantearth/agrifieldnet-competition. Soil Health Card: https://ckandev.indiadataportal.com/dataset/soil-health-card (2023-25 village level) — cycles every 2 years so mini repeat monitoring. Official portal dashboards https://soilhealth.dac.gov.in.
### Bangladesh
Only PDF upazila guides (SRDI). Poor for this product.
### Kenya / SSA
Lacuna EotG https://source.coop/lacuna/eyes-on-the-ground (CC-BY-SA-4.0, 8 counties). Radiant african-crops-kenya-02 (PlantVillage W. Kenya 2019) https://data.source.coop/radiantearth/african-crops-kenya-02/Documentation.pdf. Lacuna agriculture index https://lacunafund.org/datasets/agriculture/. Single-season labels, no multi-year history.

### Futures (mostly UNVERIFIED beyond Euronext)
Euronext (Paris MATIF): milling wheat, corn, durum, rapeseed (verified via euronext.com). CBOT/KC/MGEX/CME: corn, soy, wheat, ZL/ZM. ICE: canola (Canada), UK feed wheat (UNVERIFIED), sugar, cotton. B3 (soy, corn), Matba-Rofex (soy, corn, wheat), ASX (wheat east coast), NCDEX (limited), Ukraine no domestic exchange (use Euronext/CBOT/Black Sea FOB indices). API data access (Yahoo/Stooq/Nasdaq Data Link/Euronext delayed) not checked.
