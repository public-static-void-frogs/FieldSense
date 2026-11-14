"""The off-season slot: what can grow between the previous crop's harvest and the next planting.

The candidate ranking answers "which crop next season". This module answers the other half of the
year: after the crop now in the field is harvested, is there enough autumn left to establish a
cover crop or a fall-sown cash crop? It reads only the long weather record (weekly gridMET at the
nearest grid node) and the stage calendar, so it works the same way in every state.

Each option is tested season by season: the share of recorded autumns in which its establishment
criterion was met. Criteria are in OPTIONS, with their sources as comments. Dates are calendar medians and the
weather is weekly, so a result is a frequency over past autumns, not a forecast for this one.
"""

from dataclasses import dataclass
from statistics import median

from rule_engine.summary import SeasonSummary

SEEDING_LAG_DAYS = 7  # harvest to drilling the next crop
KILLING_FROST_C = -2.0  # hard freeze that ends the growth of winter-killed species
FROST_SEARCH_START_DOY = 213  # 1 August
YEAR_END_DOY = 365
RELIABLE_SHARE = 0.8
MARGINAL_SHARE = 0.5
MIN_SEASONS = 10  # fewer recorded autumns than this cannot support a frequency


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    kind: str  # cover_crop | winter_cash_crop
    overwinters: bool
    metric: str  # fall_gdd0 | days_to_killing_frost
    minimum: float
    needs_local_review: bool
    crop_id: str | None = None  # the candidate crop this option is, when it is one


OPTIONS = (
    Option(
        id="cereal_rye",
        label="Cereal rye cover crop",
        kind="cover_crop",
        overwinters=True,
        metric="fall_gdd0",
        minimum=130.0,  # degree days a winter cereal needs to germinate and emerge from 1 inch
        # Field Crop News (Ontario), winter wheat emergence; NRCS Iowa cereal rye fact sheet, 2024
        needs_local_review=True,
    ),
    Option(
        id="oats",
        label="Oat cover crop (winter-killed)",
        kind="cover_crop",
        overwinters=False,
        metric="days_to_killing_frost",
        minimum=40.0,  # days of growth before the first killing frost
        # SARE, Managing Cover Crops Profitably: oats
        needs_local_review=False,
    ),
    Option(
        id="winter_wheat",
        label="Winter wheat for harvest next summer",
        kind="winter_cash_crop",
        overwinters=True,
        metric="fall_gdd0",
        minimum=400.0,  # degree days to three leaves and the first tiller before winter
        # Virginia Tech SPES-431; Oakes et al. 2016
        needs_local_review=True,
        crop_id="winter_wheat",
    ),
)


def killing_frost_doy(season: SeasonSummary) -> int | None:
    """Middle of the first week from 1 August with a hard freeze. None when the autumn had none.

    The record is weekly, so the day inside the week is unknown; the middle keeps the date unbiased.
    """
    series = season.weekly.get("tmin_min") or []
    first = max(0, (FROST_SEARCH_START_DOY - season.week0_doy) // 7)
    for week in range(first, len(series)):
        value = series[week]
        if value is not None and value == value and value <= KILLING_FROST_C:
            return season.week0_doy + 7 * week + 3
    return None


def _heat_after(season: SeasonSummary, seeding_doy: int) -> float | None:
    """Degree days (base 0 C) from the seeding day to the year's end.

    The week that holds the seeding day counts only for its days from seeding on, so that a
    seeding late in a warm week is not credited with the whole week.
    """
    series = season.weekly.get("gdd0") or []
    week, day = divmod(seeding_doy - season.week0_doy, 7)
    values = [v if v is not None and v == v else None for v in series[max(0, week) :]]
    if not values or all(v is None for v in values):
        return None
    first = (values[0] or 0.0) * (7 - day) / 7
    return first + sum(v for v in values[1:] if v is not None)


def _measure(option: Option, season: SeasonSummary, seeding_doy: int) -> float | None:
    if option.metric == "fall_gdd0":
        return _heat_after(season, seeding_doy)
    frost = killing_frost_doy(season)
    if frost is None:
        return float(YEAR_END_DOY - seeding_doy)  # no hard freeze before the year ended
    return float(max(0, frost - seeding_doy))


def _level(share: float) -> str:
    if share >= RELIABLE_SHARE:
        return "reliable"
    return "marginal" if share >= MARGINAL_SHARE else "unlikely"


def off_season(
    previous_crop: str | None,
    harvest_doy: int | None,
    calendar_kind: str | None,
    seasons: tuple[SeasonSummary, ...] | list[SeasonSummary],
    candidate_ids: list[str],
) -> dict:
    """The slot after `previous_crop`. `status` says why there are no options when there are none."""
    slot = {
        "status": "ok",
        "afterCrop": previous_crop,
        "harvestDoy": harvest_doy,
        "seedingDoy": None,
        "calendarKind": calendar_kind,
        "seasonsTotal": 0,
        "firstKillingFrostDoy": None,
        "options": [],
    }
    if previous_crop is None:
        slot["status"] = "previous_crop_unknown"
    elif harvest_doy is None:
        slot["status"] = (
            "no_harvest_in_calendar"  # a perennial stand or a crop with no harvest stage
        )
    elif not seasons or "gdd0" not in seasons[0].weekly:
        slot["status"] = "no_weather_record"
    elif len(seasons) < MIN_SEASONS:
        slot["status"] = "weather_record_too_short"
        slot["seasonsTotal"] = len(seasons)
    if slot["status"] != "ok":
        return slot

    seeding = harvest_doy + SEEDING_LAG_DAYS
    frosts = [f for f in (killing_frost_doy(s) for s in seasons) if f is not None]
    slot.update(
        seedingDoy=seeding,
        seasonsTotal=len(seasons),
        firstKillingFrostDoy=round(median(frosts)) if frosts else None,
    )
    for option in OPTIONS:
        if option.crop_id is not None and option.crop_id not in candidate_ids:
            continue
        values = [v for v in (_measure(option, s, seeding) for s in seasons) if v is not None]
        if not values:
            continue
        met = sum(v >= option.minimum for v in values)
        share = met / len(values)
        slot["options"].append(
            {
                "id": option.id,
                "label": option.label,
                "kind": option.kind,
                "overwinters": option.overwinters,
                "cropId": option.crop_id,
                "level": _level(share),
                "seasonsMet": met,
                "seasonsTotal": len(values),
                "share": round(share, 3),
                "metric": option.metric,
                "minimum": option.minimum,
                "typical": round(median(values), 1),
                "needsLocalReview": option.needs_local_review or calendar_kind != "nass_region",
            }
        )
    return slot
