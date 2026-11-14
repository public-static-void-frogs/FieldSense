"""Small region reference tables: stage calendars, reference yields and prices (CSV)."""

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from rule_engine.catalog import Crop

DEFAULT_FOLDER = Path(__file__).resolve().parent / "data"
PILOT_REGION = "IA"  # state-level rows of the curated prices.csv were observed here


@dataclass(frozen=True)
class StageCalendar:
    crop_id: str
    region: str
    stages: dict[str, int]
    source: str
    kind: Literal["nass_region", "crop_default", "group_default"]
    local_shift: tuple[tuple[str, int], ...] = ()  # (stage, days moved by a local date)
    local_source: str | None = None


# a stage without a local date of its own moves with the stage it follows
STAGE_FOLLOWS = {"emerged": "planted", "grain_fill": "flowering", "harvested": "mature"}


def localize(calendar: StageCalendar, stages: dict[str, int], source: str | None) -> StageCalendar:
    """Replace regional stage dates with local ones (day of year), keeping the regional spacing.

    Only stages the regional calendar already has are moved, so a local date never adds a stage.
    """
    shifts = {
        stage: int(round(doy)) - calendar.stages[stage]
        for stage, doy in stages.items()
        if stage in calendar.stages and doy is not None
    }
    for stage, anchor in STAGE_FOLLOWS.items():
        if stage not in shifts and anchor in shifts and stage in calendar.stages:
            shifts[stage] = shifts[anchor]
    shifts = {stage: days for stage, days in shifts.items() if days}
    if not shifts:
        return calendar
    return StageCalendar(
        crop_id=calendar.crop_id,
        region=calendar.region,
        stages={s: doy + shifts.get(s, 0) for s, doy in calendar.stages.items()},
        source=calendar.source,
        kind=calendar.kind,
        local_shift=tuple(sorted(shifts.items())),
        local_source=source,
    )


@dataclass(frozen=True)
class PriceQuote:
    crop_id: str
    price_usd: float
    unit: str
    source: str
    as_of: str
    verified: bool
    level: str = "state"  # state | national: where the price was observed
    region: str | None = None  # the state a state-level price was observed in


@dataclass(frozen=True)
class YieldReference:
    crop_id: str
    region: str
    level: str
    low: float
    mid: float
    high: float
    unit: str
    source: str
    as_of: str
    verified: bool


def _flag(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class ReferenceTables:
    calendars: dict[tuple[str, str], StageCalendar]
    prices: dict[str, PriceQuote]
    yields: dict[tuple[str, str], YieldReference]
    state_prices: dict[tuple[str, str], PriceQuote] = field(default_factory=dict)

    def calendar(self, crop: Crop, region: str) -> StageCalendar:
        found = self.calendars.get((region, crop.id))
        if found is not None:
            return found
        if crop.calendar:
            return StageCalendar(
                crop_id=crop.id,
                region=region,
                stages=dict(crop.calendar),
                source=" ".join((crop.calendar_source or "crop default; unverified").split()),
                kind="crop_default",
            )
        return StageCalendar(
            crop_id=crop.id,
            region=region,
            stages=dict(crop.group.calendar),
            source=f"Group default calendar for {crop.group.label} (no NASS crop progress for "
            f"{crop.label} in {region}); unverified",
            kind="group_default",
        )

    def price(self, crop_id: str, region: str | None = None) -> PriceQuote | None:
        """The planning price: the crop's default quote unless it was observed in another
        state and the field's own state has a quote."""
        default = self.prices.get(crop_id)
        local = self.state_prices.get((region, crop_id)) if region else None
        if local is not None and (default is None or default.region not in (None, region)):
            return local
        return default

    def yield_reference(self, crop_id: str, region: str) -> YieldReference | None:
        return self.yields.get((region, crop_id))


def _calendar_rows(rows, calendars, source=None) -> None:
    for row in rows:
        key = (row["region"], row["crop"])
        current = calendars.get(key)
        stages = dict(current.stages) if current else {}
        stages[row["stage"]] = int(float(row["doy_p50"]))
        calendars[key] = StageCalendar(
            crop_id=row["crop"],
            region=row["region"],
            stages=stages,
            source=source
            or f"USDA NASS Crop Progress, {row['region']} multi-year median (50%) dates",
            kind="nass_region",
        )


def _price(row, region=None) -> PriceQuote:
    level = row.get("level") or "state"
    return PriceQuote(
        crop_id=row["crop"],
        price_usd=float(row["price_usd"]),
        unit=row["unit"],
        source=row["source"],
        as_of=row["as_of"],
        verified=_flag(row["verified"]),
        level=level,
        region=region if level == "state" else None,
    )


def _yield(row) -> YieldReference:
    return YieldReference(
        crop_id=row["crop"],
        region=row["region"],
        level=row["level"],
        low=float(row["low"]),
        mid=float(row["mid"]),
        high=float(row["high"]),
        unit=row["unit"],
        source=row["source"],
        as_of=row["as_of"],
        verified=_flag(row["verified"]),
    )


def _optional(path: Path) -> list[dict[str, str]]:
    return _rows(path) if path.exists() else []


def load_reference(folder: Path = DEFAULT_FOLDER) -> ReferenceTables:
    """Curated pilot-region tables first; the state_* tables (every state, built by
    scripts/fetch_state_reference.py) only fill (region, crop) pairs the curated ones lack."""
    folder = Path(folder)
    calendars: dict[tuple[str, str], StageCalendar] = {}
    _calendar_rows(
        _rows(folder / "iowa_stage_calendar.csv"),
        calendars,
        source="USDA NASS Crop Progress, Iowa 2025 median (50%) dates",
    )
    curated = set(calendars)
    state_rows = _optional(folder / "state_stage_calendar.csv")
    _calendar_rows([r for r in state_rows if (r["region"], r["crop"]) not in curated], calendars)
    prices = {row["crop"]: _price(row, PILOT_REGION) for row in _rows(folder / "prices.csv")}
    state_prices = {
        (row["region"], row["crop"]): _price(row, row["region"])
        for row in _optional(folder / "state_prices.csv")
    }
    yields = {
        (row["region"], row["crop"]): _yield(row) for row in _rows(folder / "reference_yields.csv")
    }
    for row in _optional(folder / "state_reference_yields.csv"):
        yields.setdefault((row["region"], row["crop"]), _yield(row))
    return ReferenceTables(
        calendars=calendars, prices=prices, yields=yields, state_prices=state_prices
    )
