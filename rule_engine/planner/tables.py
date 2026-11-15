"""The planner's own reference tables: production costs, weather yield response, soil carbon.

Every row carries its source and a `verified` flag. Unverified rows are usable but are reported
under data gaps by the environment, the same way the rule engine treats unverified traits.
"""

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data"
TILLAGE = ("conventional", "strip_till", "no_till")
COVER = ("none", "rye")
# Crops the planner can price: the ones with a cost budget (costs.csv, costs_regional.csv).
# A trained policy reads crops by their position here: add a crop at the end, and retrain.
CROPS = (
    "corn",
    "soybeans",
    "sorghum",
    "oats",
    "winter_wheat",
    "spring_wheat",
    "barley",
    "alfalfa",
    "durum_wheat",
    "cotton",
    "rice",
    "peanuts",
    "sugarbeets",
    "potatoes",
    "sugarcane",
    "dry_peas",
    "lentils",
    "chickpeas",
    "millet",
    "flax",
    "other_hay",
    "canola",
    "rye",
    "dry_beans",
    "sunflower",
)
NATIONAL = "U.S. total"


def _rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(newline="") as handle:
        return list(csv.DictReader(handle))


def _flag(value: str) -> bool:
    return value.strip().lower() == "true"


@dataclass(frozen=True)
class Cost:
    usd_per_acre: float
    verified: bool
    sources: tuple[str, ...]


@lru_cache(maxsize=1)
def _ers_regions() -> dict[str, str]:
    return {r["county_fips"]: r["region"] for r in _rows("ers_regions.csv")}


# ERS reports rice and peanuts by their own production regions, not the farm resource regions
# (crop_region). Rice by county from rice_regions.csv, else by state (two-digit FIPS):
# (region, whether ERS's own description places the state there).
RICE_STATES = {
    "06": ("California", True),
    "48": ("Gulf Coast", True),
    "28": ("Mississippi River Delta", True),
    "05": ("Arkansas Non-Delta", False),
    "29": ("Arkansas Non-Delta", False),
    "22": ("Mississippi River Delta", False),
}
PEANUT_SEABOARD = {  # the Southern Seaboard split of the ERS peanut budgets
    "01": "Southern Seaboard (AL, GA)",
    "13": "Southern Seaboard (AL, GA)",
    "51": "Southern Seaboard (VA, NC, SC)",
    "37": "Southern Seaboard (VA, NC, SC)",
    "45": "Southern Seaboard (VA, NC, SC)",
}
LAPSED_YEARS = 5  # a region ERS stopped reporting at most this many years before the latest


@lru_cache(maxsize=1)
def _rice_regions() -> dict[str, tuple[str, bool]]:
    return {
        r["county_fips"]: (r["region"], _flag(r["verified"])) for r in _rows("rice_regions.csv")
    }


def crop_region(
    crop: str, county_fips: str | None, region: str | None, state: str | None
) -> tuple[str | None, bool]:
    """(ERS cost region, whether ERS's own description places the field there) for a crop.

    Rice: the county's row of rice_regions.csv (built by the Field-Shift planner's
    scripts/build_rice_regions.py from ERS EIB-202 and the 2022 Census), else its state's region
    (RICE_STATES), else the farm resource region. Peanuts: the Southern Seaboard splits into AL-GA
    and VA-NC-SC; a Southern Seaboard county of another state (FL, MS) takes AL-GA, unverified.
    Other crops: the farm resource region. `state` is the two-digit FIPS."""
    if crop == "rice":
        county = _rice_regions().get(str(county_fips or "").zfill(5))
        return county or RICE_STATES.get(state or "", (region, True))
    if crop == "peanuts" and region == "Southern Seaboard":
        if state in PEANUT_SEABOARD:
            return PEANUT_SEABOARD[state], True
        return PEANUT_SEABOARD["13"], False
    return region, True


def _lapsed_regions(region: str | None, state: str | None, county: str | None) -> dict[str, Cost]:
    """{crop: cost} for crops whose ERS region of the field dropped out of the latest year
    (peanuts and oats in the Prairie Gateway after 2022): the U.S. total of the latest year times
    the region's mean ratio to the U.S. total over its last three years. Derived, so unverified."""
    series: dict[tuple[str, str], dict[int, float]] = {}
    for r in _rows("costs_regional_history.csv"):
        if r["usd_per_acre"]:
            series.setdefault((r["crop"], r["region"]), {})[int(r["year"])] = float(
                r["usd_per_acre"]
            )
    out: dict[str, Cost] = {}
    for (crop, name), own in series.items():
        national = series.get((crop, NATIONAL), {})
        if name != crop_region(crop, county, region, state)[0] or not national:
            continue
        latest = max(national)
        common = sorted(set(own) & set(national))[-3:]
        if max(own) >= latest or max(own) < latest - LAPSED_YEARS or not common:
            continue
        ratio = sum(own[y] for y in common) / sum(national[y] for y in common)
        out[crop] = Cost(
            national[latest] * ratio,
            False,
            (
                f"USDA ERS Commodity Costs and Returns, {crop}, U.S. total {latest} "
                f"({national[latest]:.2f}) times {name}'s ratio to it in "
                f"{common[0]}-{common[-1]} ({ratio:.3f}); ERS last reported {name} in "
                f"{max(own)}",
            ),
        )
    return out


OPERATING_ITEMS = ("seed", "fertilizer", "chemicals", "other_operating")


@lru_cache(maxsize=1)
def _ers_operating() -> dict[tuple[str, str], float]:
    """{(crop, ERS region): operating costs as a share of the cost less land}, from the latest
    year ERS reports the region (costs_regional_history.csv).

    ERS operating costs: seed, fertilizer, chemicals, custom services, fuel, repairs, purchased
    irrigation water and interest on operating capital. The rest (hired and unpaid labour,
    capital recovery of machinery, taxes, insurance, general overhead) is not paid per acre
    planted in the season."""
    latest: dict[tuple[str, str], dict[str, str]] = {}
    for r in _rows("costs_regional_history.csv"):
        key = (r["crop"], r["region"])
        if r["usd_per_acre"] and (key not in latest or int(r["year"]) > int(latest[key]["year"])):
            latest[key] = r
    return {
        key: sum(float(r[item]) for item in OPERATING_ITEMS) / float(r["usd_per_acre"])
        for key, r in latest.items()
    }


@lru_cache(maxsize=1)
def _budget_operating() -> dict[tuple[str, str], float]:
    """{(crop or crop:situation, scope): operating share} of the budgets outside the ERS tables
    (costs_operating.csv). `scope`: "reference" for a costs.csv row, else the states of a
    costs_state.csv row. Only the budgets whose source gives the split have a row."""
    if not (DATA / "costs_operating.csv").exists():
        return {}
    return {
        (r["crop"], r["scope"]): float(r["operating_usd_per_acre"]) / float(r["total_usd_per_acre"])
        for r in _rows("costs_operating.csv")
        if float(r["total_usd_per_acre"]) > 0
    }


def state_fips(county_fips: str | None) -> str | None:
    text = str(county_fips or "").strip()
    return text.zfill(5)[:2] if text else None


def ers_region(county_fips: str | None) -> str | None:
    """USDA ERS farm resource region of a county (five-digit FIPS), None when unknown."""
    return _ers_regions().get(str(county_fips or "").zfill(5))


@lru_cache(maxsize=1)
def state_crop_shares() -> dict[tuple[str, str], float]:
    """{(state, crop): share of the state's CSB acres}, from the rule engine's state_crops.csv
    (CDL labels: a satellite estimate)."""
    path = DATA.parents[1] / "data" / "state_crops.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        return {(r["region"], r["crop"]): float(r["acre_share"]) for r in csv.DictReader(handle)}


@lru_cache(maxsize=1)
def processor_counties() -> dict[str, frozenset[str]]:
    """{crop: counties (five-digit FIPS) where it is grown}, for the crops that need a processor
    nearby (processor_counties.csv, built by scripts/build_processor_counties.py)."""
    found: dict[str, set[str]] = {}
    path = DATA / "processor_counties.csv"
    if path.exists():
        for r in _rows(path.name):
            found.setdefault(r["crop"], set()).add(r["county_fips"].zfill(5))
    return {crop: frozenset(counties) for crop, counties in found.items()}


class CostTable:
    """Cost of production per acre, land excluded, so the result is a return to land.

    With a `region` (ERS farm resource region) the level of a crop's cost comes from the ERS
    regional table (costs_regional.csv); costs.csv then only supplies the differences between
    tillage systems and between corn after corn and corn after another crop. A crop that ERS
    does not report for the region uses the national ERS row, flagged unverified. Crops without
    any ERS table (alfalfa, sugarbeets, potatoes, pulses, ...) use costs.csv, except in the
    states where costs_state.csv has a budget of their own (sugarbeets in the Red River Valley,
    potatoes in Washington and Oregon).
    """

    def __init__(
        self,
        rows=None,
        cover_rows=None,
        region: str | None = None,
        regional_rows=None,
        state: str | None = None,
        state_rows=None,
        county: str | None = None,
    ):
        """`state`: two-digit FIPS, for the crops ERS reports by their own regions and the
        state budgets of costs_state.csv. `county`: five-digit FIPS, for the rice regions."""
        self.region = region
        self.regional: dict[str, Cost] = {}
        if region is not None or state is not None:
            found = regional_rows if regional_rows is not None else _rows("costs_regional.csv")
            for r in found:
                cost = Cost(float(r["usd_per_acre"]), _flag(r["verified"]), (r["source"],))
                own, placed = crop_region(r["crop"], county, region, state)
                if r["region"] == own:
                    self.regional[r["crop"]] = Cost(
                        cost.usd_per_acre, cost.verified and placed, cost.sources
                    )
                elif r["region"] == NATIONAL and r["crop"] not in self.regional:
                    self.regional[r["crop"]] = Cost(cost.usd_per_acre, False, cost.sources)
            for crop, cost in _lapsed_regions(region, state, county).items():
                if crop in self.regional and not self.regional[crop].verified:
                    self.regional[crop] = cost
        # operating costs as a share of a crop's level; a crop without a known split has none
        ers, budgets = _ers_operating(), _budget_operating()
        self.operating: dict[str, float] = {}
        for crop in self.regional:
            own = crop_region(crop, county, region, state)[0]
            share = ers.get((crop, own), ers.get((crop, NATIONAL)))
            if share is not None:
                self.operating[crop] = share
        if state is not None:
            for r in state_rows if state_rows is not None else _rows("costs_state.csv"):
                if state in r["states"].split():
                    self.regional[r["crop"]] = Cost(
                        float(r["usd_per_acre"]), _flag(r["verified"]), (r["source"],)
                    )
                    self.operating.pop(r["crop"], None)
                    if (r["crop"], r["states"]) in budgets:
                        self.operating[r["crop"]] = budgets[(r["crop"], r["states"])]
        self.reference_operating = {
            crop: share for (crop, scope), share in budgets.items() if scope == "reference"
        }
        self.rows = {
            (r["crop"], r["situation"], r["tillage"]): Cost(
                float(r["usd_per_acre"]), _flag(r["verified"]), (r["source"],)
            )
            for r in (rows if rows is not None else _rows("costs.csv"))
        }
        self.cover: dict[str, Cost] = {}
        for r in cover_rows if cover_rows is not None else _rows("cover_costs.csv"):
            old = self.cover.get(r["cover_crop"], Cost(0.0, True, ()))
            self.cover[r["cover_crop"]] = Cost(
                old.usd_per_acre + float(r["usd_per_acre"]),
                old.verified and _flag(r["verified"]),
                old.sources + (r["source"],),
            )
        self.crops = {key[0] for key in self.rows} | set(self.regional)

    def override(self, crop: str, usd_per_acre: float) -> None:
        """The farmer's own cost of a crop (land excluded) replaces the level of the tables.

        It stands for the reference situation: conventional tillage, after a different crop
        (alfalfa: the seeding year). The differences between situations still come from
        costs.csv.
        """
        self.regional[crop] = Cost(float(usd_per_acre), True, ("farmer",))
        self.operating.pop(crop, None)  # the split of the farmer's own number is not known
        self.crops.add(crop)

    def operating_share(self, crop: str, previous: str | None) -> float | None:
        """Operating costs as a share of the crop's cost (see _ers_operating), None when the
        budget in use does not give the split or the cost is the farmer's own."""
        if crop in self.regional:
            return self.operating.get(crop)
        situation = self._situation(crop, previous)
        found = self.reference_operating
        return found.get(f"{crop}:{situation}", found.get(crop))

    def _situation(self, crop: str, previous: str | None) -> str:
        if crop == "corn":
            return "after_corn" if previous == "corn" else "after_other"
        if crop == "alfalfa":
            return "established" if previous == "alfalfa" else "seeding"
        return "any"

    def crop_cost(self, crop: str, previous: str | None, tillage: str) -> Cost | None:
        local = self._budget(crop, previous, tillage)
        level = self.regional.get(crop)
        if level is None:
            return local
        reference = self._budget(crop, None, TILLAGE[0])
        if local is None or reference is None or local is reference:
            return level
        return Cost(
            level.usd_per_acre + local.usd_per_acre - reference.usd_per_acre,
            level.verified and local.verified,
            level.sources + local.sources,
        )

    def _budget(self, crop: str, previous: str | None, tillage: str) -> Cost | None:
        """The costs.csv budget for the situation, None when the crop has none."""
        situation = self._situation(crop, previous)
        for key in ((crop, situation, tillage), (crop, situation, "any")):
            if key in self.rows:
                return self.rows[key]
        # No budget for this tillage in this situation (corn after corn): shift the conventional
        # budget by the tillage difference published for the other situation.
        base = self.rows.get((crop, situation, "conventional"))
        other = [s for (c, s, t) in self.rows if c == crop and t == tillage and s != situation]
        if base is None or not other:
            return base and Cost(base.usd_per_acre, False, base.sources)
        shifted = self.rows[(crop, other[0], tillage)]
        reference = self.rows[(crop, other[0], "conventional")]
        return Cost(
            base.usd_per_acre + shifted.usd_per_acre - reference.usd_per_acre,
            False,
            base.sources + shifted.sources,
        )

    def cover_cost(self, cover: str) -> Cost:
        if cover == "none":
            return Cost(0.0, True, ())
        return self.cover[cover]


@dataclass(frozen=True)
class Response:
    id: str
    rule: str  # the engine hazard rule whose points this row replaces
    applies_to: str  # crop id
    kind: str  # per_hit | per_unit | per_drought_week | per_d4_week
    loss_low: float
    loss_high: float
    cap: float
    verified: bool
    basis: str
    source: str
    url: str

    @property
    def loss(self) -> float:
        return (self.loss_low + self.loss_high) / 2


def load_responses() -> list[Response]:
    return [
        Response(
            r["id"],
            r["rule"],
            r["applies_to"],
            r["kind"],
            float(r["loss_low"]),
            float(r["loss_high"]),
            float(r["cap"]),
            _flag(r["verified"]),
            r["basis"],
            r["source"],
            r["url"],
        )
        for r in _rows("weather_yield_response.csv")
    ]


def load_adjustments() -> dict[str, dict]:
    return {
        r["id"]: {**r, "value": float(r["value"]), "verified": _flag(r["verified"])}
        for r in _rows("crop_adjustments.csv")
    }


@dataclass(frozen=True)
class CarbonInput:
    dry_matter: float
    shoot_per_harvest_c: float
    root_per_harvest_c: float
    verified: bool
    source: str


def load_carbon_inputs() -> dict[str, CarbonInput]:
    return {
        r["applies_to"]: CarbonInput(
            float(r["dry_matter"]),
            float(r["shoot_residue_per_harvest_c"]),
            float(r["root_per_harvest_c"]),
            _flag(r["verified"]),
            r["source"],
        )
        for r in _rows("soil_carbon.csv")
    }
