"""Soil-health view: a provider protocol for the soil team plus indicators derived from our data."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from rule_engine.catalog import Crop
from rule_engine.facts import HistoryYear
from rule_engine.summary import SeasonSummary

Basis = Literal["crop_trait", "cdl_history", "smap_rootzone", "soil_team"]


@dataclass(frozen=True)
class SoilIndicator:
    """One machine-readable indicator; wording is left to the consumer."""

    id: str
    value: float | str | None
    unit: str | None
    direction: Literal["better", "worse", "neutral", "unknown"]
    basis: Basis  # what the value is computed from
    kind: Literal["derived_indicator", "soil_team"]
    verified: bool = True  # False when an input trait is flagged unverified
    threshold: float | None = None  # value compared against to set `direction`
    inputs: dict = field(default_factory=dict)


class SoilHealthProvider(Protocol):
    """The soil team plugs in here; the engine only passes through what comes back."""

    name: str

    def indicators(
        self,
        field: dict,
        candidate: Crop,
        history: list[HistoryYear],
        seasons: list[SeasonSummary],
    ) -> list[SoilIndicator]: ...


def _direction(value, worse_when_high: bool, threshold: float):
    if value is None:
        return "unknown"
    if value > threshold:
        return "worse" if worse_when_high else "better"
    if value < threshold:
        return "better" if worse_when_high else "worse"
    return "neutral"


def _verified(crop: Crop, name: str) -> bool:
    try:
        return crop.trait(name).verified
    except KeyError:
        return False


class DerivedSoilIndicators:
    """Indicators derived from catalog traits, CDL history and SMAP; not soil measurements."""

    name = "derived_indicator"

    def indicators(self, field, candidate, history, seasons):
        prev = next((y.crop for y in reversed(history) if y.crop), None)
        bare = candidate.value("bare_soil_months")
        rusle = candidate.value("rusle_c")
        humus = candidate.value("humus_balance")
        residue = candidate.value("residue")
        n_fixer = bool(candidate.value("n_fixer"))
        n_demand = candidate.value("n_demand")
        recent = [y.crop for y in history[-5:] if y.crop]
        latest = seasons[-1] if seasons else None
        rz_weeks = None
        if latest and latest.weekly.get("rz_lt20_days"):
            days = [d for d in latest.weekly["rz_lt20_days"] if d is not None]
            rz_weeks = sum(1 for d in days if d >= 4)

        if n_fixer:
            n_value, n_dir = "fixer", "better"
        elif n_demand == "high":
            n_value, n_dir = "high_demand", "worse"
        else:
            n_value, n_dir = f"{n_demand or 'unknown'}_demand", "neutral"

        def trait(id_, value, unit, direction, name, threshold=None):
            return SoilIndicator(
                id_,
                value,
                unit,
                direction,
                "crop_trait",
                self.name,
                _verified(candidate, name),
                threshold,
                {"trait": name, "crop": candidate.id},
            )

        return [
            trait(
                "bare_soil_months", bare, "months", _direction(bare, True, 4), "bare_soil_months", 4
            ),
            trait(
                "erosion_exposure", rusle, "rusle_c", _direction(rusle, True, 0.25), "rusle_c", 0.25
            ),
            trait(
                "residue_return",
                residue,
                None,
                {"high": "better", "medium": "neutral", "low": "worse"}.get(residue, "unknown"),
                "residue",
            ),
            trait(
                "humus_balance",
                humus,
                "humus_eq_ha_yr",
                _direction(humus, False, 0),
                "humus_balance",
                0,
            ),
            SoilIndicator(
                "n_balance",
                n_value,
                None,
                n_dir,
                "crop_trait",
                self.name,
                _verified(candidate, "n_fixer") and _verified(candidate, "n_demand"),
                None,
                {"nFixer": n_fixer, "nDemand": n_demand, "previousCrop": prev},
            ),
            SoilIndicator(
                "rotation_diversity",
                len(set(recent)),
                "distinct_crops_5y",
                _direction(len(set(recent)), False, 2) if history else "unknown",
                "cdl_history",
                self.name,
                True,
                2,
                {
                    "seasons": len(recent),
                    "satelliteEstimate": any(y.source == "cdl" for y in history),
                },
            ),
            SoilIndicator(
                "rootzone_dry_weeks",
                rz_weeks,
                "weeks",
                _direction(rz_weeks, True, 2) if rz_weeks is not None else "unknown",
                "smap_rootzone",
                self.name,
                True,
                2,
                {
                    "season": latest.year if latest else None,
                    "metric": "rz_lt20_days",
                    "minDaysPerWeek": 4,
                    "gridKm": 9,
                },
            ),
        ]
