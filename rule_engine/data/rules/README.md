# Rotation rules

Each `*.yaml` file here holds a list under `rules:`. A rule fires for a **candidate crop** on a
field when its `applies_to` selector matches the candidate and every `when` condition holds
(or, for timed hazards, when at least one past season hit the `hazard`). Nothing is coded in
Python: add or tune a rule by editing these files.

Rules carry no prose. The engine reports each firing rule with its id, level, points and a
structured `trigger` (the conditions with their actual fact values, or the hazard window with
per-season values), and the consumer (an LLM agent or the UI) writes the wording. A rule that
still has an `explanation` key is rejected at load time.

```yaml
- id: corn_rootworm_continuous          # stable identifier
  title: Corn rootworm pressure         # short name shown to the farmer
  category: pest_disease               # pest_disease | soil_nutrient | erosion | water |
                                       # temperature | diversity | yield | market | weed
  applies_to: {crops: [corn]}          # any of: crops: [...], groups: [...], traits: ["n_fixer=true"]
  when:                                # all conditions must hold (AND); missing fact = false
    - {fact: history.consecutive_same_crop, op: ge, value: 1}
  effect: {kind: risk, level: high}    # kind: risk | benefit | advisory
  evidence_strength: strong            # strong | moderate | weak
  sources: ["..."]
  needs_local_review: true
```

Timed hazards replace `when` with a `hazard` block evaluated per past season on the field:

```yaml
  hazard:
    stage: flowering                   # stage from the crop calendar (planted, emerged, flowering,
                                       # grain_fill, mature, harvested). If the crop's
                                       # calendar lacks the stage (fall-sown cereals have no
                                       # in-season planting), the rule is skipped with a
                                       # hazard_stage_not_in_calendar gap.
    window_days: [-10, 10]             # days around the stage median
    metric: tmax_ge35_days             # a weekly summary metric (see rule_engine/summary.py)
    aggregate: sum                     # sum | min | max over the window
    compare: ge                        # season "hit" when aggregate <compare> threshold
    threshold: 1
  effect:
    kind: risk
    level_bands: {high: 0.5, medium: 0.25, low: 0.0}   # share of seasons hit → level
```

Facts available to `when` (prefix list is validated at load time):

- `candidate.crop`, `candidate.group`, and every trait as `candidate.<trait>`
  (`family`, `n_fixer`, `n_demand`, `water_demand`, `rusle_c`, `bare_soil_months`,
  `min_return_years`, `humus_balance`, `hosts`, ...).
- `history.years` (seasons of history known), `history.prev1.crop|group|family|n_fixer|hosts`,
  `history.consecutive_same_crop`, `history.consecutive_same_family`,
  `history.years_since_same_family` (null if never grown), `history.distinct_groups_5y`,
  `history.share_same_crop_5y`, `history.corn_soy_alternation_years`,
  `history.shared_hosts_prev1` (hosts in common between the candidate and last year's crop).
- `county.rma_drought_share_lag1`, `county.rma_excess_moisture_share_lag1`,
  `county.rma_heat_share_lag1`, `county.rma_freeze_share_lag1`, `county.rma_hail_share_lag1`.
- `field.has_history`, `field.has_seasons`.
- `field.soil.<key>`: whatever the caller put in `field["soil"]` (`slope_pct`, `drainage_class`,
  `aws_100cm_mm`, `sand_pct`, `ph`, `caco3_pct`, `nirr_class`, `hel`, ...), plus the derived
  `field.soil.wetness` = `wet | somewhat_wet | not_wet | tiled` (drainage class, overridden by
  `field.practice.tile_drained`).
- `field.practice.<key>`: `tillage`, `tile_drained`, `cover_crop`, `cover_termination_days`,
  `weed_escapes`, plus `field.practice.cover_planned`, which is always present (false when no
  cover crop is declared). `drainage_class`, `tillage` and `cover_crop` are normalised to
  lower snake_case (`Poorly drained` becomes `poorly_drained`).
- `herbicide.*`, computed per candidate from `field["practices"]["herbicides"]` and
  `data/herbicide_plantback.csv` (see `herbicide.py`): `herbicide.provided`,
  `herbicide.shortfall_months` (label interval minus months from application to planting the
  candidate, floored at 0; absent when no declared active has an interval for the crop),
  `herbicide.limiting_active`, `herbicide.restricted_actives`,
  `herbicide.late_restricted_count` (applied in July or later), `herbicide.repeated_groups`
  and `herbicide.repeated_group_count` (same WSSA group in the last two seasons).

A soil or practice fact the caller did not supply is simply missing, so every condition on it
is false except `is_null`. Use `is_null` for fallbacks (see `sandy_soil_high_water_demand`),
never `ne`. The `weed` category counts under the `pest_break` priority.

`history.candidate_group_in_5y` is also available. Rules whose finding depends on a trait flagged `verified: false` in the catalog list that
trait under `uses_traits`; the engine downgrades them to `weak` evidence and adds a data gap.
