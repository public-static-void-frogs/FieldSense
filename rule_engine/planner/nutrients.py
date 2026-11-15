"""Phosphorus and potassium from the farmer's soil test: what they change in the fertilizer bill.

The soil-test value is put in a category (very low to very high) and the category gives the
recommended rate of P2O5 and K2O per acre for corn and for soybeans, from Iowa State University
Extension PM 1688 (revised February 2023; data/soil_test_categories.csv, soil_test_rates.csv).
The Optimum rate is the removal of a 210 bu/acre corn or 70 bu/acre soybean crop. The cost
budgets assume ordinary fertilizer use, taken here as that Optimum rate, so the change in cost is

    (rate of the category - rate at Optimum) x price per pound

with the prices of data/fertilizer_prices.csv. Low tests cost more (build-up rates); high tests
need no P or K that season. PM 1688 is calibrated on Iowa soils: outside Iowa the result is
flagged, not withheld. Other crops have no rate table here and are left unchanged.

The yield is not changed: the rates are what keeps the yield at the expected level. PM 1688
gives the chance that a crop responds to the nutrient per category, which is reported.
"""

from functools import lru_cache

from rule_engine.planner.tables import _flag, _rows

NUTRIENTS = ("phosphorus", "potassium")
DEFAULT_TEST = {"phosphorus": "bray_p1", "potassium": "dried"}
CALIBRATION_REGION = "IA"


@lru_cache(maxsize=1)
def _tables():
    categories: dict[tuple[str, str], list[tuple[float, str, float]]] = {}
    for r in _rows("soil_test_categories.csv"):
        categories.setdefault((r["nutrient"], r["test"]), []).append(
            (float(r["ppm_from"]), r["category"], float(r["response_probability"]))
        )
    for bounds in categories.values():
        bounds.sort()
    rates = {
        (r["crop"], r["nutrient"], r["category"]): float(r["lb_per_acre"])
        for r in _rows("soil_test_rates.csv")
    }
    prices = {r["nutrient"]: r for r in _rows("fertilizer_prices.csv")}
    verified = all(
        _flag(r["verified"])
        for name in ("soil_test_categories.csv", "soil_test_rates.csv", "fertilizer_prices.csv")
        for r in _rows(name)
    )
    return categories, rates, prices, verified


def tests(nutrient: str) -> list[str]:
    return sorted(test for (name, test) in _tables()[0] if name == nutrient)


def category(nutrient: str, ppm: float, test: str | None = None) -> tuple[str, float] | None:
    """(category, chance of a yield response) of a soil-test value, None for an unknown test."""
    bounds = _tables()[0].get((nutrient, test or DEFAULT_TEST[nutrient]))
    if not bounds:
        return None
    found = bounds[0]
    for bound in bounds:
        if ppm >= bound[0]:
            found = bound
    return found[1], found[2]


def soil_test_effect(soil_test: dict, region: str | None) -> list[dict]:
    """One entry per nutrient measured: category, rates and cost change per crop.

    `soil_test`: {"phosphorus": {"ppm": 12, "test": "bray_p1"}, "potassium": {"ppm": 150}}
    """
    _, rates, prices, verified = _tables()
    out = []
    for nutrient in NUTRIENTS:
        entry = soil_test.get(nutrient)
        if not entry or entry.get("ppm") is None:
            continue
        test = entry.get("test") or DEFAULT_TEST[nutrient]
        found = category(nutrient, float(entry["ppm"]), test)
        if found is None:
            continue
        name, response = found
        price = float(prices[nutrient]["usd_per_lb"])
        crops = []
        for (crop, rate_nutrient, rate_category), rate in sorted(rates.items()):
            if rate_nutrient != nutrient or rate_category != name:
                continue
            maintenance = rates[(crop, nutrient, "optimum")]
            crops.append(
                {
                    "crop": crop,
                    "rateLbPerAcre": rate,
                    "maintenanceRateLbPerAcre": maintenance,
                    "costChangeUsdPerAcre": round((rate - maintenance) * price, 2),
                }
            )
        out.append(
            {
                "nutrient": nutrient,
                "ppm": float(entry["ppm"]),
                "test": test,
                "category": name,
                "yieldResponseProbability": response,
                "fertilizerUnit": prices[nutrient]["unit"],
                "fertilizerUsdPerLb": price,
                "calibration": "iowa" if region == CALIBRATION_REGION else "iowa_applied_elsewhere",
                "verified": verified,
                "crops": crops,
            }
        )
    return out


def cost_changes(effects: list[dict]) -> dict[str, float]:
    """{crop: USD per acre} summed over the nutrients."""
    total: dict[str, float] = {}
    for effect in effects:
        for crop in effect["crops"]:
            total[crop["crop"]] = round(
                total.get(crop["crop"], 0.0) + crop["costChangeUsdPerAcre"], 2
            )
    return total
