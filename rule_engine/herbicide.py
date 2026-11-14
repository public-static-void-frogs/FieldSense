"""Herbicide plant-back (rotational restriction) facts for a candidate crop.

The table holds the longest label interval, in months, between applying a residual herbicide
and planting each following crop. Source: University of Wisconsin-Madison Extension,
"Herbicide Rotational Restrictions for Cover and Forage Cropping Systems" (2024),
https://cropsandsoils.extension.wisc.edu/files/2024/03/RotationalRestrictions_2024_digital.pdf
It is a Wisconsin compilation of label maxima, not an Iowa table: the product label governs.
Sorghum, other hay and pasture have no column there, so they are reported as unknown.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from rule_engine.catalog import Crop
from rule_engine.reference import StageCalendar

DEFAULT_TABLE = Path(__file__).resolve().parent / "data" / "herbicide_plantback.csv"
TABLE_COLUMN = {
    "corn": "corn",
    "soybeans": "soybeans",
    "alfalfa": "alfalfa",
    "winter_wheat": "wheat",
    "spring_wheat": "wheat",
    "oats": "oats",
    "rye": "rye",
}
DEFAULT_APPLICATION_MONTH = 6
FALL_SOWING_MONTH = 10  # fall-sown cereals have no in-season planting stage in the calendar
LATE_APPLICATION_MONTH = 7  # ISU / Purdue: carry-over cases follow July or later applications


@dataclass(frozen=True)
class PlantBack:
    active: str
    group: str
    months: dict[str, float]  # table column -> months; missing column = not listed


def load_plantback(path: Path = DEFAULT_TABLE) -> dict[str, PlantBack]:
    table = {}
    with Path(path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            months = {
                column: float(row[column])
                for column in set(TABLE_COLUMN.values())
                if (row.get(column) or "").strip()
            }
            table[row["active"]] = PlantBack(row["active"], row["wssa_group"], months)
    return table


def _key(name) -> str:
    return str(name).strip().lower().replace("-", "_").replace(" ", "_")


def _elapsed_months(season: int, month: int, calendar: StageCalendar) -> int:
    """Months from application (`season` seasons ago) to planting the candidate."""
    planted = calendar.stages.get("planted")
    if planted is None:  # sown in the autumn of the last season
        return max(0, 12 * (season - 1) + FALL_SOWING_MONTH - month)
    planting_month = min(12, (int(planted) - 1) // 30 + 1)
    return 12 * season - month + planting_month


def herbicide_facts(
    field: dict, crop: Crop, calendar: StageCalendar, table: dict[str, PlantBack]
) -> tuple[dict, list[str]]:
    """(facts, actives with no known interval for this crop).

    `field["practices"]["herbicides"]` is a list of {active, month?, season?}: `month` is the
    application month (default June) and `season` how many seasons ago (default 1, last season).
    """
    entries = (field.get("practices") or {}).get("herbicides")
    if entries is None:
        return {"herbicide.provided": False}, []
    column = TABLE_COLUMN.get(crop.id)
    shortfall, limiting, restricted, late, unknown = None, None, [], 0, []
    groups: dict[int, set[str]] = {}
    for entry in entries:
        entry = entry if isinstance(entry, dict) else {"active": entry}
        active = _key(entry.get("active"))
        season = int(entry.get("season") or 1)
        month = int(entry.get("month") or DEFAULT_APPLICATION_MONTH)
        row = table.get(active)
        group = _key(entry["group"]) if entry.get("group") else (row.group if row else None)
        if group:
            groups.setdefault(season, set()).add(group)
        if row is None or column is None or column not in row.months:
            unknown.append(active)
            continue
        interval = row.months[column]
        gap = interval - _elapsed_months(season, month, calendar)
        if shortfall is None or gap > shortfall:
            shortfall, limiting = gap, active
        if interval > 0 and season == 1:
            restricted.append(active)
            if month >= LATE_APPLICATION_MONTH:
                late += 1
    repeated = sorted(groups.get(1, set()) & groups.get(2, set()))
    facts = {
        "herbicide.provided": True,
        "herbicide.restricted_actives": sorted(set(restricted)),
        "herbicide.late_restricted_count": late,
        "herbicide.repeated_groups": repeated,
        "herbicide.repeated_group_count": len(repeated),
    }
    if shortfall is not None:
        facts["herbicide.shortfall_months"] = round(max(0.0, shortfall), 1)
        facts["herbicide.limiting_active"] = limiting
    return facts, sorted(set(unknown))
