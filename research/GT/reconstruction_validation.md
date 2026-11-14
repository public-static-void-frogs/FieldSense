# Feasibility: reconstructing field soil-depletion history from crop sequence (research notes, 2026-10-23)

Legend: [V] seen in a fetched/search source this session; [U] unverified / from background knowledge, check before citing.
Caveat: research was via search snippets only (no full-text reads); numbers need checking in the primary papers.

## 1. Methods

| Method | Inputs | Open implementation | Effort/field | Notes |
|---|---|---|---|---|
| Soil-surface nutrient balance (OECD/Eurostat GNB; NUTMON) | Inputs: fertilizer, manure, atmospheric deposition, N fixation, seed. Outputs: crop removal (yield x nutrient content) | Trivial; ~50 lines of pandas. NuGIS does it at county level in the US | Minutes; no spin-up | Removal side is computable from yield + crop coefficients [U]; input side (fertilizer, manure) is the unknown. A surplus/deficit, not a soil stock |
| Humus balance (VDLUFA, also Swiss/Austrian variants) | Crop-specific humus demand/supply coefficients (kg C/ha), organic amendments, residue handling | Coefficient tables only; no standard Python package known [U]. Implement as lookup table | Minutes | Rainford et al. (Swiss, 14 long-term sites): R2 = 0.06 for mixed fertilization, 0.64 for organic fertilization; not suited to predict SOC over single rotations [V]. German trials: weak correlations [V, conference paper] |
| RothC 26.3 | Monthly T, rain, evaporation (NASA POWER usable), clay, soil cover, C input (residues/manure), initial SOC | Rothamsted publishes official Fortran (github.com/Rothamsted-Models/RothC_Code) and a Python version (Apache licence) [V]; pyRothC on PyPI [V, unchecked]; CoolFarm Python RothC + IPCC tier-2 with Monte Carlo (gitlab MethodsCFT/coolfarm-soc) [V]; R: SoilR, PEcAn.RothC | Seconds/field monthly; needs spin-up to equilibrium (or use measured SOC and solve for inputs) | Standard choice. FAO GSOCseq uses it [V] |
| ICBM | 2 pools, annual C inputs (above/below-ground), climate factor | R: SoilR::ICBMModel [V]. No Python package found [V]; the model is ~10 lines of ODE, trivially re-implemented | Seconds | Designed for crop-rotation C-input from yields via allometry (Bolinder) - fits this use case well; Holos (Canada) uses it [V] |
| AMG | Annual, 3 pools, clay/CaCO3/pH, C inputs from yield | Not found in Python [V negative]. Simple annual formula [U] | Seconds | French; inputs from yields via humification coefficients |
| SIMPLE (Zhang et al.) | Very simple; not found in search [V negative] | - | - | Not verified |
| Century/DayCent | Daily weather, soil layers, management schedule (.sch), fertilizer, tillage | DayCent Fortran/C; Python wrappers are research-grade [U] | Hours to set up per site; calibration | Gives N, P (Century), SOC; too heavy for 2 weeks |
| DNDC | Daily weather, soil, management | DNDC binary / Python port exist (Linux/Win) [U] | Hours per site | Needs full management (fertilizer, tillage dates) |
| FAO GSOCseq | RothC on 1 km grid; inputs monthly rain/T/PET, initial SOC (GSOC map), clay, soil cover, NPP-derived C inputs; spin-up then warm-up 2000-2018 [V] | FAO docs and R/GEE workflow (fao-gsp.github.io/GSOCseq) [V] | Pre-computed country maps | Fixed-scenario, 0-30 cm, 20-yr projections; inspiration for NPP-based input estimation |

What satellite/public data cannot give (unknowable per field): fertilizer N/P/K rates; manure type/rate/history; residue removal (baling, grazing); tillage; cover crops (partly via NDVI); irrigation; liming; actual yield (only approximated); previous land use before 2008 (CSB/CDL) and initial SOC pool state; erosion/deposition. These dominate P/K balance: input side is often 50-100% of the term [U].

## 2. Validation ground truth

- **TFI/IPNI "Soil Test Levels in North America"**: 2020 summary (12th in series per TFI [V]); earlier 2001/2005/2010/2015. Data are production-farm samples from commercial labs, reported at STATE/province level (not county), manured samples flagged; interactive tool soiltest.tfi.org (chart/map/table) [V]. County level NOT confirmed [V negative]. Some state labs (Iowa State, Wisconsin, Michigan State) publish county-level medians [U].
- **NuGIS (nugis.tfi.org)**: county/HUC nutrient balances from Census of Ag + NASS + fertilizer sales; census years 1987-2007 plus annual 2010-2013 per IPNI-era description; current extension unknown [V partial]. Free; export options unconfirmed. Paper found county surplus P correlated with soil test P r = 0.45-0.65 in AR, NC, OK; best aggregation period 10, 30 and 4 yr [V] (par.nsf.gov/biblio/10608803 - verify). This is the best precedent for a county backtest.
- **NRCS**: RaCA (2010-2011, ~6000 sites, SOC; single time point, no trend) [U]; NRCS NCSS lab data (KSSL) and SSURGO as static baseline [U]. NRCS NRI/CEAP for national modeled SOC [U].
- **Long-term experiments**: Rothamsted e-RA - open-access tier (Broadbalk, Park Grass, Hoos Barley, met data; no login) and e-RAdata (free, password, ~5 working days) [V]. KBS LTER MCSE: KBS024 surface C/N 1989-2001, KBS044 deep cores 2001-2022; note redistribution requires permission notice [V]. Morrow Plots (Illinois, >100 yr SOC; 15-19% decline some corn-soy plots 1968-1998 [V]); no downloadable dataset found. Sanborn Field (Missouri): not checked. A 2026 Scientific Data paper: harmonized dataset of 34 temperate-cropland long-term experiments, 167 treatments, SOC stocks + C inputs + climate + soil, built for testing SOC models [V] (lter.kbs.msu.edu/citations/4286 - strong candidate for a ready-made RothC/ICBM backtest; check licence).
- **LUCAS Topsoil**: 2009, 2015, 2018 (and 2022 campaign); ~ thousands of revisited points; EU+UK SOC change 2009-2018 modelled (De Rosa et al.): mean -0.75%; continuous cropland -0.04 +/- 0.01 g C/kg/yr [V]. ESDAC distributes after request/registration [V]. Land-cover misclassification can distort trends (Swedish check) [V]. P and K measured (Olsen P, K) in LUCAS 2009/2015/2018 [U].
- **France RMQS**: 2,240 sites, 16 km grid; RMQS1 2000-2009, RMQS2 2016-2027, resampled ~12-15 yr; archived samples [V]. Access via Gis Sol, request-based [U].
- **England**: Countryside Survey (1978, 1998, 2007) and NSI - not researched [U].
- **Ukraine agrochemical certification**: rounds approx. every 5 years; 10th round 2011-2015, 11th 2016-2020 [V]. Humus down 0.22 points over rounds 1986-2010 to 3.14% [V]; chernozem 10th round humus down ~2.5-4% relative, but mobile P and K up slightly [V] (shows P/K trend decoupled from humus). Data are published as regional/oblast summaries; field-level data held by state institutions, not open [U]. Useful for oblast-level sanity check only.

## 3. Evidence on accuracy

- RothC: Coleman et al. 1997 fitted to 18 treatments / 6 LTEs, acceptable fit for 14, but fitted by adjusting plant C input [V]. Indian LTE studies: RMSE 3-25% of SOC, again with calibrated inputs [V]. No clean uncalibrated error figure found [V negative]; general lit expectation: uncalibrated cropland predictions of SOC change have errors comparable to or larger than the signal [U].
- Humus balance: poor for mixed mineral/organic regimes (R2 0.06), OK where organic amendments dominate (R2 0.64) [V].
- Nutrient balance to soil test: P budget vs soil-test P is nonlinear, with a deflection point; above it r2 0.33-0.72, below it not significant (grassland, 6 sites) [V]; Argentina: ~8-11 kg P/ha per 1 mg/kg Bray [V]; China no-P plots: Olsen P fell 1.4-2.4 mg/kg per 100 kg P/ha deficit [V]. Slope depends on initial STP, soil, extraction, so one conversion constant is misleading [V].
- Minimum detectable SOC change: Necpalova 2014 (US Corn Belt): MDD (0-10 cm, 5 reps) from 1.04 g C/kg (6%) to 7.15 g C/kg (31%) [V]. Swiss 393 fields: detectability <10 yr with equivalent-soil-mass sampling, decades for fixed depth [V]. RMQS simulation: 3-15 yr to detect [V]. Smith 2004: 10-15 yr [V]. So at 5-15 yr, typical cropland SOC change (0.1-0.5 %/yr of stock) is at or below single-sample noise (tens of % CV in the field).

## 4. Yield inputs

- SCYM (Lobell et al.): vs yield-monitor data on >1M US Corn Belt maize fields, pixel r2 0.31 -> 0.40 with smoothing, field r2 0.45, county r2 0.69 [V]. Soybean improved variant r2 = 0.27 at 30 m [V]. R2 >= 0.5 for US maize/India wheat in an earlier multi-region test [V]. SCYM data are in GEE (maize/soy US) [U].
- County yields (NASS Quick Stats; Eurostat NUTS2/3) are free and good for relative/multi-year averages; they capture the interannual variation (county r2 ~0.7) but not field-to-field differences.
- Impact: C input is proportional to yield in allometric models, but the Bolinder root and residue coefficients, harvest index changes, and the root:shoot allocation are more sensitive (EGU23-4250; PMC5007648 argues root input is crop-specific rather than yield-dependent) [V]. For nutrient removal, removal = yield x content so error is linear in yield error. Over a 10-year multi-field average, random yield error averages down; systematic bias (county mean vs. field) does not. For rotation comparisons, crop identity effects (legume vs cereal, residue return) exceed yield-estimation noise [U-inference].
- CDL/CSB: CDL accuracy ~85-95% major crops; CSB corn/soy acreage within ~2-8% of NASS totals [V, snippet-level]. Crop-sequence errors compound over 10+ years (~0.9^n per-field chance of fully correct sequence) [inference].

## 5. Bottom line for a 2-week build

Credible to show:
- Relative, per-rotation comparison: modeled N/P/K removal (yield x coefficient) and a C-input index/ICBM or RothC delta-SOC, with ranges from Monte Carlo over unknowns (fertilizer rate, residue removal, yield +/- ).
- "Crop removal" history per field (kg N/P2O5/K2O removed per year) from CSB sequence x county yield. This is fully defensible and needs no unknown inputs.
- Scenario ranking: "rotation A loses ~X-Y kg P/ha/yr more than B under typical fertilization", and SOC "direction" with an explicit uncertainty band; clearly labelled "relative to baseline".
- County-scale backtest result as a credibility check.

Not credible:
- Your field's current P, K, or N level; absolute SOC trajectory; year-by-year depletion history as a measured fact; any claim about fertilizer-unaware "depletion".
- SOC change <~0.3 t C/ha/yr claimed as significant; per-field forecasts without soil test input.
- Using Century/DNDC claims without management data.
- Offer to user: optional input of a recent soil test (P, K, SOC) to anchor the trajectory (back-calculate/forward), which converts "reconstruction" into "anchored estimate".

Minimal method (suggested):
1. Per field/year: crop from CSB/CDL (US); yield = county NASS yield x (optional SCYM scaling); removal N/P2O5/K2O from standard coefficient tables (e.g. USDA NRCS PLANTS / IPNI crop removal tables [U]).
2. Inputs: assume county-average fertilizer (NuGIS fertilizer + manure) as a prior with +/- range; legume N fixation by coefficients.
3. SOC: ICBM or RothC (Python, monthly NASA POWER, clay from SoilGrids/SSURGO); C input via Bolinder-style allometry from yield; start from SoilGrids SOC at 2008 (steady state spin-up as alternative); Monte Carlo 200 draws over residue removal, input coefficients, yield error.
4. Output: ranges and relative ranking; P/K as cumulative balance, with soil-test conversion only if user gives a test (use ~8-70 kg P/ha per mg/kg range, flagged).

Feasible 2-week validation experiments:
A. County backtest (US): compute cumulative P and K balance 2008-2017 from CDL area x NASS yields x removal vs NuGIS county balances (consistency check) and vs county/state soil-test change (TFI state-level 2010 -> 2015 -> 2020; county-level from Iowa/Wisconsin/Michigan/Indiana state lab summaries if obtainable). Expect r ~0.4-0.65 at best (literature) [V]; report the correlation and scatter honestly. Risk: county soil-test data access.
B. LTE backtest of the SOC engine: take the 34-LTE harmonized Scientific Data set, or Rothamsted open-access Broadbalk/Park Grass, or KBS surface C 1989-2001; run ICBM/RothC with only yield-derived inputs and compare to measured SOC change; report RMSE and whether the rotation ranking is recovered. Most doable in 2 weeks and most rigorous.
C. Ukraine/oblast-level sanity check: sign of humus change vs modeled SOC direction (low rigor).
D. Optional: LUCAS revisit points (needs ESDAC registration; allow days).

## Sources
- https://soiltest.tfi.org/about
- https://store.tfi.org/products/soil-test-levels-in-north-america-2020-summary-update
- https://www.sciencesocieties.org/publications/crops-soils/2021/november-december/soil-test-levels-to-guide-nutrient-stewardship
- https://nugis.tfi.org/ and https://nugis.tfi.org/about
- https://par.nsf.gov/biblio/10608803 (county STP vs surplus P)
- https://ri.agro.uba.ar/files/download/articulo/2011Ciampitti.pdf (Argentina P/Bray)
- https://pmc.ncbi.nlm.nih.gov/articles/PMC4329157 and https://link.springer.com/article/10.1007/s13280-015-0628-x (STP vs P budgets; unverified which is which)
- https://www.rothamsted.ac.uk/rothamsted-carbon-model-rothc ; https://github.com/Rothamsted-Models/RothC_Code
- https://coolfarm.org/from-theory-to-practice-the-4-key-advantages-of-implementing-two-soc-models-in-python/
- https://rdrr.io/cran/SoilR/man/ICBMModel.html
- https://www.fao.org/fileadmin/user_upload/soils/Joint_trainings/Dec2022-OCB_GSP/4._GSOCseq_Running_the_RothC_Model.pdf
- https://orgprints.org/21587/ ; https://ira.agroscope.ch/de-CH/publication/57805 (humus balance validation; Rainford DOI 10.1111/ejss.70007)
- https://eprints.qut.edu.au/229231 (RothC LTE); https://repository.rothamsted.ac.uk/id/eprint/12307
- https://corn.aae.wisc.edu/Pubs/JL_JournalArticles/Journal%20of%20Soil%20and%20Water%20Conservation-2014-Necpálová-517-31.pdf
- https://esdac.jrc.ec.europa.eu/content/SOC-changes-2009-18 (LUCAS SOC change)
- https://app.inrae.fr/en/partnerships/monitoring-soils-for-better-protection/ (RMQS)
- https://www.afes.fr/wp-content/uploads/2023/04/EGS_10_1_arrouaysdenis.pdf
- https://www.era.rothamsted.ac.uk/info/RLTEdatavailable ; https://era.rothamsted.ac.uk/info/howtoaccessdata
- https://lter.kbs.msu.edu/datasets/27 ; https://lter.kbs.msu.edu/datasets/47 ; https://lter.kbs.msu.edu/citations/4286
- https://experts.illinois.edu/en/publications/soil-organic-carbon-trends-over-100-years-in-the-morrow-plots/
- https://journals.nubip.edu.ua/index.php/Agronomija/en/article/view/agr2019.03.029 ; https://sdg.ukrstat.gov.ua/15-3-1
- https://fse.fsi.stanford.edu/taxonomy/term/331 (SCYM listings; find primary paper: Lobell et al. 2015 RSE; Jin et al. 2019)
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5007648/ ; https://meetingorganizer.copernicus.org/EGU23/EGU23-4250.html
- https://www.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/metadata_Crop-Sequence-Boundaries-2022.htm ; https://journals.sagepub.com/doi/10.3233/SJI-230078
