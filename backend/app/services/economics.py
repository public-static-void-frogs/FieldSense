"""The price, cost and rent calculator: USDA averages as defaults, the farmer's own values on top.

Defaults for a field:
    price       the rule engine's planning price of the crop (crop insurance projected price
                where there is one)
    cost        the planner's cost table: USDA ERS Commodity Costs and Returns for the county's
                farm resource region, land excluded, with the ERS items of the latest year
    land rent   USDA NASS Cash Rents Survey: the county, else the state; else the ERS regional
                opportunity cost of land for corn

Land rent is charged only when the farmer enters one: an owner pays none, and the plan's cash
result is otherwise a return to land.
"""

import csv
from functools import lru_cache

COST_ITEMS = (
    "seed",
    "fertilizer",
    "chemicals",
    "other_operating",
    "labor",
    "machinery",
    "overhead",
)


@lru_cache(maxsize=1)
def _tables():
    from rule_engine.planner.tables import DATA

    with (DATA / "cash_rent.csv").open(newline="") as handle:
        rent = {(r["geography"], r["land"]): r for r in csv.DictReader(handle)}
    items: dict[tuple[str, str], dict] = {}
    with (DATA / "costs_regional_history.csv").open(newline="") as handle:
        for r in csv.DictReader(handle):
            key = (r["crop"], r["region"])
            if key not in items or int(r["year"]) > int(items[key]["year"]):
                items[key] = r
    return rent, items


def _rent(county_fips: str | None, state: str | None, region: str | None, land: str):
    rent, items = _tables()
    for level, geography in (("county", county_fips), ("state", state)):
        row = rent.get((geography or "", land))
        if row:
            return {
                "usdPerAcre": float(row["usd_per_acre"]),
                "year": int(row["year"]),
                "level": level,
                "source": "nass_cash_rents",
            }
    row = items.get(("corn", region or "")) if land == "non_irrigated" else None
    if row:
        return {
            "usdPerAcre": float(row["land"]),
            "year": int(row["year"]),
            "level": "ers_region",
            "source": "ers_land_opportunity_cost",
        }
    return None


def defaults(advisor, record: dict, candidates: list[str]) -> dict:
    from rule_engine.planner.tables import NATIONAL, TILLAGE, CostTable, ers_region, state_fips

    county = record.get("countyFips")
    region = ers_region(county)
    state, _ = advisor.region_for(record)
    table = CostTable(region=region, state=state_fips(county), county=county)
    _, items = _tables()
    crops = []
    for crop in candidates:
        quote = advisor.reference.price(crop, state)
        cost = table.crop_cost(crop, None, TILLAGE[0]) if crop in table.crops else None
        if quote is None or cost is None:
            continue
        level, row = "state_budget", None
        if crop in table.regional:
            row = items.get((crop, region or ""))
            level = "ers_region" if row else "national"
            row = row or items.get((crop, NATIONAL))
        crops.append(
            {
                "crop": crop,
                "priceUsd": quote.price_usd,
                "priceUnit": quote.unit,
                "priceLevel": quote.level,
                "costUsdPerAcre": round(cost.usd_per_acre, 2),
                "costLevel": level,
                "costYear": int(row["year"]) if row else None,
                "costItems": {name: float(row[name]) for name in COST_ITEMS} if row else None,
            }
        )
    return {
        "costRegion": region,
        "landRent": _rent(county, state, region, "non_irrigated"),
        "irrigatedLandRent": _rent(county, state, region, "irrigated"),
        "crops": crops,
    }


def engine_economics(stored: dict | None, cost_changes: dict[str, float]) -> dict | None:
    """The stored calculator values in the shape `field["economics"]` of the planner."""
    stored = stored or {}
    crops = stored.get("crops") or []
    found = {
        "prices": {c["crop"]: c["priceUsd"] for c in crops if c.get("priceUsd")},
        "costs": {
            c["crop"]: c["costUsdPerAcre"] for c in crops if c.get("costUsdPerAcre") is not None
        },
        "landRentUsdPerAcre": stored.get("landRentUsdPerAcre"),
        "costChanges": cost_changes,
    }
    return found if any(found.values()) else None
