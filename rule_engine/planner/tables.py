"""The planner's own reference tables: production costs, weather yield response, soil carbon.

Every row carries its source and a `verified` flag. Unverified rows are usable but are reported
under data gaps by the environment, the same way the rule engine treats unverified traits.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).parent / "data"
TILLAGE = ("conventional", "strip_till", "no_till")
COVER = ("none", "rye")


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


class CostTable:
    """Cost of production per acre, land excluded, so the result is a return to land."""

    def __init__(self, rows=None, cover_rows=None):
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
        self.crops = {key[0] for key in self.rows}

    def _situation(self, crop: str, previous: str | None) -> str:
        if crop == "corn":
            return "after_corn" if previous == "corn" else "after_other"
        if crop == "alfalfa":
            return "established" if previous == "alfalfa" else "seeding"
        return "any"

    def crop_cost(self, crop: str, previous: str | None, tillage: str) -> Cost | None:
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
        r["group"]: CarbonInput(
            float(r["dry_matter"]),
            float(r["shoot_residue_per_harvest_c"]),
            float(r["root_per_harvest_c"]),
            _flag(r["verified"]),
            r["source"],
        )
        for r in _rows("soil_carbon.csv")
    }
