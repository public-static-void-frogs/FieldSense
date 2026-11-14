# Season timing (M3 outputs)

The rotation advice (`GET /api/v1/fields/{id}/rotation-advice`) carries an optional
`seasonTiming` block with local sowing windows and heat and frost risk for corn and soybeans.
The numbers come from the M3 batch job (`m3_window_forecaster.py`, run offline by its owners).
The backend only reads the tables it wrote.

- `app/services/m3_lookup.py` is the M3 team's reader. The app builds one `M3Advice` at startup
  and the `m3-insights` endpoint and the rotation advice share it.
- `app/services/season_timing.py` picks the values the screen shows and renames them to the API
  contract (`app/schemas/rotation.py:SeasonTiming`).
- `M3_OUT` is the M3 output folder. The default is `data/m3_out`, checked into the repo. When the
  folder or `field_index.parquet` is absent, `seasonTiming` is `null` and nothing else changes.

## What the block means

- It is climatology over past years for the field's weather cell (about 50 km), not a forecast
  for one season. Every date is a range as month-day strings: `early`, `typical` and `late` are
  the dates 10%, 50% and 90% of years reach.
- `matchLevel` is `field` when a CSB field centroid is within 1 km of the point, else `cell`.
  The windows and risks are per cell either way.
- `heatAtFlowering.probability` is the share of years with 2 or more days at 35 °C or hotter in
  the flowering window. `vulnerable` is M3's flag for a share of 0.40 or more.
- `sowingDelayMarginDays` is how long sowing can be postponed (steps of 5 days, up to 30)
  before frost risk passes 10% or heat risk rises by more than 5 points. `null` means no safe
  delay, not "unknown".
- `outlook2040` gives the 2040 heat share under SSP2-4.5 and SSP5-8.5 as the median, minimum and
  maximum over climate models. That is model spread, not a probability range.
- `dateErrorDays` is M3's mean absolute error against held-out NASS crop progress dates.

One value reaches the rule engine: the typical local sowing date (`stages.sow.typical`) of
each crop, through `season_timing.py:local_calendar`. It moves that crop's `planted` and
`emerged` stages from the state median to the local day, which moves the windows of the hazard
rules tied to those stages (`calendar.localShiftDays` in the advice shows the shift). In Iowa
the local date runs from about 30 April in the south to 9 May in the north for corn.

Flowering and maturity dates are not passed on. M3 computes them with one heat requirement for
the whole state, while farmers further north plant earlier-maturing hybrids, so its north-south
difference (maturity 4 September to 4 October for corn) is larger than in the field. The rest
of the block is for display and does not change scores or ranks.

## Coverage of the supplied archive (`m3_out.zip`)

- Iowa only: 484,923 CSB fields in 79 counties, 62 weather cells, crops corn and soybeans.
- Weather history 1981-2025 (45 years); risks are counted over 30 years.
- Mean error against NASS: sowing 8 days (corn) and 10 days (soybeans), flowering 3-4 days,
  maturity 6-7 days.
- The three Fallow-Zero tables (`fallow_zero_units`, `fallow_zero_m9_units`,
  `fallow_zero_field_metrics`) arrived separately and go in `m3_out/fallow_zero/`. They cover
  all 62 cells and every indexed field, over 42 years of weather. Without them
  `seasonTiming.waterAtSowing` is `{}`.

## Water at sowing (`seasonTiming.waterAtSowing`)

Keyed by the crop just harvested (`corn`, `soybeans`); the next crop is fixed by M3 (soybeans
after corn, corn after soybeans). For bare fallow and for a winter rye cover crop it gives
`shortfall`, the share of past years in which plant-available soil water at sowing was below
`thresholdMm`, with an 80% range and the typical water in mm. `coverOk` is M3's rule: shortfall
with the cover crop at or below 0.30. `safeAutumnRainMm` is the autumn rain from which the
cover crop is water-safe (0: any year; null: no such level). The recommend screen shows this
in the after-harvest card. It does not change scores or ranks.
