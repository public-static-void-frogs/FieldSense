# Rotation planner

A multi-year planning layer on top of the rule engine. The rule engine scores one crop for one
coming year; the planner chooses a sequence of crops, tillage systems and cover crops over several
years, because each choice changes what the rules say about the next one.

```sh
python -m rule_engine.planner --field 191825000034355 \
    --fields data/local/usa_sample/fields.jsonl \
    --summaries data/local/usa_sample/season_summary data/local/planner/season_summary \
    --horizon 5 --q-learning 20000
```

## The decision problem

| Part     | Definition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| State    | Plan year, the last five crops, two soil carbon pools, and the year just experienced.                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Action   | Crop × tillage (`conventional`, `strip_till`, `no_till`) × cover crop before it (`none`, `rye`). Invalid combinations are masked: a standing perennial is not tilled, and rye goes only before warm-season annual crops. A perennial stand is kept for its minimum life and ended at its maximum (`crop_adjustments.csv`: sugarcane stands three harvests, then a fallow year). Sugarbeets and flax come back no sooner than every third year (`{crop}_min_return_years`: NDSU guidance; CDL shows 6.9 % of beet and 4.2 % of flax fields returning sooner). |
| Chance   | One whole historical year is drawn each step: its weather, yields and prices together, so their real correlation is kept. The odds of each year depend on the year just experienced (see below).                                                                                                                                                                                                                                                                                                                                                             |
| Reward   | USD per acre per year: revenue − production cost − risk penalty + soil carbon value. Land cost is excluded.                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Dynamics | The crop history shifts by one and the soil carbon pools take one yearly step; the year just experienced is the drawn year.                                                                                                                                                                                                                                                                                                                                                                                                                                  |

Sugarbeets, sugarcane and potatoes are sold under contract to a nearby factory, mill or packer.
They are planned only in the counties of `data/processor_counties.csv`
(`scripts/build_processor_counties.py`: at least 0.5 % of the county's sampled CSB acres in CDL
2021-2025), on a field whose history shows the crop, or when the farmer enters its cost. Any
other field reports gap code `no_processor_nearby`.

`exact_plan` solves the problem by dynamic programming and is the reference. `RotationEnv` exposes
the same model with Gymnasium-style `reset` and `step` for learning agents; `q_learning` is the
reference learner. Every plan is scored by `evaluate`, the exact expected value of a policy.

## Carry-over between years

Two conditions are known before planting and shift the odds of the coming year (`chance.py`):

- **Drought.** The Drought Monitor class at the end of one season against the class at the start
  of the next. Across the national sample (102,570 field-year pairs, 2015–2025) they correlate at
  0.45. Counties that started the season in D1 or worse had corn yields 4–6 % below their mean.
- **Price.** The price level of the year just finished against the level preceding each
  candidate year.

The next year is drawn from the historical years, weighted by how closely each year's starting
conditions match the conditions just reached. `Persistence(strength, bandwidth)` sets how strongly:
strength 0 gives independent years.

With carry-over the best plan is a policy that reacts to the year just experienced, not a fixed
sequence. `open_loop_plan` gives the best fixed sequence, so the difference between the two is the
value of adapting. On 12 Iowa sample fields over four years it was 0–16 USD per acre in total,
at most about 2 % of the plan value: prices of the main crops move together, so the year
just experienced rarely changes which crop is best. The plan's first year shifts more than that,
because its odds are conditioned on the latest real year instead of an average year.

## One learned policy for all fields

`exact_plan` needs the full model of one field and several seconds. `ppo.py` trains a single
network that plans for any field from its soil, position, crop history and the rule engine's
one-year scores, in milliseconds.

```sh
python rule_engine/planner/scripts/build_tables.py \
    --fields data/local/usa_sample/fields.jsonl \
    --summaries data/local/usa_sample/season_summary \
    --climate data/local/usa_sample/climate_record \
    --out data/local/planner/tables --workers 8
python rule_engine/planner/scripts/train_policy.py \
    --tables data/local/planner/tables --out data/local/planner/policy \
    --iterations 1500 --hidden 512 --entropy 0.01
python -m rule_engine.planner --field <id> ... --policy data/local/planner/policy/policy.pt
```

`--climate` gives the tables the same long weather record the backend plans with
(`context.with_climate`), so the policy is trained on what it will be asked at serving time.

- `tabular.py` turns each field's problem into arrays (reward of every action in every crop
  history and drawable year). Exact solving and scoring a policy then take milliseconds per field,
  and the trainer steps thousands of fields at once on a GPU.
- `ppo.py` is PPO with action masking, written directly in PyTorch. Whole counties are held out
  (`is_test_county`), so the test fields are in places the policy never saw.
- Every score is the exact expected plan value of the policy, not a sampled return.

Result of a short run with the 25-crop vocabulary, the years 1981–2025 and inflation-adjusted
prices. It used a sample of the fields, not all of them: the first 1,000 fields of the list plus
every sixth of the rest, 2,543 in all; 2,254 for training, 289 in held-out counties; 9 minutes
(1,238 iterations) on one GPU; USD per acre over five years:

| Held-out fields | Exact optimum | Learned policy | Year-by-year rule | Gap closed |
| --------------- | ------------- | -------------- | ----------------- | ---------- |
| All 289         | 611.5         | 600.8          | 547.6             | 83 %       |
| 3 crops (16)    | 834.1         | 833.2          | 714.4             | 99 %       |
| 4 crops (10)    | 488.6         | 463.4          | 441.8             | 46 %       |
| 5 crops (262)   | 606.2         | 595.4          | 544.8             | 82 %       |

One held-out field has two crops and is not shown; a table holds at most five crops per field.
The learned policy is within 1 % of the optimum
on 69 % of held-out fields, falls 10.7 USD short of it on average, and trails the year-by-year
rule on 18 %. On its training fields it closes 94 % of the gap. It is an approximation: where the
exact plan is affordable, use it. A longer run on every field is the next step.

The vocabulary is the 25 crops of `tables.CROPS`, in that order. A policy file stores the crop
order it was trained with, and `learned.load_policy` refuses a file whose order or sizes differ
(`policy_does_not_fit`). Adding a crop means adding it at the end of `CROPS` and retraining.

### Serving the learned plan

`GET /fields/{id}/rotation-advice?planner=learned` builds the plan with the policy;
`planner=exact` (the default) keeps the exact calculation.

- The backend reads the policy once from `ROTATION_POLICY_PATH` (default
  `data/local/planner/policy/policy.pt`, which is not in git: copy the file to the server).
- `plan.method` is `learned_policy` or `dynamic_programming_fixed_sequence`.
- `plan.planner` reports what was asked for, what was used, and whether a policy is loaded
  (`learnedAvailable`, with the reason code in `learnedUnavailable` when it is not).
- Each plan crop of a learned plan has `belowOptimumUsdPerAcre`: how far it is below the exact
  best plan that starts with the same crop.
- The server needs PyTorch for it: `pip install -r backend/requirements-ml.txt`.
- Without a usable policy file, or without PyTorch installed, the exact plan is returned.
- `train_policy.py --minutes N` stops training after N minutes; the learning-rate and entropy
  schedules then follow the clock.

## Where each number comes from

- **Yield.** The expected yield today (county trend for corn and soybeans, state series for other
  crops) × that year's observed anomaly × the rule engine's rotation yield factors. An observed
  yield already contains that year's weather. When a year has no observed yield, the anomaly is
  modelled from the season's hazards with `data/weather_yield_response.csv`.
- **Rotation yield factors, calibrated.** `scripts/calibrate_yield_factors.py` blends each
  literature range (read as midpoint ± 2 sd) with measured yields by inverse variance:
  - corn after corn: the same-field MODIS greenness panel (`scripts/ndvi_field_panel.py`),
    0.42 % greenness-implied loss scaled ×9.2 (the attenuation found on soybeans after
    soybeans against Seifert et al. 2017's 10.3 %) = 3.9 ± 0.9 %; with the prior 9.5 ± 2.75 %:
    4.4 ± 0.9 %, factor [0.94, 0.97] (was [0.85, 0.96]);
  - rotation benefit (corn and soybeans after a small grain or hay, against after each other,
    same field, `scripts/small_grain_field_panel.py`): corn +7.5 ± 2.2 %, soybeans
    +5.3 ± 3.6 %; with the prior 4.5 ± 2.25 %: +5.9 ± 1.4 %, factor [1.03, 1.09] (was
    [1.00, 1.09]);
  - soybeans after soybeans: Seifert 10.3 % with the county panel (`scripts/repeat_yield_panel.py`)
    8.9 ± 3.8 %: 10.2 ± 1.0 %, the new rule `soy_after_soy_yield_penalty` [0.88, 0.92].

  The county panel's corn rows are not used: a corn-after-corn share also "raises" soybean yield
  there, so something that lifts both crops is mixed in. It is not soil:
  `scripts/land_controlled_panel.py` adds the NCCPI of the acres in each crop every county-year
  (SSURGO via the CSB sample), and the corn coefficient does not move (−3.9 ± 5.3 % with and
  without; corn-after-corn fields' soil is worth −0.1 % yield against other corn fields, and
  the county's land index varies by under 1 % of yield from year to year). County fixed effects
  already remove fixed soil. Controlling for the county's soybean yield the same year (local
  weather, management) gives corn after corn −8.6 ± 4.0 % with the placebo gone (−1.1 ± 3.2 %),
  in line with the calibrated 4.4 ± 0.9 %; the same control fails its placebo for soybeans, so
  it is a cross-check and is not blended in. The greenness numbers are attenuated
  (250 m pixels mix neighbouring fields) and the scale comes from one crop. Fields of 40 acres
  and more give the same corn factor ([0.93, 0.98]), but a corn rotation gain of 17 ± 5 %, so
  the benefit is uncertain.

  The other yield factors keep their literature ranges. `scripts/ndvi_rule_panel.py` runs the
  same same-field greenness test on them, with each crop's own growing window and county-yield
  slope, but only as a check of direction: the canopy shows about a twelfth of the soybean
  trial loss, so a greenness change is a floor on the yield change and is not blended in.
  - Take-all (a cereal after a host cereal, against a non-host): spring wheat −1.6 ± 0.5 %
    greenness, durum −2.5 ± 0.5 %, barley −2.8 ± 0.7 %. These are yield floors of 3 to 7 %, in
    the direction of [0.80, 0.95].
  - Take-all in winter wheat: against all non-hosts it comes out +1.7 %. Wheat after soybeans or
    sorghum goes in late, and wheat after wheat or fallow does not, so the planting date is mixed
    in. Against early-harvested non-hosts (oats, canola, peas, lentils) it is −1.8 ± 0.9 %
    (−3.3 ± 1.5 % on 40 acres and more).
  - Peanuts (after peanuts +0.1 ± 1.0 %, after a one-year break −0.4 ± 0.6 %) and potatoes
    (+2.3 ± 1.3 %): no loss shows in the canopy. These rules lose yield to pod and tuber
    disease, which leaves the canopy green, so their trial ranges stand.
  - Sugarbeets, pulses, chickpeas and flax have too few repeat fields in the sample.

  The late planting of winter wheat after a fall harvest is not a rule. The weekly plan
  (`weekly.py`) frees the field only after the previous crop's harvest and charges the days past
  the usual planting date (`data/planting_date_response.csv`), so a sequence factor would count
  it twice.

  Each end of a literature range is a published trial or farm-record figure (see the rule's
  comment), with three exceptions:
  - chickpea after pea or lentil borrows the pea range;
  - flax is farm records;
  - the 0.87 end of the two rye-before-corn rules is ISU SP 435's mean less one SD.

- **Price.** The rule engine's current planning price × that year's price change: the year's
  marketing-year price over the previous year's, in constant dollars (CPI-U, `data/cpi_u.csv`),
  scaled to mean 1. See [Backtest](#backtest) for why it is the change and not the price level. `data/nass_long_history.csv`
  (`scripts/fetch_long_history.py`) holds state and national prices since 1980.
- **Cost.** Land excluded, so the reward is a return to land. The ERS regional table
  (`data/costs_regional.csv`) sets the level for the crops ERS surveys; `data/costs.csv`
  (ISU 2026 for corn, soybeans, alfalfa and pasture; UNL 2026 for oats, wheat, sorghum, Panhandle
  sugarbeets and millet; NDSU 2026 for peas, lentils and flax; LSU 2025 for sugarcane) gives
  the rest and the tillage differences; `data/costs_state.csv` overrides by state (Red River
  Valley sugarbeets from the Moorhead farm business records; Washington and Oregon potatoes).
  Unverified rows: potatoes (no budget after 2019, inflated by CPI-U; storage to April
  included because the NASS price includes potatoes sold from storage), chickpeas (a 2026
  Saskatchewan budget at an assumed 0.72 USD per CAD), the low-till rows standing in for
  no-till, and ERS wheat classes in regions where the class is under 5 % of the survey's wheat
  acres. The NASS sugarcane price is per ton of cane for the grower and landlord shares
  together, after the mill's in-kind share, so it is used as is: the LSU cost excludes both
  in-kind shares, and the landlord's sixth is the return to land. `data/cover_costs.csv` prices
  the cover crops.
- **Risk penalty.** Rule engine points × `Weights.risk_usd_per_point`. A finding that carries a
  yield factor is paid through yield and its points are not counted again.
- **Soil carbon.** A two-pool yearly model (`dynamics.SoilCarbon`) fed by residue from
  `data/soil_carbon.csv`, valued at `Weights.soil_usd_per_t_c`.

The weights are preferences, not data. Every table row has a `verified` column and a source.

## Building the earlier years

The national sample ships season summaries for 2021–2025. The planner draws from 1981–2025:

```sh
bash rule_engine/planner/scripts/fetch_gridmet_history.sh 1981 2014      # weather at each field
python rule_engine/planner/scripts/fetch_county_yields.py                # NASS county yields
python rule_engine/planner/scripts/build_history_summaries.py \
    --sample data/local/usa_sample --work data/local/planner --years $(seq 1981 2020)
```

The sources do not all reach 1981:

| Source                               | First year | Before that                                   |
| ------------------------------------ | ---------- | --------------------------------------------- |
| gridMET weather, NASS yields, prices | 1981       |                                               |
| RMA cause of loss (previous year)    | 1990       | empty                                         |
| Drought Monitor                      | 2000       | no drought signal; year odds use price only   |
| Previous crop from CDL               | 2018       | empty (the plan uses the field's own history) |

## The forecast and the farmer's own results

- `solve.crop_options` gives, for every crop, the best fixed plan that starts with it.
  `solve.replay` runs a fixed plan through the past years in cash terms (sales less production
  cost; land is not charged).
- The first season is replayed under every past year, weighted by the year odds. The whole plan is
  started in each past year and run through the years that really followed.
- A farmer's declared crops replace the satellite labels in the history. Declared yields set the
  field's yield level relative to the reference yield, from the latest 10 years; with fewer than 4
  years of a crop the missing years count at ratio 1.0 (`sampler.OWN_YIELD_MAX_YEARS`,
  `OWN_YIELD_MIN_YEARS`).
- A county yield of zero in the season summary means "no record" and is treated as missing.
- The farmer's own economics arrive in `field["economics"]`:
  - `prices` replaces a crop's planning price (past years still move around it).
  - `costs` replaces a crop's cost level (`CostTable.override`: conventional tillage, after a
    different crop).
  - `landRent` is charged in every season; without it land is not charged.
  - `costChanges` is the soil-test effect below, skipped for a crop with a farmer's cost.
- `nutrients.py` turns soil-test phosphorus and potassium into a cost change: the Iowa State
  category of the test (`data/soil_test_categories.csv`), the recommended rate less the
  maintenance rate (`data/soil_test_rates.csv`), times the fertilizer price
  (`data/fertilizer_prices.csv`). Corn and soybeans only; the yield is not changed. Outside Iowa
  the entry is marked `iowa_applied_elsewhere`.
- `soil_level.py` places a field within its county by the NCCPI soil productivity index, when
  the farmer gave no yields: expected yield = county level x (1 + slope x (field index - county
  mean)), within +/- 15 %. The slope is our own estimate (see the module); county means are in
  `data/county_nccpi.csv` (`scripts/build_county_nccpi.py`). `rule_engine/ssurgo.py` fetches the
  index with the soil; `scripts/fetch_soil_extra.py` fetches it for a whole sample.
- `data/cash_rent.csv` holds NASS cash rents by county and state
  (`scripts/fetch_cash_rent.py`). It is only a default for the calculator form.

The HTTP contract is in `backend/docs/rotation-plan.md`.

## Limits

- Crop history is a satellite estimate (USDA CDL/CSB), not a farmer's declaration. The plan output
  repeats this under `dataGaps`.
- The small-grain and sorghum costs are Nebraska operating costs without machinery ownership, so
  those crops look cheaper than the Iowa corn and soybean budgets beside them.
- The soil carbon parameters come from the literature and are not calibrated to these fields.
- The weather response table covers corn and soybeans only. It has no rows for spring frost, small
  grains or alfalfa.
- The year odds rest on 45 historical years (about 30 effective analog years on the example
  field). They show direction, not calibrated probabilities.
- Years since 1981 are treated as equally likely weather for the coming seasons. Yields are
  detrended, but a warming trend in the weather itself is not modelled.
- The exact plan takes about 50 seconds per field with 45 years (9 seconds with 11).
- Tabular Q-learning needs far more episodes once the state tracks the year just experienced
  (200,000 episodes reached 96 % of the exact value on the example field; 20,000 reached 84 %).
- Pest and disease pressure enters only through the rotation rules, as a deterministic effect.

## Backtest

`scripts/backtest.py` forecasts the first season of every past year from earlier years only and
compares it with what happened: county yield × that year's price − the ERS regional cost of that
year (`data/costs_regional_history.csv`, land excluded). Run on the 30,000-field sample
(one field per county, counties with at least 15 earlier yields), target years 1997–2025:
45,793 corn forecasts in 2,018 counties and 36,888 soybean forecasts in 1,673 counties.

| Forecast variant                                 | Crop     | Mean predicted loss chance | Observed loss share | Brier skill | Actual inside p10–p90 | Mean net forecast / actual, USD/ac |
| ------------------------------------------------ | -------- | -------------------------- | ------------------- | ----------- | --------------------- | ---------------------------------- |
| Price level, analog odds (the model before)      | corn     | 0.59                       | 0.38                | 0.11        | 0.63                  | 33 / 82                            |
| Price level, equal odds                          | corn     | 0.51                       | 0.38                | 0.31        | 0.88                  | 58 / 82                            |
| Price change, trend one year ahead, equal odds   | corn     | 0.44                       | 0.38                | 0.39        | 0.75                  | 78 / 82                            |
| Price change, trend one year ahead, analog (now) | corn     | 0.41                       | 0.38                | 0.41        | 0.75                  | 87 / 82                            |
| Price level, analog odds (the model before)      | soybeans | 0.41                       | 0.24                | 0.15        | 0.68                  | 69 / 101                           |
| Price level, equal odds                          | soybeans | 0.35                       | 0.24                | 0.32        | 0.83                  | 84 / 101                           |
| Price change, trend one year ahead, equal odds   | soybeans | 0.28                       | 0.24                | 0.37        | 0.75                  | 99 / 101                           |
| Price change, trend one year ahead, analog (now) | soybeans | 0.25                       | 0.24                | 0.36        | 0.71                  | 106 / 101                          |

Brier skill is 1 − Brier score ÷ the Brier score of always predicting the observed loss share
(0 = no better than that constant, 1 = perfect).

What it shows:

- **The price level was the error.** With constant-dollar price levels, most recent years sit
  below the planning price, so a predicted 37 % loss chance came true 13 % of the time for corn.
  With price changes the same bin comes true 34 % of the time (bins for the current model, corn:
  predicted 3 / 17 / 37 / 63 / 90 %, observed 4 / 15 / 34 / 58 / 82 %).
- **The p10–p90 range is somewhat narrow**: it should hold 80 % of the outcomes and holds 71–75 %.
- **Analog odds add little** over equal odds once the price is right: slightly better for corn,
  slightly worse for soybeans.
- **Yield**: the mean absolute error of the expected yield is 18.6 bu/ac for corn and 5.6 for
  soybeans, against 19.6 and 5.8 for the mean of the last five years.
- **A year is mostly one draw.** Counties share the price, so the 29 years are far fewer
  independent tests than the forecast count suggests. Mean predicted and observed loss share per
  year correlate at 0.77 (corn) and 0.73 (soybeans).

Limits: this tests the county-level forecast of corn and soybeans, the first season only. It
does not test how a field differs from its county, the other crops, the rotation effects or the
later seasons of a plan. The backtest's planning price is the previous year's price; the live
one is the crop insurance projected price, which is based on futures.
