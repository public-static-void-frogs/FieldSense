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

| Part     | Definition                                                                                                                                                                                                                 |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| State    | Plan year, the last five crops, two soil carbon pools, and the year just experienced. |
| Action   | Crop × tillage (`conventional`, `strip_till`, `no_till`) × cover crop before it (`none`, `rye`). Invalid combinations are masked: a standing perennial is not tilled, and rye goes only before warm-season annual crops.   |
| Chance   | One whole historical year is drawn each step: its weather, yields and prices together, so their real correlation is kept. The odds of each year depend on the year just experienced (see below). |
| Reward   | USD per acre per year: revenue − production cost − risk penalty + soil carbon value. Land cost is excluded.                                                                                                                |
| Dynamics | The crop history shifts by one and the soil carbon pools take one yearly step; the year just experienced is the drawn year. |

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
    --summaries data/local/usa_sample/season_summary data/local/planner/season_summary \
    --out data/local/planner/tables_1981 --workers 14
python rule_engine/planner/scripts/train_policy.py \
    --tables data/local/planner/tables_1981 --out data/local/planner/policy_1981 \
    --iterations 1500 --hidden 512 --entropy 0.01
python -m rule_engine.planner --field <id> ... --policy data/local/planner/policy_1981/policy.pt
```

- `tabular.py` turns each field's problem into arrays (reward of every action in every crop
  history and drawable year). Exact solving and scoring a policy then take milliseconds per field,
  and the trainer steps thousands of fields at once on a GPU.
- `ppo.py` is PPO with action masking, written directly in PyTorch. Whole counties are held out
  (`is_test_county`), so the test fields are in places the policy never saw.
- Every score is the exact expected plan value of the policy, not a sampled return.

Result of the run above with the years 1981–2025 (9,969 fields with at least two modellable
crops; 8,859 for training, 1,110 in held-out counties; 6 minutes on one GPU; USD per acre over
five years):

| Held-out fields | Exact optimum | Learned policy | Year-by-year rule | Gap closed |
| --------------- | ------------- | -------------- | ----------------- | ---------- |
| All 1,110       | 494.4         | 489.9          | 445.9             | 91 %       |
| 2 crops (474)   | 304.8         | 303.5          | 289.3             | 91 %       |
| 3 crops (283)   | 679.6         | 674.0          | 596.9             | 93 %       |
| 4 crops (353)   | 600.5         | 592.7          | 535.1             | 88 %       |

The learned policy is within 1 % of the optimum on 82 % of held-out fields. It beats the
year-by-year rule on 49 % of them (by 92 USD on average), ties on 42 %, and trails it on 9 % (by
12 USD on average, 84 USD at worst). It is an approximation: where the exact plan is affordable, use
it. With only the years 2015–2025 the same training closed 91 % of the gap too (optimum 472.0,
learned 467.5, year-by-year rule 421.0).

The vocabulary is fixed at corn, soybeans, oats and alfalfa (`tabular.CROPS`), the crops with a
cost budget. Adding a crop means retraining.

## Where each number comes from

- **Yield.** The expected yield today (county trend for corn and soybeans, state series for other
  crops) × that year's observed anomaly × the rule engine's rotation yield factors. An observed
  yield already contains that year's weather. When a year has no observed yield, the anomaly is
  modelled from the season's hazards with `data/weather_yield_response.csv`.
- **Price.** That year's marketing-year price relative to the price level of its time, times the
  rule engine's current planning price. A series of 20 years or more is divided by its log-linear
  trend, so a 1985 price counts as high or low for 1985, not against today's dollars. Shorter
  series are only rescaled to their mean. `data/nass_long_history.csv`
  (`scripts/fetch_long_history.py`) holds state and national prices since 1980.
- **Cost.** `data/costs.csv` (Iowa State University 2026 crop budgets and custom rates) and
  `data/cover_costs.csv`.
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
