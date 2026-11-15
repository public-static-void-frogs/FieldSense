"""The rotation plan: which crops pay over the next seasons, from the planner in `rule_engine`.

The rule engine scores risk in points. The planner (`rule_engine/planner`) turns the same rules,
past weather years, prices and cost budgets into USD per acre and solves for the crop sequence
with the highest expected return over a set number of seasons. This module only runs it for one
field and shapes the result: codes and numbers, no wording.

    return of a season = revenue - production cost (land excluded) - risk penalty + soil value

`netUsdPerAcre` is revenue less cost. `objectiveUsdPerAcre` also carries the risk penalty and
the soil value: it is what the plan maximises, not money in hand.

The cost is the full economic cost (USDA ERS: operating costs plus labour, machinery ownership
and overhead). `lossProbability` is measured against it; `operatingLossProbability` against the
operating costs alone (`operatingCostUsdPerAcre`), the money spent on the crop in the season.
"""

from dataclasses import replace

NOT_MODELLED = ("no_cost_budget", "no_price", "no_yield", "not_marketed")
TOP = 3
RYE_COVER = "cereal_rye"  # the off-season option the planner's rye cover crop is
MIN_SEASONS, MAX_SEASONS, DEFAULT_SEASONS = 1, 5, 3
EXACT, LEARNED = "dynamic_programming_fixed_sequence", "learned_policy"  # plan.method
EXACT_PLANNER, LEARNED_PLANNER = "exact", "learned"  # the request's choice
PLANNERS = (EXACT_PLANNER, LEARNED_PLANNER)


def _fall_sown() -> set[str]:
    from rule_engine.offseason import OPTIONS

    return {o.crop_id for o in OPTIONS if o.kind == "winter_cash_crop" and o.crop_id}


def _step(model, state, action, season: int, fall_sown: set[str]) -> dict:
    found = model.summary(state, action)
    previous = state.history[-1] if state.history else None
    if previous == action.crop and model._lifecycle[action.crop] == "perennial":
        before = "keep_stand"
    elif action.crop in fall_sown:
        before = "sow_winter_crop"
    elif action.cover != "none":
        before = "sow_cover_crop"
    else:
        before = "none"
    overhead = model.overhead(state.history, action)
    return {
        "season": season,
        "crop": action.crop,
        "tillage": action.tillage,
        "coverCrop": action.cover,
        "autumnBefore": before,
        "objectiveUsdPerAcre": found["expectedUsdPerAcre"],
        "netUsdPerAcre": round(found["revenueUsdPerAcre"] - found["costUsdPerAcre"], 2),
        "worstYearUsdPerAcre": found["worstYearCashUsdPerAcre"],
        "bestYearUsdPerAcre": found["bestYearCashUsdPerAcre"],
        "worstYear": found["worstCashYear"],
        "revenueUsdPerAcre": found["revenueUsdPerAcre"],
        "costUsdPerAcre": found["costUsdPerAcre"],
        "operatingCostUsdPerAcre": None
        if overhead is None
        else round(found["costUsdPerAcre"] - overhead, 2),
        "riskPenaltyUsdPerAcre": found["riskPenaltyUsdPerAcre"],
        "soilValueUsdPerAcre": found["soilValueUsdPerAcre"],
        "yieldPerAcre": found["yieldPerAcre"],
        "yieldUnit": found["yieldUnit"],
        "rules": sorted({*found["pointRules"], *found["yieldRules"]}),
    }


def _autumn(first: dict, option: dict, off_season: dict | None) -> dict:
    """What the plan asks for between this harvest and winter, with how often it establishes."""
    levels = {}
    for found in (off_season or {}).get("options", []):
        levels[found["id"]] = levels[found.get("cropId")] = found["level"]
    wanted = {"sow_cover_crop": RYE_COVER, "sow_winter_crop": first["crop"]}.get(
        first["autumnBefore"]
    )
    gain = option["coverGain"]
    return {
        "action": first["autumnBefore"],
        "species": wanted,
        "establishment": levels.get(wanted) if wanted else None,
        "ryeCoverGainUsdPerAcre": None if gain is None else round(gain, 2),
        "ryeCoverEstablishment": levels.get(RYE_COVER),
    }


def _money(spread: dict) -> dict:
    operating = spread["operatingLossProbability"]
    return {
        "lossProbability": round(spread["lossProbability"], 3),
        "operatingLossProbability": None if operating is None else round(operating, 3),
        "meanUsdPerAcre": round(spread["mean"], 2),
        "p10UsdPerAcre": round(spread["p10"], 2),
        "p50UsdPerAcre": round(spread["p50"], 2),
        "p90UsdPerAcre": round(spread["p90"], 2),
    }


def _extreme(rows: list[dict], pick) -> dict:
    found = pick(rows, key=lambda r: r["cash"])
    return {"year": found["year"], "netUsdPerAcre": round(found["cash"], 2)}


def _simulation(replayed: dict, top: dict | None) -> dict:
    """The plan replayed through the past years: cash per acre, and how often each result came.

    `top` is the replay of the first-ranked plan; the same year hits both crops, so the share of
    years in which this crop earns at least as much is a like-for-like comparison.
    """
    first, runs = replayed["first"], replayed["runs"]
    years = first["years"]
    beats = None
    if top is not None:
        pairs = zip(years, top["first"]["years"], strict=True)
        beats = round(sum(a["odds"] for a, b in pairs if a["cash"] >= b["cash"]), 3)
    return {
        "firstSeason": {
            **_money(first),
            "years": len(years),
            "yieldPerAcre": {
                "unit": replayed["unit"],
                **{
                    f"{key}PerAcre": round(first["yield"][key], 2)
                    for key in ("mean", "p10", "p50", "p90")
                },
            },
            "planningPriceUsd": round(replayed["price"], 2),
            "observedYieldYears": sum(y["yieldMode"] == "observed" for y in years),
            "worst": _extreme(years, min),
            "best": _extreme(years, max),
            "beatsTopProbability": beats,
            "outcomes": [
                {
                    "year": y["year"],
                    "probability": round(y["odds"], 4),
                    "netUsdPerAcre": round(y["cash"], 2),
                    "yieldPerAcre": round(y["yield"], 2),
                    "priceUsd": round(y["price"], 2),
                    "yieldMode": y["yieldMode"],
                }
                for y in years
            ],
        },
        "plan": {
            **_money(runs),
            "runs": len(runs["starts"]),
            "worst": _extreme(runs["starts"], min),
            "best": _extreme(runs["starts"], max),
        }
        if runs
        else None,
    }


def _year_odds(model) -> dict:
    odds = model.distribution(model.open_loop_state)
    found = {"method": "equal", "effectiveYears": round(1.0 / sum(p * p for p in odds), 1)}
    if model.chain:
        chain = model.chain
        found |= {
            "method": "analog_years",
            "startsAfter": chain.labels[chain.latest],
            "signals": list(chain.signals),
        }
    return found


def _economics(model) -> dict:
    """The price, cost and rent the plan used, and whose they are."""
    crops = []
    for crop in model.crops:
        cost = model.costs.crop_cost(crop, None, model.tillage[0])
        shift = model.cost_shift.get(crop, 0.0)
        crops.append(
            {
                "crop": crop,
                "priceUsd": model.sampler.basis[crop].price,
                "priceSource": "farmer"
                if model.sampler.basis[crop].price_level == "farmer"
                else "planning",
                "costUsdPerAcre": round(cost.usd_per_acre + shift, 2),
                "costSource": "farmer" if "farmer" in cost.sources else "tables",
                "soilTestCostChangeUsdPerAcre": shift,
            }
        )
    return {
        "landRentUsdPerAcre": model.land_rent,
        "landRentSource": "farmer" if model.land_rent else "not_charged",
        "crops": crops,
    }


def rotation_plan(
    advisor,
    record: dict,
    candidates: list[str],
    priorities: list[str],
    seasons: int,
    summary_root,
    reference_aws_mm: float | None,
    off_season: dict | None,
    as_of_year: int,
    policy=None,
) -> dict:
    """`policy` (a rule_engine LearnedPolicy) plans the seasons after the first instead of the
    exact optimum; each crop then also reports how far its plan is below that optimum."""
    from rule_engine.planner import RotationModel, build_context, with_climate
    from rule_engine.planner.solve import crop_options, replay

    context = build_context(record, advisor, [summary_root] if summary_root else [])
    context = replace(context, reference_aws_mm=reference_aws_mm)
    years_source = "field_seasons" if context.seasons else "price_years"
    context, long_record = with_climate(context, advisor)
    if long_record:
        years_source = "climate_record"
    try:
        model = RotationModel(
            context, advisor, crops=tuple(candidates), priorities=tuple(priorities), horizon=seasons
        )
    except ValueError:
        return {"status": "no_modellable_crop", "seasons": seasons, "crops": [], "steps": []}
    first_season = (context.last_history_year or as_of_year - 1) + 1
    fall_sown = _fall_sown()
    crops = []
    learned = policy is not None
    optimum = {o["steps"][0][1].crop: o["value"] for o in crop_options(model)} if learned else {}
    for option in crop_options(model, policy.act_for(model) if learned else None):
        steps = [
            _step(model, state, action, first_season + i, fall_sown)
            for i, (state, action) in enumerate(option["steps"])
        ]
        autumn = _autumn(steps[0], option, off_season)
        crops.append(
            {
                "crop": steps[0]["crop"],
                # a crop that rarely establishes in the autumn left is not a first choice
                "demoted": "autumn_establishment_unlikely"
                if autumn["establishment"] == "unlikely"
                else None,
                "planObjectiveUsdPerAcre": round(option["value"], 2),
                # a learned plan against the exact optimum that starts with the same crop
                "belowOptimumUsdPerAcre": round(optimum[steps[0]["crop"]] - option["value"], 2)
                if learned
                else None,
                "planNetUsdPerAcre": round(sum(s["netUsdPerAcre"] for s in steps), 2),
                "autumn": autumn,
                "steps": steps,
                "replay": {
                    **replay(model, option["steps"]),
                    "unit": steps[0]["yieldUnit"],
                    "price": model.sampler.basis[steps[0]["crop"]].price,
                },
            }
        )
    crops.sort(key=lambda c: c["demoted"] is not None)  # stable: the plan order is kept
    for rank, crop in enumerate(crops, start=1):
        crop["rank"] = rank
        crop["tier"] = "top" if rank <= TOP and not crop["demoted"] else "alternative"
    for crop in crops:
        top = crops[0]["replay"] if crop is not crops[0] else None
        crop["simulation"] = _simulation(crop["replay"], top)
    for crop in crops:
        del crop["replay"]
    weights = model.weights
    return {
        "status": "ok",
        "objective": "expected_return_less_risk_plus_soil",
        "method": LEARNED if learned else EXACT,
        "seasons": seasons,
        "firstSeason": first_season,
        "weights": {
            "riskUsdPerPoint": weights.risk_usd_per_point,
            "soilUsdPerTonneCarbon": weights.soil_usd_per_t_c,
        },
        "years": {
            "source": years_source,
            "count": len(model.years),
            "first": model.years[0].year,
            "last": model.years[-1].year,
        },
        "costRegion": model.costs.region,
        "economics": _economics(model),
        "soilTest": record.get("soilTestEffects") or [],
        "yearOdds": _year_odds(model),
        "ownYields": [
            {
                "crop": crop_id,
                "yieldUnit": basis.unit + "/acre",
                "ratio": round(basis.own_ratio, 3),
                "expectedYieldPerAcre": round(basis.expected_yield, 2),
                "points": [
                    {
                        "year": year,
                        "yieldPerAcre": round(own, 2),
                        "referenceYieldPerAcre": round(reference, 2),
                    }
                    for year, own, reference in basis.own_points
                ],
            }
            for crop_id, basis in model.sampler.basis.items()
            if basis.own_points
        ],
        "soilYield": [
            {
                "crop": crop_id,
                "index": basis.soil_level.index,
                "fieldIndex": basis.soil_level.field,
                "countyIndex": basis.soil_level.county,
                "countyFields": basis.soil_level.county_fields,
                "ratio": round(basis.soil_level.ratio, 3),
                "expectedYieldPerAcre": round(basis.expected_yield, 2),
                "verified": False,
            }
            for crop_id, basis in model.sampler.basis.items()
            if basis.soil_level is not None
        ],
        "crops": crops,
        "notModelled": [
            {"crop": g["crop"], "code": g["code"]} for g in model.gaps if g["code"] in NOT_MODELLED
        ],
        "gaps": [g for g in model.gaps if g["code"] not in NOT_MODELLED],
    }
