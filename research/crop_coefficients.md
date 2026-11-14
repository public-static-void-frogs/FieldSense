# Per-crop depletion coefficients: research findings (2026-10-23)

Full machine-readable table: `crop_coefficients.csv` (same folder). Every row has a `verification` and `sources` column.

Legend: **verified** = read by me from the primary/secondary table in this session. **UNVERIFIED** = from general agronomic knowledge or a search snippet only; check before the app relies on it. kg/t are per tonne of fresh harvested product at marketing moisture unless stated. DueV values were converted from kg/dt x 10.

## 1. Master table

| Crop | Yield t/ha (UNVERIFIED typical) | N kg/t | P2O5 kg/t | K2O kg/t | Straw:grain (DueV) | BNF / N credit | Humus balance HA/ha/yr (VDLUFA via LfL) | Kc ini/mid/end (FAO-56) | Seasonal ET mm (UNVERIFIED) | RUSLE C crop factor (OMAFRA) | Return interval yr (UNVERIFIED) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Maize grain | 5-12 | 13.8-15.1 (DueV); 11.5-17.7 (ON) | 8.0; 6.6-7.9 | 4.6-5.2 | 1.0 | none | -800 (-1040 org col.) | ~0.3/1.20/0.35-0.60 | 450-650 | 0.40 | 1-2 |
| Maize silage | 35-60 t FM | 3.8-4.7 per t FM | 1.6-1.8 per t FM | UNVERIFIED | whole plant | none | -800 | as maize | 450-650 | 0.50 | 1-2 |
| Winter wheat | 3-9 | 18.1-24.1 (by protein 12-16%); ON 19-21 | 8.0 (DueV); 9-10 (ON); 6.5 (UK) | 5.5-6.2 | 0.8 | none | -400 (-520) | 0.4 or 0.7/1.15/0.25-0.40 | 350-500 | 0.35 | 2 |
| Spring wheat | 2.5-5 | as winter | 8.0 | 5.5-6.2 | 0.8 | none | -400 (-520) | -/1.15/0.25-0.40 | 300-450 | 0.35 | 2 |
| Barley | 3-7 | 13.8-17.9 (DueV); 17-23 (ON); 20.6 (MN) | 8.0; 5.2-8.3 | 4.8-7.2 | 0.7-0.8 | none | -400 (-520) | -/1.15/0.25 | 300-450 | 0.35 | 2 |
| Rye | 2.5-6 | 15.1-16.5; ON 19-22 | 8.0; ON 6-9 | 6.1-7.1 | 0.9 | none | -400 (-520) | cereal 0.3/1.15/0.4 | 300-450 | 0.35 | 1-2 |
| Oats | 2-5 | 15.1-16.5; ON 18-24; MN 24 | 8.0; 7.5-8.8 | 5.8-6.3 | 1.1 | none | -400 (-520) | -/1.15/0.25 | 300-450 | 0.35 | 2-3 |
| Soybean | 1.8-3.8 | 44 (DueV); 62-67 (ON/IA) | 15; 13-15 | 23-25 | 1.0 | Ndfa mean 50-60% (range 20-80+); credit 28-50 kg N/ha | +160 | -/1.15/0.50 | 450-600 | 0.50 | 3-4 |
| Sunflower | 1.8-3.5 | 29 (DueV); 27 (MN) | 16; 9.7 (MN) | ~9 (MN, UNVERIFIED) | 2.0 | none | -400 (-520) | 0.35/1.0-1.15/0.35 | 500-650; deep roots | ~0.50 proxy | 4-6 |
| Rapeseed/canola | 2.2-4.5 | 33.5 (DueV); 38-44 (MN/ON) | 18; 22-27 | 11-13 (ON) vs ~40 (MN): CONFLICT | 1.7 | none | -400 (-520) | -/1.0-1.15/0.35 | 350-500 | 0.50 | 3-4 |
| Peas (dry) | 2-4 | 36 | 11 | UNVERIFIED | 1.0 | Ndfa ~50-80% UNVERIFIED; credit ~22 kg N/ha | +160 | -/1.15/0.30 | 300-400 | ~0.50 proxy | 5-6 |
| Lentil | 1-2 | ~36-41 proxy | ~11-12 proxy | UNVERIFIED | ~1 | Ndfa ~62% mean; credit UNVERIFIED | +160 | -/1.10/0.30 | 250-350 | ~0.50 proxy | 4-5 |
| Chickpea | 1-2.5 | ~36-41 proxy | ~11-12 proxy | UNVERIFIED | ~1 | Ndfa 40-70% UNVERIFIED | +160 | -/1.00/0.35 | 250-350 | ~0.50 proxy | 4-5 |
| Alfalfa | 8-14 t DM | ~29-32 per t DM | ~7 per t DM | UNVERIFIED (~20-30) | whole herbage | <10 to >250 kg N/ha/yr; credit 146-213 kg N/ha | +800 per main year (+150 to +500 in seeding year) | 0.40/0.95 avg (1.20 per cut)/0.90 | 800-1200; roots 3-6 m | 0.02 | 4-5 |
| Clover / clover-grass | 6-12 t DM | ~29-33 per t DM | ~7 per t DM | UNVERIFIED | whole herbage | credit ~80% of alfalfa (~117-170 kg N/ha) | +800 per main year | 0.40/0.90/0.85 (berseem) | 700-1000 | 0.02 | 3-5 |
| Sugar beet | 45-90 t FM | 1.8 | 1.0 | 3.7 (MN) | leaf 0.7 | none | -1300 (-1840) | 0.35/1.20/0.70 | 500-700 | ~0.50 proxy | 3-4 |
| Potato | 25-55 | 3.5; MN 3.2 | 1.4; MN 1.2 | 5.5 (MN) | haulm 0.2 | none | -1000 (-1240) | -/1.15/0.75 | 400-550 | ~0.50 proxy | 3-4 |
| Cotton | 2-4 seed cotton | UNVERIFIED (~25-30) | UNVERIFIED | UNVERIFIED | stalks | none | not in VDLUFA | 0.35/1.15-1.20/0.50-0.70 | 700-1300 | UNVERIFIED | 1-2 |
| Rice | 4-9 paddy | UNVERIFIED (~14-17) | UNVERIFIED | UNVERIFIED | ~1 | n/a | not in VDLUFA | 1.05/1.20/0.60-0.90 | 700-1300 | ~0.1 paddy UNVERIFIED | 0-1 |
| Sorghum | 2.5-8 | UNVERIFIED (~18-25) | ~7.5 (MD) | UNVERIFIED | ~1 | none | -800 (grouped with maize as "Mais, Hirse") | -/1.00-1.10/0.55 | 400-550 | ~0.40 proxy | 1-2 |
| Fallow, bare | 0 | 0 | 0 | 0 | | none | negative, not tabulated (UNVERIFIED) | evaporation only | | 1.0 (definition) | |
| Fallow, vegetated | 0 | 0 | 0 | 0 | | | +80 (self-greened from spring) to +180 (from prev. autumn); +400 to +700 sown clover-grass | | | 0.02-0.10 UNVERIFIED | |
| Cover crop, winter rye (green) | | | | | | | -120, plus 0.8 HA per dt FM incorporated | | | 0.01-0.10 UNVERIFIED | |
| Cover crop, vetch/legume mix (stubble sown) | | | | | | UNVERIFIED (~30-60 kg N/ha) | +100, plus 0.8 HA per dt FM incorporated (190-300 dt FM typical) | | | 0.01-0.10 UNVERIFIED | |

Humus values: first number is the LfL "konv." column, bracket the "ökol." column, as printed. In the LfL sheet the instruction text and the column labels disagree on which column is which, so confirm against the VDLUFA Standpunkt 2014 (untere/mittlere/obere). The magnitudes (cereals -400 to -520, row crops -800 to -1300) agree with the pattern in the literature.

## 2. How to use the numbers

**Removal per hectare** = yield (t/ha) x kg/t. Add straw: straw t = grain t x ratio, times straw kg/t.
Example, winter wheat 7 t/ha at 12% protein: grain N 7 x 18.1 = 127 kg, P2O5 7 x 8.0 = 56 kg, K2O about 7 x 5.8 = 41 kg. With straw removed (5.6 t): extra N 28, P2O5 17, K2O about 67.

**Harvest index** (grain mass share of grain plus straw, derived from the DueV straw ratios): wheat 0.56, winter barley 0.59, rye 0.53, oats 0.48, grain maize 0.50, faba bean, pea and soybean 0.50, rapeseed 0.37, sunflower 0.33. These come from the DueV ratios, not from separate HI literature.

**Humus balance**: annual value for the crop (HA = kg humus-C per ha). Straw returned adds 7 HA per dt of straw (cereals, maize, oilseeds, as printed in LfL sheet). Example: winter wheat 8 t grain, straw ratio 0.8, so 64 dt straw x 7 = +448; net about +48 against the -400 crop value. If straw is baled the crop value stands alone. Sugar beet leaf adds 1.3 HA per dt. Net legumes and forage give positive values; hoed crops (beet, potato, maize) strongly negative. A satellite-only crop map cannot see straw management, so the app should run two scenarios (straw removed, straw returned).

**Interpretation of "depletion"**: nutrient removal, humus balance and water use measure different things. Do not add them. A transparent scoring option is a vector per crop, or a separately normalised index per dimension.

## 3. Notes by topic

**Nutrient removal (strongest data).** The DueV Anlage 7 table (primary, legal) is the cleanest source for N and P2O5, but it has no K. K2O comes from Ontario (OMAFRA Field Crop News, which draws on IPNI), the UK PDA/RB209 summary, a Minnesota table citing IPNI 2005 (converted from lb per bushel), and the old Iowa State PM 1688. Those sources agree for cereals within about 10-20%. They disagree strongly on canola K2O, and Ontario's soybean N (62-67 kg/t) is higher than DueV's (44), probably because of different protein assumptions. Iowa's table notes that its data date from the 1980s-90s, and Ohio work found P and K grain concentrations have fallen, so older numbers overstate removal. Use ranges.

Iowa PM 1688 (1999 version, via search snippet, not opened): corn 0.375 lb P2O5 and 0.30 lb K2O per bu, soybean 0.80 and 1.50, wheat 0.60 and 0.30. Converted (56 and 60 lb/bu) these match Ontario: corn 6.7 / 5.4, soybean 13.3 / 25, wheat 10 / 5 kg/t. Iowa stover: 4.8 lb P2O5 and 18 lb K2O per ton.

**BNF.** Mean soybean Ndfa is 50-60% (Salvagiotti 2008 and Peoples; seen via secondary citation, range 20-80+%; Europe 44%, Brazil 78%). Net soil N balance after soybean is usually negative because the seed exports the fixed N. Lentil and vetch mean Ndfa is about 62%, common bean about 38%. Pasture legumes fix about 20 kg shoot N per t DM. The N credit to the next crop is much smaller than the amount fixed. Wisconsin credits for corn: alfalfa 190, 160, 130 lb N/ac for good, fair, poor stands; soybean 40; pea and beans 20; red clover about 80% of alfalfa. Nebraska: soybean 25-45 lb/ac. Iowa State says not to subtract a soybean credit because the rotation-based rates already include it. 1 lb/ac = 1.12 kg/ha.

**Humus balance.** The LfL (Bavaria) form reproduces the VDLUFA 2014 method and was read in full. Other values from that sheet: grain legumes +160, all species. Arable grass and forage legumes +800 per main use year; in the seeding year +500 (spring blank sowing), +400 (green cover crop), +300 (grain cover crop), +150 (late summer blank sowing). Reduce to 75% if the fresh-matter yield is under 50 t/ha. Intercrops: undersown +250, stubble-sown +100 to +140, winter-grain green rye -120. Fallow: self-greening +80 to +180, sown mix +400 to +700. Maize silage and sudangrass -800; fodder beet -1300; potato -1000; vegetables -400 to -1000. The sheet says "residue effect already included" for the remaining crops (silage maize, potatoes, grain legumes, forage) and excluded for cereals, oilseeds, sugar beet. Manure factors: fresh farmyard manure 28-40 HA per t, slurry 2-14 HA per m3.

**Ukrainian/Soviet tables.** I could not open the Ukrainian humus-balance and winnowing (винос) normative tables: the repository PDF redirected to a localhost address. Humification coefficients and mineralisation coefficients for Ukrainian chernozems (Chesnyak and Lykov method) are UNVERIFIED and not in the table. Treat that gap as open. The Kharkiv methodological guide (see S15) is the lead.

**Water use.** The Kc and growth-stage values are FAO-56 Tables 11 and 12 (read). Seasonal ET numbers in the table are my ranges, not read from a source. They require climate-specific ET0 and should be calculated by the app as sum(Kc x ET0) using the FAO-56 stage lengths (Table 11, e.g. winter wheat 180-335 days, maize 125-180, soybean 85-150, sugar beet 155-255, potato 115-165, alfalfa 30-75 days per cutting cycle). Deep-root drying of the subsoil (sunflower, alfalfa) is qualitatively well known; no number was verified.

**Erosion.** OMAFRA gives crop type factors: grain corn 0.40; silage corn, beans and canola 0.50; cereals 0.35; seasonal horticultural crops 0.50; hay/pasture 0.02. These multiply by a tillage factor (fall plough 1.0, spring plough 0.90, mulch 0.60, ridge 0.35, no-till and zone 0.25). The factor is generic, ignores rotation and climate. RUSLE2 and USDA Handbook 703 C values by crop stage and region were not fetched. For crops OMAFRA does not list (sugar beet, potato, sunflower, cotton, rice) I give proxies labelled UNVERIFIED.

**Return intervals.** The figures for minimum years between the same crop family are general agronomic guidance, not read from a table, and all UNVERIFIED. Typical drivers: take-all in wheat, clubroot in canola, sclerotinia in sunflower, canola and soybean, Aphanomyces in pea, cyst nematodes in beet, late blight in potato, autotoxicity in alfalfa. German Fruchtfolge guidance (e.g. DLG, LfL) would be a citable source and should be fetched.

## 4. Confidence summary

Well established: N and P2O5 removal for cereals, maize, soybean, pea, rapeseed, sunflower, potato, sugar beet (DueV); K2O for cereals, maize, soybean (several agreeing sources); VDLUFA humus values (LfL form); FAO-56 Kc; OMAFRA crop factors for 4 crop groups.

Shaky: K2O for canola, sunflower, pulses, forages; all values for cotton, rice, sorghum, lentil, chickpea; BNF kg N/ha by species; seasonal ET; return intervals; C factors outside the OMAFRA list; Ukrainian coefficients.

## 5. Sources

- S1. LfL Bayern (R. Rippel, R. Beck), Humusbilanz-Methode, Stand 11/2014 (based on VDLUFA Standpunkt Humusbilanzierung 2014): https://www.lfl.bayern.de/mam/cms07/iab/dateien/humusbilanz_beratung_bleistift-version_nov_2014_2.pdf
- S2. Duengeverordnung Anlage 7 (Naehrstoffgehalte pflanzlicher Erzeugnisse), BGBl. I 2020, 855: https://www.gesetze-im-internet.de/d_v_2017/anlage_7.html
- S3. OMAFRA Field Crop News, Crop Removal Values (Elgie, 2025; IPNI-based): https://fieldcropnews.com/?p=28952
- S4. Iowa State PM 1688 (1999 table and 2023 revision; 1999 PDF fetch failed, values taken from search results): https://www.agronext.iastate.edu/soilfertility/info/PM%2016881999.pdf and https://store.extension.iastate.edu/Product/5232-pdf ; stover: https://crops.extension.iastate.edu/post/nutrient-replacement-corn-and-soybean-stover-removal
- S5. Minnesota Dept of Agriculture nutrient management tables (IPNI 2005, lb/bu; seen via search snippet only): https://mda.state.mn.us/sites/default/files/2018-05/nutmantables.pdf
- S6. University of Maryland NM-3 (P2O5 removal, snippet only): https://extension.umd.edu/sites/extension.umd.edu/files/2021-04/NM-3.pdf
- S7. Manitoba crop removal (snippet only): https://web40.gov.mb.ca/sd/eal/registries/5659steinbach/crop_nutrient_removal.pdf
- S8. UK PDA/RB209 nutrients in crop material (snippet only): https://www.pda.org.uk/wp/wp-content/uploads/2020/03/pda-pprc.pdf
- S9. Saskatchewan Canola Development Commission, Revising crop nutrient uptake: https://www.saskcanola.com/s/Final-Report-Revising-the-crop-nutrient-uptake.pdf
- S10. Salvagiotti et al. 2008, Field Crops Research 108:1-13 (via secondary citation); Peoples & Giller grain-legume BNF review; Peoples et al. 2012 Crop and Pasture Science 63:759 (https://publish.csiro.au/CP/CP12123).
- S11. Wisconsin legume N credits: https://corn.aae.wisc.edu/Management/pdfs/A3591.pdf , https://corn.aae.wisc.edu/Management/pdfs/L025_FastFacts.pdf , https://ipcm.wisc.edu/wp-content/uploads/sites/54/2022/11/Usinglegumes.pdf
- S12. Nebraska CropWatch N credits: https://cropwatch.unl.edu/giving-proper-nitrogen-credit-legumes-corn-and-milo-rotations ; Iowa "Don't double dip": https://crops.extension.iastate.edu/encyclopedia/dont-double-dip-soybean
- S13. FAO Irrigation and Drainage Paper 56, Chapter 6, Tables 11-12: https://www.fao.org/4/x0490e/x0490e0b.htm
- S14. OMAFRA Universal Soil Loss Equation factsheet 23-005: https://files.ontario.ca/omafra-universal-soil-loss-equation-23-005-en-2023-03-02.pdf
- S15. Ukrainian humus balance methodology (not opened): https://repo.btu.kharkov.ua/bitstream/123456789/35106/3/230_MV_BALANS%20HUMUSU_2022.pdf
- Leads not yet used: BMEL/KTBL Basisdaten; Sachsen LfULG Tab_2 Naehrstoffgehalte (https://landwirtschaft.sachsen.de/download/Tab_2_Naehrstgeh_Acker_sonst_Kult_Oeko_2026_02_02.pdf, which likely has K2O); AHDB RB209 section 4 (cereals/oilseeds crop N and removal); USDA NRCS Crop Nutrient Tool; FAOSTAT yields.
