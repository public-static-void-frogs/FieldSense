# Metrics of Agricultural Field (Soil) Depletion

A reference list of chemical, physical, and biological/productivity metrics used to assess soil degradation, with definitions, verified thresholds, and the composite indices (SQI, SMAF, Cornell CASH) that combine them. Section 5 is based on three source papers supplied with the request; sections 1-4 are unchanged from the first version.

**Important for the app:** sections 2-5 describe lab and field measurements. Bulk density, aggregate stability, enzymes, earthworms, microbial biomass and the SQI, SMAF and CASH scores cannot be measured by satellite for a field. **Section 6** lists which metrics can be obtained without sampling. It also describes the modelled reconstruction used instead: crop history, yields and nutrient removal, input ranges, and a soil carbon model.

## 1. Corrections to commonly quoted thresholds

- **Soil organic carbon (SOC):** About 2% is widely suggested as the level below which deterioration may occur, but it is a rule of thumb. A single universally accepted minimum or maximum value cannot be established; it depends on soil type, climate, texture, and land use. One study estimated a critical threshold from the clay and silt content of the soil. Read it as "below roughly 2% (soil-specific) = elevated risk."
- **Bulk density:** A single cutoff (e.g. 1.4-1.6 g/cm3) is too coarse. The root-limiting value depends on texture. Based on Harris 1990, one horticultural reference gives 1.4-1.55 g/cc for clay and silt loam, 1.55-1.75 for sandy loam, and above 1.75 for sand. Compare measurements against a texture-specific benchmark.

## 2. Chemical metrics

| Metric | Definition |
|---|---|
| Soil organic carbon (SOC) / organic matter | Carbon stored in soil organic matter. The most frequently selected soil quality indicator: soil organic matter appeared in 67.7% of 155 minimum data sets reviewed. |
| Available N, P, K | The fraction of nitrogen, phosphorus, and potassium that plants can take up. Available phosphorus appeared in 43.2% of the same minimum data sets. |
| Soil pH | Acidity or alkalinity of the soil; controls nutrient availability and microbial activity. The optimum (commonly cited as 6.0-7.5) varies by crop; the Cornell manual gives about 6.2-6.8 for most crops (see section 5.3). |
| Electrical conductivity (EC) | Measure of soluble salts. High values signal salinization. Texture-specific classes are in section 5.3. |
| Cation exchange capacity (CEC) | Capacity of the soil to hold exchangeable cations (Ca, Mg, K and others). |
| Base saturation | Share of the CEC occupied by base cations rather than H+ or Al3+. A falling value indicates leaching and acidification. |
| Total N, Ca, Mg | Additional chemical indicators proposed in a review of Mexican soil quality studies (organic matter, pH, total and inorganic N, P, K, Ca, Mg). |

## 3. Physical metrics

| Metric | Definition |
|---|---|
| Bulk density | Dry soil mass per unit volume (g/cm3); an indicator of compaction. High values signal low porosity and may restrict root growth and the movement of air and water. |
| Topsoil depth / erosion loss | Thickness of the fertile upper layer, or the rate at which it is lost (t/ha/yr). |
| Aggregate stability | How well soil clumps resist breakdown under wetting or raindrop impact. Low stability leads to crusting and erosion. |
| Water infiltration rate | Speed at which water enters the soil surface. Slow rates indicate compaction and runoff risk. |
| Penetration resistance | Force needed to push a probe through soil; direct measure of mechanical impedance to roots. |
| Texture and water retention | Mostly inherent properties; they set the baseline against which other physical metrics are interpreted. |

## 4. Biological and productivity metrics

| Metric | Definition |
|---|---|
| Microbial biomass carbon (MBC) | Carbon held in living microbial cells; a sensitive early indicator of biological decline. |
| Soil respiration | CO2 released by soil organisms; measure of biological activity. |
| Soil enzyme activities | Activities of dehydrogenase, beta-glucosidase, urease, phosphatase. Enzyme assays do not represent true in situ activity and must be viewed as an index (USDA-NRCS). |
| Earthworm density | Abundance of earthworms as a macro-fauna indicator. |
| Mycorrhizal fungi | Abundance of arbuscular mycorrhizal fungi. |
| Crop yield trend | Long-term change in yield at constant inputs. A lagging indicator: it confirms degradation after soil metrics have already shifted. |

## 5. Composite indices that combine the metrics

All three indices below follow the same three-stage logic: (1) choose indicators from the physical, chemical, and biological groups, (2) convert each measurement to a unitless score, (3) integrate the scores into one number. They differ in how they carry out each stage.

| | SQI (Damiba et al. 2024) | SMAF (Pacci & Dengiz 2021, after Andrews et al. 2004) | Cornell CASH (Moebius-Clune et al. 2016) |
|---|---|---|---|
| Indicators | 22 in the full set; 10 after PCA reduction | Up to 13 | 12 standard rating lines, plus add-ons |
| Selection | Statistical (principal component analysis) | Minimum data set chosen from site-specific factors | Fixed set, selected from 42 candidates by six criteria |
| Scoring | Linear, bounded 0.1-1.0, with study-specific lower/upper thresholds | Cumulative normal curves, 0-1 (0-100), shape adjustable to site | Cumulative normal curves, 0-100, from a soil database, texture- and region-specific |
| Integration | Plain average (A-SQI) or PCA-weighted sum (W-SQI) | "Combined" into physical, chemical, biological and total indices; weighting not given in the supplied paper | Unweighted mean of all ratings |
| Output | Index 0-1 with grade classes | Scores 0-1 with five classes | Overall score 0-100 with classes, plus per-indicator constraints |
| Main stated limit | Thresholds and PCA depend on the data and site | Scoring is site-specific and needs local curves | Developed for the Northeastern US; overall score is secondary to constraints |

### 5.1 Soil Quality Index (SQI)

**Generic form.** An SQI is a function of several soil quality indicators, built by selecting a minimum data set (MDS) with statistical techniques, scoring the indicators, and computing the index. The weighted form is:

```
SQI = sum(Wi x Si)
```

`Si` is the score of indicator i and `Wi` its weight. PCA is the most widely used method for building minimum data sets (415 articles reviewed).

**Worked example: Damiba, Gathenya, Raude & Home (2024), Heliyon 10(5): e25611.** The paper compares two SQI methods in the Kakia-Esamburmbur catchment (46.2 km2), Narok County, Kenya, under three land uses: grassland (GL), cropland (CL), and forest (FL). Sampling was 24 sites (8 per land use), 72 composite samples, at 0-20 cm depth. Soil erosion and declining productivity motivate the study.

#### Step 1: Indicator selection

The full dataset covers three groups:

| Group | Indicators |
|---|---|
| Physical (7) | Moisture, bulk density (BD), saturated hydraulic conductivity (Ksat), sand, clay, silt, basic infiltration rate (BIR) |
| Chemical (11) | pH, EC, total N, available P (PO4-P), exchangeable K, Na, Ca, Mg, CEC, total organic carbon (TOC), soil organic matter (SOM) |
| Biological (4) | Microbial biomass N (MBN), microbial biomass C (MBC), potentially mineralizable N (PMN), soil respiration (SRM) |

For the weighted index, PCA reduced this set to a minimum data set the paper calls the identified key indicators (IKI):

1. Derived indicators (OM, Na/K, Ca/Mg) were removed, and the data were standardized to z-scores.
2. Only principal components (PCs) with eigenvalue above 1 and at least 5% of variance were kept: eight PCs, together explaining 81.09% of the variance.
3. Within each PC, highly loaded indicators were examined. Where several were strongly correlated (r of 0.5 or more, p below 0.05), the one with the highest loading was kept; where they were not correlated, all were kept.

| PC | Variance explained | Weight | Indicator(s) kept | Paper's label for the PC |
|---|---|---|---|---|
| 1 | 22.65% | 0.279 | Mg, Moisture | Base cations, moisture, structure |
| 2 | 13.80% | 0.170 | TOC | Total organic matter factor |
| 3 | 9.55% | 0.118 | Sand | Texture effect on salinity |
| 4 | 9.22% | 0.114 | CEC | Soil macro-nutrients |
| 5 | 8.66% | 0.107 | BIR, PMN | BIR effect on N mineralization, salinity, respiration |
| 6 | 7.05% | 0.087 | BD | Soil physical properties |
| 7 | 5.29% | 0.065 | MBC | Microbial biomass carbon |
| 8 | 4.85% | 0.060 | MBN | Microbial biomass nitrogen |

The weight of each PC is its variance share divided by the cumulative variance (for example 22.654 / 81.087 = 0.279). Each key indicator takes the weight of its PC.

#### Step 2: Scoring (homothetic linear scoring, HLSF)

Each indicator is converted to a score between 0.1 and 1.0 using a lower threshold L and an upper threshold U:

```
More is better (Eq. 1):   0.1                          if x <= L
                          0.1 + 0.9 (x - L)/(U - L)    if L < x < U
                          1.0                          if x >= U

Less is better (Eq. 2):   1.0                          if x <= L
                          1 - 0.9 (x - L)/(U - L)      if L < x < U
                          0.1                          if x >= U

Optimum (Eq. 3, with L < L1 <= U1 < U):
                          0.1                          if x < L or x > U
                          0.1 + 0.9 (x - L)/(L1 - L)   if L <= x < L1
                          1.0                          if L1 <= x <= U1
                          1 - 0.9 (x - U1)/(U - U1)    if U1 < x <= U
```

Thresholds used in the study (Table 3 of the paper, mostly from the literature and the authors' experience for this climate):

| Indicator | Unit | Lower | Upper | Reference | Function |
|---|---|---|---|---|---|
| Moisture | % | 15 | 105 | 60 | More is better |
| BD | g/cm3 | 1.2 | 1.8 | 1.6 | Less is better |
| Ksat | cm/hr | 0.083 | 36 | 3.6 | Less is better |
| Sand | % | 0 | 60 | - | Less is better |
| Clay | % | 0 | 30 | - | More is better |
| Silt | % | 0 | 25 | - | More is better |
| BIR | cm/hr | 1 | 4 | 2 | Less is better |
| pH (1:2.5) | - | 4.5 / 7 | 6 / 8 | 6-7 | Optimum (more is better below 6, less is better above 7) |
| EC | dS/cm | 0.2 | 2 | 1 | Less is better |
| Total N | % | 0.05 | 0.54 | 0.3 | More is better |
| PO4-P | mg/kg | 4.55 | 54.5 | 29.55 | More is better |
| Exch. K | meq/100g | 0.2 | 2 | 2 | More is better |
| Exch. Na | meq/100g | 0.3 | 0.7 | - | More is better |
| Exch. Ca | meq/100g | 4 | 10 | - | More is better |
| Exch. Mg | meq/100g | 3 | 8 | - | More is better |
| CEC | meq/100g | 15 | 25 | 15 | More is better |
| TOC | % | 2 | 8 | 5 | Optimum |
| SOM | % | 3.44 | 13.76 | - | More is better |
| MBN | ppm | 0 | 45.5 | - | More is better |
| MBC | ppm | 0 | 170.5 | - | More is better |
| PMN | ppm | 0 | 100 | 90.9 | Optimum |
| SRM | mg CO2/g | 0 | 1.25 | - | More is better |

#### Step 3: Integration

Two indices were computed and compared.

**Additive SQI (A-SQI)**, the plain average of all scores in the full dataset:

```
A-SQI = sum(Si) / n        n = 22 (all), 7 (physical), 11 (chemical), 4 (biological)
```

The same formula gives the partial indices: the Soil Physical Quality Index (SPQI), Soil Chemical Quality Index (SCQI), and Soil Biological Quality Index (SBQI).

**Weighted SQI (W-SQI)**, the PCA-weighted sum over the ten key indicators (Eq. 8):

```
W-SQI = 0.279 S_Mg + 0.279 S_Moisture + 0.170 S_TOC + 0.118 S_Sand + 0.114 S_CEC
      + 0.107 S_BIR + 0.107 S_PMN + 0.087 S_BD + 0.065 S_MBC + 0.060 S_MBN
```

#### Classes

| Index | Class boundaries |
|---|---|
| A-SQI | Poor/low below 0.55; intermediate 0.55-0.70; high above 0.70 |
| W-SQI | Very low 0-0.19; low 0.20-0.39; medium 0.40-0.59; good 0.60-0.79; very good 0.80-0.99 |

#### Results reported

| Land use | A-SQI mean | W-SQI mean | Mean TOC (%) |
|---|---|---|---|
| Forest (FL) | 0.61 | 0.57 | 1.90 |
| Cropland (CL) | 0.59 | 0.55 | 2.02 |
| Grassland (GL) | 0.58 | 0.53 | 1.57 |

- Both methods place the whole catchment in the "medium" class, with forest highest and grassland lowest. For most indicators, differences between land uses were not statistically significant (ANOVA p above 0.05; BIR was the exception at p = 0.027), and the two methods did not differ significantly from each other.
- Sensitivity, defined as S = SQI max / SQI min: A-SQI 1.47 and W-SQI 2.25 for the whole catchment. W-SQI also had the wider coefficient of variation (12.57-19.14% against 5.02-10.73%), which the authors treat as the reason it is the more sensitive method. A-SQI classified 95.84% of sites as poor or medium; W-SQI classified 79.17% as poor or medium.
- Contribution of each key indicator to the W-SQI: CEC 18.68%, BD 15.61%, BIR 14.71%, Mg 14.26%, MBN 8.30%, MBC 8.26%, Sand 6.77%, Moisture 5.75%, TOC 5.16%, PMN 2.63%.
- Mean linear scores of the key indicators show which ones limit quality (low scores) and which do not (scores near 1):

| Land use | Mg | Moisture | TOC | Sand | PMN | BIR | BD | MBC | MBN | CEC |
|---|---|---|---|---|---|---|---|---|---|---|
| GL | 0.19 | 0.10 | 0.15 | 0.33 | 0.14 | 0.91 | 1.00 | 0.65 | 0.53 | 1.00 |
| CL | 0.33 | 0.13 | 0.20 | 0.31 | 0.13 | 0.56 | 1.00 | 0.73 | 0.89 | 0.81 |
| FL | 0.26 | 0.11 | 0.16 | 0.32 | 0.15 | 0.82 | 0.99 | 0.74 | 0.89 | 0.92 |

- TOC is among the limiting indicators: mean TOC was 1.57-2.02%, at or just below the roughly 2% rule of thumb in section 1, which the authors read as impaired organic carbon.

#### Limitations stated by the authors

- PCA may be unreliable when the original dataset is small.
- Thresholds depend on literature and the authors' judgment for this climate.
- An SQI for one crop may differ from that for another crop or management.
- Sampling date and season affect the indicator values (post-harvest residues and manure may have raised TOC).

#### Notes from checking the paper against itself

- **Indicator count:** the abstract says 23 indicators; the equation text uses n = 22 (7 + 11 + 4), matching Table 3.
- **Weights do not sum to 1:** the eight PC weights sum to 1, but PC1 and PC5 each supply two indicators, so the weights in Eq. 8 sum to 1.386. Using the paper's Table 14 mean scores, Eq. 8 reproduces the reported W-SQI means (GL 0.533, CL 0.553, FL 0.564 against 0.53, 0.55, 0.57), so the equation itself is applied consistently, but the index is not capped at 1.
- **Equation labels:** the printed Eq. 1 is "more is better" and Eq. 2 is "less is better", while the sentence below them assigns them the other way round. I followed the equations. The printed denominators in Eq. 3 do not make the curve continuous at L1 and U1; the form above is my reading of the evident intent.
- **A-SQI partial indices:** Table 6 reports SPQI of 0.01-0.02, which cannot be an average of seven scores bounded at 0.1-1.0 (the BD and BIR mean scores alone are 0.56-1.00). Treat that row with caution.
- **W-SQI partial indices:** the FL chemical value in Table 13 (0.115) looks like a typo; Figure 10 of the paper shows about 0.20.
- **Respiration threshold:** all sites exceeded the SRM upper threshold of 1.25 mg CO2/g (mean 6.4), so that indicator cannot discriminate between sites.

### 5.2 SMAF (Soil Management Assessment Framework)

**Source:** Pacci & Dengiz (2021), an introductory paper on SMAF; the framework itself is from Andrews, Karlen & Cambardella (2004), which the paper cites. The supplied paper also contains an unrelated paragraph on seed priming and salinity under the SMAF heading, which I ignored.

**What it is.** SMAF is a framework for assessing how soil performs its functions for a chosen land use. Because soil quality depends on management objectives, climate, crops, and soil type, it provides site-specific interpretation of each indicator rather than one universal threshold.

**Three steps (Figure 1 of the paper):**

1. **Select a minimum data set (MDS)** from physical, chemical, and biological indicators, chosen on site-specific factors.
2. **Interpret each indicator with a scoring function.**
3. **Calculate the soil quality index** as a function of the scored MDS indicators.

**Indicators.** The paper lists 13: macroaggregate stability, available water capacity, bulk density, beta-glucosidase activity, electrical conductivity, soil test potassium, microbial biomass carbon, soil solution pH, potentially mineralizable nitrogen, extractable phosphorus, "soil adsorption ratio" (presumably the sodium adsorption ratio), total organic carbon, and water-filled pore space.

**Scoring.**

- Measured values are converted by a cumulative normal distribution curve to a score from 0 to 1 (0 to 100 as a percentage), where 1 is the optimum.
- Three curve types: *more is better* (for example aggregate stability), *less is better* (for example bulk density), and *optimum* (for example pH, where both extremes are undesirable).
- The threshold of each curve is adjusted by organic matter, texture, climate, slope, region, mineralogy, decomposition class, crop, sampling time, and analytical method. For example, the bulk density curves differ by texture, and the optimum pH differs by crop.
- Score classes: below 20 very low (red), 20-40 low (orange), 40-60 medium (yellow), 60-80 high (green), above 80 very high (dark green).

**Integration.** The paper says the scores are "combined" to give the soil quality index, from which physical, chemical, and biological quality are evaluated and management is decided. It does not give the weighting; see Andrews et al. (2004) for the full procedure.

**Case study cited (Pacci et al. 2021, Van Basin, Turkey).** 150 surface (0-30 cm) samples over 6,024 ha of pasture, using 11 of the 13 indicators (without PMN and beta-glucosidase). The chemical quality index was low, the biological index high, and the physical and total indices moderate. The middle of the area scored low on all indices, attributed to steep slope and high erosion.

**Advantages and limits claimed by the paper.**

- Scoring curves can be adapted to soil structure, climate, and agricultural practice.
- A minimum data set from one region cannot be transferred to another, but because SMAF takes soil taxonomy into account, curves for a given soil class can be applied to the same class elsewhere.
- The paper's conclusion says SMAF avoids disagreements by interpreting a fixed parameter set against standards, whereas other models re-derive a minimum data set each time.

### 5.3 Cornell CASH (Comprehensive Assessment of Soil Health)

**Source:** Moebius-Clune et al. (2016), *Comprehensive Assessment of Soil Health: The Cornell Framework*, Edition 3.2 (revised 2017). The 2017 version of the assessment and its scoring was developed for the Northeastern United States.

**What it is.** CASH measures soil health as the integration of chemical, physical, and biological processes important for sustained productivity and environmental quality. It identifies constraints to soil functioning beyond nutrient levels and guides management to remove them.

**How indicators were chosen.** 42 candidate indicators were evaluated on six criteria: sensitivity to management, ability to represent agronomically and environmentally important soil processes, consistency and reproducibility, ease and cost of sampling, cost of analysis, and ease of interpretation.

**Indicators (standard package and add-ons):**

| Group | Indicator | What it measures | Scoring direction |
|---|---|---|---|
| Physical | Available water capacity (AWC) | Water a disturbed sample holds between field capacity and wilting point (g/g) | More is better |
| Physical | Surface hardness | Maximum penetration resistance at 0-6 in (psi) | Less is better |
| Physical | Subsurface hardness | Maximum penetration resistance at 6-18 in (psi) | Less is better |
| Physical | Aggregate stability | Percent of 0.25-2 mm aggregates remaining after simulated rainfall | More is better |
| Biological | Organic matter | Mass lost on ignition at 500 C (%) | More is better |
| Biological | ACE soil protein index | Citrate-extractable protein, the organically bound N pool (mg/g) | More is better |
| Biological | Soil respiration | CO2 released over a 4-day incubation (mg/g) | More is better |
| Biological | Active carbon | Permanganate-oxidizable carbon, the easily available food source for microbes (ppm) | More is better |
| Chemical | pH | Soil acidity (1:1 water) | Optimum |
| Chemical | Extractable phosphorus | Modified Morgan extraction (ppm) | Optimum |
| Chemical | Extractable potassium | Standard nutrient analysis | More is better |
| Chemical | Minor elements | Mg, Zn (more is better, deficiency risk); Fe, Mn (less is better, toxicity risk) | Mixed |
| Add-on | Potentially mineralizable N, root pathogen pressure | Biological activity; disease pressure | More / less is better |
| Add-on | Salinity and sodicity, heavy metals | Soluble salts, sodium adsorption ratio, metal contamination | See below |

Soil texture is measured but is not itself a health indicator; it informs how the others are scored.

**Scoring.** Each measurement is converted to a 0-100 rating using the cumulative normal distribution (CND), with the mean and standard deviation taken from the Cornell Soil Health Lab database for each texture class (coarse, medium, fine). Since 2016 the means and standard deviations are also computed for five USDA-NRCS Major Land Resource Area regions (L, M, N, R, S). The scoring approach was adapted from Andrews et al. (2004), that is, from SMAF.

```
More is better:  Score = 100 x CND(x)
Less is better:  Score = 100 x (1 - CND(x))
Optimum curve:   rises to the lower end of the optimum range, stays at 100 within it,
                 then falls again with further increase (used for pH and phosphorus)
```

The manual's example uses active carbon in medium-textured soil, with a mean of 531 ppm and a standard deviation of 182 ppm, and gives a score of 60 for 600 ppm. By my calculation those parameters give about 65, so the manual's figure is probably read from a rounded or texture-specific curve and should be treated as illustrative.

**Rating classes:**

| Rating | Class | Colour | Meaning in the manual |
|---|---|---|---|
| 0-20 | Very low | Red | Constraint likely limiting yield, quality, and sustainability |
| 20-40 | Low | Orange | Process functioning somewhat poorly |
| 40-60 | Medium | Yellow | Suboptimal; yield and sustainability could decrease over time |
| 60-80 | High | Light green | Non-limiting functioning |
| 80-100 | Very high | Dark green | Optimal or near optimal |

Before 2016 the report used three classes: low 0-30, medium 30-70, high 70-100.

**Overall quality score.** The unweighted average of all indicator ratings, classed as below 40 very low to low, 40-60 medium, 60-80 high, and 80-100 very high.

**Worked example (manual, Figure 2.14), a silt loam under conventional small-grain management:**

| Indicator | Value | Rating |
|---|---|---|
| Available water capacity | 0.14 | 37 |
| Surface hardness | 260 | 12 (constraint: rooting, water transmission) |
| Subsurface hardness | 340 | 35 |
| Aggregate stability | 15.7 | 19 (constraint: aeration, infiltration, rooting, crusting, sealing, erosion, runoff) |
| Organic matter | 2.5 | 28 |
| ACE soil protein index | 5.1 | 25 |
| Soil respiration | 0.5 | 40 |
| Active carbon | 288 | 12 (constraint: energy source for soil biota) |
| pH | 6.5 | 100 |
| Extractable P | 20.0 | 100 |
| Extractable K | 150.6 | 100 |
| Minor elements | - | 100 |
| **Overall score** | | **51 / Medium** (mean of the twelve ratings = 50.7) |

The example shows the pattern the manual describes: chemical ratings are usually high because nutrients and pH are managed through routine testing, while the constraints appear in physical and biological indicators.

**Reference values in the manual for metrics in sections 1-4:**

- *pH:* optimum is around 6.2-6.8 for most crops (exceptions include potatoes and blueberries).
- *Salinity (1:1 soluble-salts test, EC in mmhos/cm):*

| Class | Coarse sand to loamy sand | Loamy fine sand to loam | Silt loam to clay loam | Silty clay loam to clay |
|---|---|---|---|---|
| Non-saline | 0-1.1 | 0-1.2 | 0-1.3 | 0-1.4 |
| Slightly saline | 1.2-2.4 | 1.3-2.4 | 1.4-2.5 | 1.5-2.8 |
| Moderately saline | 2.5-4.4 | 2.5-4.7 | 2.6-5.0 | 2.9-5.7 |
| Strongly saline | 4.5-8.9 | 4.8-9.4 | 5.1-10.1 | 5.8-11.4 |
| Very strongly saline | above 9.0 | above 9.5 | above 10.1 | above 11.5 |

- *Saline / sodic classification:* saline is ECe above 4 mmho/cm with pH below 8.5; sodic is ECe below 4 with pH above 8.5; saline-sodic is ECe above 4 with pH above 8.5.

**Guidance from the manual on interpretation:**

- The individual ratings, and especially the constraints, matter more than the overall score, which is useful mainly for relative comparison.
- The report is a management guide, not a prescription; there is no single prescribed treatment for a given constraint.
- Compare fields with care: different management, history, and soil type confound comparisons. Compare samples taken at a similar time of year and at similar soil moisture and temperature.
- Soil health changes slowly; for example, after conversion to no-till it may take 3-5 years before beneficial changes become noticeable.
- The scoring functions should be adjusted for other regions. The manual notes the framework was applied in western Kenya (Moebius-Clune et al. 2011).

### 5.4 Other indices

Karlen et al. compare four indices. The Soil Conditioning Index (SCI) predicts changes in organic matter but covers a single indicator. AEPAT, Cornell, and SMAF are more comprehensive because they include biological, chemical, and physical indicators. SHAPE (Soil Health Assessment Protocol and Evaluation) is a newer tool developed because of limitations in both SMAF and CASH.

### 5.5 Using the indices to track depletion

- Each index is relative to its own thresholds or reference database, so a score is meaningful mainly as a trend for the same field measured the same way.
- Keep the sampling depth, season, and moisture state constant between years (the SQI paper shows season and amendments shift results; the Cornell manual says the same).
- Report the limiting indicators with the index: the SQI paper's low-scoring TOC, Mg, moisture, sand, and PMN, or the red-rated constraints in CASH, show where depletion is concentrated.
- Use a general index only after checking that its indicator set and thresholds match the soil type and crop; none of the three is universal.

### Caveat

No single universal index exists. There is little consensus on how to measure soil quality, because soils have multiple functions and their properties interact. The minimum data set is specific to each soil type and function. Choose indicators suited to the soil and crop, and track trends over time. Without lab samples, trends can only be modelled (section 6), and the model output is a relative estimate with wide ranges, not a measurement.

## 6. What can be obtained for a field without lab samples

Sections 2–5 describe measurements made on soil samples or in the field. No satellite measures any of them directly for a single field, and most cannot be mapped at all. For an app where a farmer only draws a field polygon, each metric falls into one of three groups:

- **Static map value:** a modelled estimate from a soil map. It has no history and is often uncertain.
- **Model trend:** a value reconstructed from crop history, yields, climate and input priors.
- **Lab or farmer only:** a value that needs a sample, a field test or the farmer's own records.

Data source numbers (#) refer to the team's data guide (`space_apps_2026_data_sources.md`, section 2E).

### 6.1 Availability of each metric

| Metric | Static map value | Model trend | Lab or farmer only |
|---|---|---|---|
| SOC / organic matter | SoilGrids 250 m (#21), SSURGO in the US (#48), HWSD (#50), nearby WoSIS profiles (#49), GSOCseq starting stock (#46) | **Yes:** RothC or ICBM (#44–45), plus a humus balance (#38) | The field's current measured value |
| Available N, P, K | Total N only (SoilGrids). No reliable field-scale P or K map outside Africa | **Yes, as a balance:** removal (crop × yield × #37) minus inputs (#34–36, #39), as ranges | The actual soil-test P and K |
| Soil pH | SoilGrids, SSURGO | No (liming history is unknown) | Current value |
| Electrical conductivity | SSURGO (US) | No | Elsewhere |
| CEC | SoilGrids, SSURGO | No (mostly inherent) | — |
| Base saturation | SSURGO (US) | No | Elsewhere |
| Total N, Ca, Mg | Total N in SoilGrids; WoSIS profiles nearby | No | Ca, Mg |
| Bulk density | SoilGrids, SSURGO (static estimate only) | No (compaction from traffic is not modelled) | Measured value |
| Topsoil depth / erosion loss | Soil depth from SSURGO; slope from a DEM | **Relative risk only:** RUSLE with a crop cover factor (#41) | Measured loss |
| Aggregate stability | No | No | Yes |
| Water infiltration rate | SSURGO Ksat and hydrologic group (US) | No | Field test |
| Penetration resistance | No | No | Field test |
| Texture and water retention | SoilGrids, SSURGO | Inherent; no trend needed | — |
| Microbial biomass C, respiration, enzymes | No | No | Yes |
| Earthworm density, mycorrhizal fungi | No | No | Yes |
| Crop yield trend | County yields (Quick Stats #18, GDHY #32) | **Observable:** satellite yield proxies reach R² ≈ 0.45 for a field and ≈ 0.69 for a county | The farmer's own yield records |
| SQI, SMAF, CASH scores | No | No | Need the lab indicators above |

So the composite indices in section 5 work only when the farmer supplies a lab report. The app can accept such a report (for example a CASH report) as an anchor (section 6.2, step 6), but cannot compute the indices itself.

### 6.2 The modelled reconstruction

1. **Crop history.** Read the crop for each year from CSB in the US (#26) or a parcel register in the EU (#27–28). Elsewhere, use a crop map (#29–31) or the farmer's answers.
2. **Yield.** Use county yields from Quick Stats (#18) in the US, and GDHY (#32) or SPAM2020 (#33) elsewhere. The farmer's own yields replace these when given.
3. **Removal.** For each year, multiply yield by the N, P2O5 and K2O per tonne (#37). Add straw removal if straw is baled. Coefficients are in `crop_coefficients.csv`.
4. **Inputs (uncertain).** Fertilizer rates per crop come from IFA FUBC (#35), NuGIS county data in the US (#36) and the FAOSTAT budget (#34). Add legume N credits (#39). Manure and straw handling are unknown, so treat them as yes/no draws.
5. **Monte Carlo.** Run a few hundred draws over the inputs. Report the median and a 10–90% range for the nutrient balance and for SOC.
6. **Soil carbon.** Run RothC (#44) monthly, using:
   - climate from POWER (#1) or AgERA5 (#47);
   - clay from SSURGO (#48) or SoilGrids (#21);
   - starting SOC from the same maps, or from a soil test;
   - carbon inputs from yield and residue ratios;
   - months with soil cover from the crop calendar (#42).

   Use ICBM (#45) and the VDLUFA humus balance (#38) as cross-checks, and GSOCseq (#46) as a regional benchmark.
7. **Soil-test anchor (optional).** If the farmer uploads a soil test (SOC, P, K, pH), it sets RothC's starting point and the starting nutrient levels, and narrows the ranges.

Output is shown as a relative comparison between rotations, with ranges. An example: "Rotation A removes about 40–60 kg/ha/yr more K2O than B; SOC trend: falling in A, flat in B." It is never a claim about the field's current measured fertility.

### 6.3 How draining each crop is

Removal, humus balance, water demand and erosion risk are kept as **separate indices**; they are not combined into one score.

| Crop group | Humus balance (VDLUFA humus equivalents per ha per year) | Notes |
|---|---|---|
| Sugar beet | −1300 | High K removal |
| Potato | −1000 | High K removal |
| Grain maize | −800 | Large residue return if stover stays |
| Cereals | −400 to −520 | Straw returned adds +7 per dt |
| Grain legumes | +160 | Plus an N credit to the next crop |
| Alfalfa, clover | +800 | Plus a large N credit |

Per-crop removal (N, P2O5, K2O per tonne), FAO-56 Kc, RUSLE C factors and legume credits for 24 crops are in `crop_coefficients.csv`, with sources. Coefficients are missing for cotton, rice, sorghum, lentil and chickpea, as is K2O for canola, sunflower and pulses.

### 6.4 Validation and what to claim

- **Validate against:**
  - Rothamsted long-term experiments (#52) and KBS LTER (#53), for known depletion under known treatments.
  - LUCAS repeat topsoil samples (#51) in the EU.
  - NuGIS balances (#36) against TFI soil tests (#54) in the US. The published correlation is only ~0.45–0.65.
- **Expected error:**
  - Calibrated RothC errs by 3–25%.
  - Humus-balance validations reach R² of only 0.06–0.64.
  - The smallest SOC change detectable by resampling is 6–31% of the mean.
  - Crop-history labels from CDL are 85–95% accurate.
- **Credible:** nutrient removal history, relative comparison of rotations with ranges, and the direction of the SOC trend.
- **Not credible:** the field's current P or K level, absolute SOC, and any "depleted" claim that ignores fertilizer.

## Sources

Supplied papers (used for section 5):

- Damiba, W.A.F., Gathenya, J.M., Raude, J.M., Home, P.G. (2024). Soil quality index (SQI) for evaluating the sustainability status of Kakia-Esamburmbur catchment under three different land use types in Narok County, Kenya. *Heliyon* 10(5): e25611. https://doi.org/10.1016/j.heliyon.2024.e25611
- Pacci, S., Dengiz, O. (2021). Soil management assessment framework (SMAF) in assessment soil quality. International Symposium on "Soil Science and Plant Nutrition", Samsun, Turkey, 18-19 December 2021, pp. 46-50.
- Moebius-Clune, B.N., Moebius-Clune, D.J., Gugino, B.K., Idowu, O.J., Schindelbeck, R.R., Ristow, A.J., van Es, H.M., Thies, J.E., Shayler, H.A., McBride, M.B., Kurtz, K.S.M., Wolfe, D.W., Abawi, G.S. (2016). *Comprehensive Assessment of Soil Health: The Cornell Framework*, Edition 3.2. Cornell University, Geneva, NY.

Earlier sources:

- [ICAR - Indexing Methods of Soil Quality in Agro-Ecosystems](https://krishi.icar.gov.in/jspui/handle/123456789/44703)
- [Soil Quality Indices; Salt-affected Soil, Northern Egypt](https://journals.ekb.eg/article_3333.html)
- [Scientia Agricultura Sinica 2021, minimum data set bibliometrics](https://www.chinaagrisci.com/EN/Y2021/V54/I14/3043)
- [Analysis of soil quality indicators and indices in Mexico](https://cienciasagricolas.inifap.gob.mx/index.php/agricolas/es/article/download/3148/6053/32351?inline=1)
- [Musinguzi et al. - SOC Thresholds and Nitrogen Management (JRC)](https://publications.jrc.ec.europa.eu/repository/handle/JRC85704)
- [Vallejos Torres et al. 2023 - SOC critical threshold, Peruvian Amazon](https://agris.fao.org/search/ar/records/662916512b3930d7cdc0a29c)
- [USDA-NRCS - Bulk Density](https://soilquality.nres.illinois.edu/bulk-density/)
- [UF/IFAS - Critical bulk density values](https://hort.ifas.ufl.edu/woody/critical-value.shtml)
- [USDA-NRCS - Biological Indicators and Soil Functions](https://www.nrcs.usda.gov/sites/default/files/2023-01/Indicators-Biological-Indicators-and-Soil-Functions.pdf)
- [SMAF scoring protocol (Cambridge)](https://core-cms.cambridgecore.org/core/journals/renewable-agriculture-and-food-systems/article/protocol-for-indicator-scoring-in-the-soil-management-assessment-framework-smaf/3B3C2C94F977CEFF8D294D87B0D06DBF)
- [Cornell Soil Health Assessment Framework](https://scisoc.confex.com/crops/2015am/webprogram/Paper94590.html)
- [Nunes et al. 2021 - SHAPE](https://soilhealthprogram.cals.cornell.edu/files/2022/01/Nunes-et-al-2021-The-soil-health-assessment-protocol-and-evaluation-applied-to-soil-organic-carbon.pdf)
- [Karlen et al. - Soil Quality Assessment: Past, Present and Future](https://works.bepress.com/douglas_karlen/10/)

Sources for section 6 (reconstruction; see the data guide section 2E for data links):

- [RothC model code (Rothamsted)](https://github.com/Rothamsted-Models/RothC_Code) and [model page](https://www.rothamsted.ac.uk/rothamsted-carbon-model-rothc)
- [ICBM in SoilR](https://rdrr.io/cran/SoilR/man/ICBMModel.html)
- [FAO GSOCseq: running the RothC model](https://www.fao.org/fileadmin/user_upload/soils/Joint_trainings/Dec2022-OCB_GSP/4._GSOCseq_Running_the_RothC_Model.pdf)
- [CoolFarm: two SOC models in Python](https://coolfarm.org/from-theory-to-practice-the-4-key-advantages-of-implementing-two-soc-models-in-python/)
- [LfL Bayern: VDLUFA humus balance](https://www.lfl.bayern.de/mam/cms07/iab/dateien/humusbilanz_beratung_bleistift-version_nov_2014_2.pdf)
- [Agroscope: humus balance validation](https://ira.agroscope.ch/de-CH/publication/57805)
- [Düngeverordnung Anlage 7 (nutrient contents of crops)](https://www.gesetze-im-internet.de/d_v_2017/anlage_7.html)
- [OMAFRA crop nutrient removal](https://fieldcropnews.com/?p=28952)
- [Iowa State PM 1688](https://store.extension.iastate.edu/Product/5232-pdf)
- [Wisconsin A3591 (legume N credits)](https://corn.aae.wisc.edu/Management/pdfs/A3591.pdf)
- [FAO-56 crop coefficients](https://www.fao.org/4/x0490e/x0490e0b.htm)
- [OMAFRA USLE factsheet](https://files.ontario.ca/omafra-universal-soil-loss-equation-23-005-en-2023-03-02.pdf)
- Ludemann et al. (2024). A global FAOSTAT reference database of cropland nutrient budgets and nutrient use efficiency (1961–2020). *Earth System Science Data* 16: 525–541. https://essd.copernicus.org/articles/16/525/2024/
- Ludemann, Gruère, Heffer, Dobermann (2022). Global data on fertilizer use by crop and by country. *Scientific Data* 9: 501. https://doi.org/10.1038/s41597-022-01592-z
- [NuGIS county nutrient balances (TFI)](https://nugis.tfi.org/) and [TFI soil test summary](https://soiltest.tfi.org/about)
- [Rothamsted e-RA data availability](https://www.era.rothamsted.ac.uk/info/RLTEdatavailable)
- [ESDAC: SOC changes 2009–2018 (LUCAS)](https://esdac.jrc.ec.europa.eu/content/SOC-changes-2009-18)
