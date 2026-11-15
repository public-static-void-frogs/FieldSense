# Rotation plan, forecast and farmer inputs

`GET /api/v1/fields/{field_id}/rotation-advice` returns the rotation risks for every catalog crop
and, when the field has planner data, a `plan` block. All money is USD per acre and all yields are
per acre in the crop's own unit. The response holds codes and numbers only; the frontend owns the
wording.

## Query parameters

| Parameter    | Meaning                                                      |
| ------------ | ------------------------------------------------------------ |
| `crop`       | The crop the farmer intends to grow. Default: the last crop. |
| `priorities` | Rule categories that count double.                           |
| `seasons`    | Seasons to plan, 1 to 5. Default 3. Anything else gives 422. |

## The plan

For each crop that has a yield, a price and a cost budget, the planner finds the best fixed plan
that starts with that crop. Plans are ordered by their objective: sales less production cost, less
a charge for each rotation risk, plus the value of soil carbon gained.

- `plan.crops[]` holds one entry per priced crop, with `rank` and `tier` (`top` for the first
  three, `alternative` for the rest).
- `steps[]` lists each season: crop, tillage, what to sow the autumn before, expected yield, sales,
  cost and the cash result. `worstYearUsdPerAcre` and `bestYearUsdPerAcre` are cash as well.
- `autumn` says what to do this autumn and what a rye cover crop would add or cost.
- `plan.notModelled[]` lists crops left out, with the reason (`no_cost_budget`, `no_price`,
  `no_yield`). They stay in `candidates` with their rotation risk.
- `plan.gaps[]` lists what the numbers rest on, for example `cost_budget_from_another_state` or
  `yield_not_observed_every_year`.

Cash results include land rent only when the farmer entered one (see the calculator below).
`plan.economics` says which price, cost and rent the plan used and where each came from.

## The forecast (`simulation`)

The plan is replayed through every past year on record: that year's weather and yield, and that
year's price change. The price of a drawn year is the planning price times the change of the real
price from the year before to that year, so the spread is centred on the planning price.

- `simulation.firstSeason` is the forecast for the first season. Each past year is one entry in
  `outcomes[]` with its `probability`, cash result, yield, price and `yieldMode`.
  - `lossProbability`, `p10`, `p50`, `p90` and the mean are weighted by those probabilities.
  - `beatsTopProbability` is the share of years in which this crop earns at least as much as the
    first-ranked crop.
- `simulation.plan` runs the whole plan from each start year through the years that really
  followed it, and reports the spread of the total.
- `plan.yearOdds` says how the past years were weighted: `analog_years` (years that resemble the
  current drought and price situation count more) or `equal`.

`yieldMode` per year:

| Value      | Meaning                                                              |
| ---------- | -------------------------------------------------------------------- |
| `observed` | A county yield (corn, soybeans) or state yield (other crops).        |
| `modelled` | No record for that year; published weather losses applied instead.   |
| `none`     | No record and no weather response; the expected yield is used as is. |

The probabilities are how often something happened in the record. A backtest (forecasts for
1997-2025, each made only from earlier years) found the loss probability close to what happened:
see the Backtest section of `rule_engine/planner/README.md`.

## The farmer's seasons

`GET` and `PUT /api/v1/fields/{field_id}/season-results` read and replace the farmer's own record:

```json
{ "results": [{ "year": 2025, "crop": "soybeans", "yieldPerAcre": 70 }] }
```

- `crop` is a catalog crop id. Unknown crops and two entries for one year give 422.
- `yieldPerAcre` is optional.
- A declared crop replaces the satellite label for that year (`historySource.declaredSeasons`
  counts them). The season after the last declared year becomes the plan's first season.
- Declared yields set the field's yield level relative to the county, from the latest 10 years.
  With fewer than 4 years of a crop, the missing years count at the county level. The result is in
  `plan.ownYields[]`.

## The farmer's soil test

`GET`, `PUT` and `DELETE /api/v1/fields/{field_id}/soil-survey`. `GET` returns `null` when there is
none.

- pH and organic matter replace the soil-map values. `soilInputs[]` in the advice shows each value,
  its source and where it is used.
- Phosphorus and potassium (ppm) change the fertilizer cost (`usedIn: ["fertilizer_cost"]`).
  - Each value is put in an Iowa State category (PM 1688, 2023): `very_low` to `very_high`.
    `phosphorusTest` (`bray_p1` by default, `mehlich3_colorimetric`, `mehlich3_icp`, `olsen`) and
    `potassiumSample` (`dried` by default, `moist`) pick the scale.
  - The recommended rate for the category, less the maintenance rate of the Optimum category, times
    the fertilizer price (Iowa State, 2026) is added to the crop's cost. A low test costs more; a
    high test saves the maintenance application.
  - `plan.soilTest[]` reports the category, the chance of a yield response, the rates and the cost
    change per crop. Corn and soybeans only.
  - `calibration` is `iowa`, or `iowa_applied_elsewhere` for fields in other states. The yield
    itself is not changed.

## The soil productivity index

When the farmer gave no yields, the soil places the field within its county. `plan.soilYield[]`
reports, for corn and soybeans:

- `index`: the NRCS productivity index used (NCCPI 3.0 corn or soybean submodel, 0 to 1), with
  `fieldIndex` and `countyIndex` (the mean over the sampled cropland fields of the county).
- `ratio`: the field's yield level against the county yield, within 0.85 to 1.15. The expected
  yield is the county level times this ratio.
- `verified: false`: the slope is our own estimate between counties, applied within a county.

The farmer's own yields replace it. Depth to a restrictive layer, water table, flooding and
ponding were tested too and did not add enough to use (see `rule_engine/planner/soil_level.py`).

## The calculator: price, cost and rent

`GET`, `PUT` and `DELETE /api/v1/fields/{field_id}/economics`.

```json
{
  "landRentUsdPerAcre": 290,
  "crops": [{ "crop": "corn", "priceUsd": 4.4, "costUsdPerAcre": 520 }]
}
```

- `GET` returns `inputs` (the farmer's values, or `null`) and `defaults` (the USDA averages to
  prefill the form):
  - `defaults.crops[]`: the planning price, and the cost from the USDA ERS budget of the field's
    farm resource region (`costLevel`, `costYear`, `costItems`).
  - `defaults.landRent`: the NASS cash rent of the county, or of the state when the county has
    none (`level`), with `irrigatedLandRent` beside it.
- Everything is optional. What the farmer leaves out keeps the average.
- `priceUsd` is per bushel (hay: per ton). It replaces the planning price; past years still move
  around it.
- `costUsdPerAcre` excludes land. It stands for conventional tillage after a different crop; the
  differences for other tillage and for corn after corn still come from the tables. A soil-test
  cost change is not added on top of a farmer's own cost.
- `landRentUsdPerAcre` is charged in every season. Without it no rent is charged
  (`landRentSource: not_charged`) and the result is a return to land.

The three inputs live on `user_fields` (migrations `0008_farmer_inputs`, `0009_field_economics`).

## Which fields are covered

The advice response carries `summarySource`: `{kind, distanceKm}`.

- `own`: the field is one of the 362,105 sampled fields and has its own season summaries.
- `weather_cell`: the field reads the sampled field of its weather cell (about 4 km) and county.
  Weather, drought and county yield are the same; crop history and soil are the field's own.
- `nearby_cell`: no sampled field in the cell, so the nearest sampled cell of the same county is
  used. `distanceKm` is the distance between cell centres, at most 40.
- `none`: no sampled field of the county within 40 km. The plan then runs on price years only.

Files in the data root: `summary_index.parquet` (CSBID, county_fips, ix, iy), `season_summary/`,
`soil_points.csv` (CSBID, mukey), `soil_units.csv` (map-unit values), `soil_extra.csv`,
`cdl_history_all.parquet`, `climate_record/`. A small sample may have `fields.jsonl` instead of
the two soil tables.
