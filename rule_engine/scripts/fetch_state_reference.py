"""Per-state reference tables for every state, from USDA NASS Quick Stats.

Usage (from the repo root; needs USDA_DATA_KEY in .env or the environment):

    python rule_engine/scripts/fetch_state_reference.py

Writes three files in rule_engine/data. The curated Iowa files (iowa_stage_calendar.csv,
reference_yields.csv, prices.csv) are not touched and win over these where both have a row.

    state_stage_calendar.csv   region, crop, stage, doy_p50: median over START_YEAR.. of the day
                               each year's state crop progress crossed 50 %
    state_reference_yields.csv region, crop, low, mid, high: min, mean, max of the state yields
    state_prices.csv           region, crop, price: latest marketing-year price received

NASS reports crop progress only for the main producing states of each crop, so many
(state, crop) pairs stay without a calendar and fall back to the crop or group default.
"""

import csv
import json
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_nass_reference import API, DATA, _key  # noqa: E402

START_YEAR = 2021
LB_PER_BU_CANOLA = 50
CWT_PER_BU = {"sorghum": 0.56, "canola": 0.50}

# crop id -> (commodity_desc, class_desc or None, {engine stage: NASS progress unit})
PROGRESS = {
    "corn": ("CORN", None, {"planted": "PLANTED", "emerged": "EMERGED", "flowering": "SILKING",
             "grain_fill": "DOUGH", "mature": "MATURE", "harvested": "HARVESTED"}),
    "soybeans": ("SOYBEANS", None, {"planted": "PLANTED", "emerged": "EMERGED",
                 "flowering": "BLOOMING", "grain_fill": "SETTING PODS",
                 "mature": "DROPPING LEAVES", "harvested": "HARVESTED"}),
    "sorghum": ("SORGHUM", None, {"planted": "PLANTED", "flowering": "HEADED",
                "grain_fill": "COLORING", "mature": "MATURE", "harvested": "HARVESTED"}),
    "oats": ("OATS", None, {"planted": "PLANTED", "emerged": "EMERGED", "flowering": "HEADED",
             "grain_fill": "COLORING", "harvested": "HARVESTED"}),
    "barley": ("BARLEY", None, {"planted": "PLANTED", "emerged": "EMERGED",
               "flowering": "HEADED", "harvested": "HARVESTED"}),
    "spring_wheat": ("WHEAT", "SPRING, (EXCL DURUM)", {"planted": "PLANTED", "emerged": "EMERGED",
                     "flowering": "HEADED", "harvested": "HARVESTED"}),
    # fall-sown: planting and emergence belong to the previous autumn and are left out
    "winter_wheat": ("WHEAT", "WINTER", {"flowering": "HEADED", "harvested": "HARVESTED"}),
}  # fmt: skip
GRAIN_FILL_AFTER_HEADING = 15  # days; used when NASS reports no grain-fill stage for a cereal
MATURE_BEFORE_HARVEST = 10

# crop id -> (short_desc, unit in the table, multiplier)
YIELDS = {
    "corn": ("CORN, GRAIN - YIELD, MEASURED IN BU / ACRE", "bu/acre", 1),
    "soybeans": ("SOYBEANS - YIELD, MEASURED IN BU / ACRE", "bu/acre", 1),
    "sorghum": ("SORGHUM, GRAIN - YIELD, MEASURED IN BU / ACRE", "bu/acre", 1),
    "oats": ("OATS - YIELD, MEASURED IN BU / ACRE", "bu/acre", 1),
    "barley": ("BARLEY - YIELD, MEASURED IN BU / ACRE", "bu/acre", 1),
    "rye": ("RYE - YIELD, MEASURED IN BU / ACRE", "bu/acre", 1),
    "winter_wheat": ("WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE", "bu/acre", 1),
    "spring_wheat": ("WHEAT, SPRING, (EXCL DURUM) - YIELD, MEASURED IN BU / ACRE", "bu/acre", 1),
    "canola": ("CANOLA - YIELD, MEASURED IN LB / ACRE", "bu/acre", 1 / LB_PER_BU_CANOLA),
    "alfalfa": ("HAY, ALFALFA - YIELD, MEASURED IN TONS / ACRE", "ton/acre", 1),
    "other_hay": ("HAY, (EXCL ALFALFA) - YIELD, MEASURED IN TONS / ACRE", "ton/acre", 1),
}
PRICES = {
    "oats": ("OATS - PRICE RECEIVED, MEASURED IN $ / BU", "bu", 1),
    "barley": ("BARLEY - PRICE RECEIVED, MEASURED IN $ / BU", "bu", 1),
    "winter_wheat": ("WHEAT, WINTER - PRICE RECEIVED, MEASURED IN $ / BU", "bu", 1),
    "spring_wheat": ("WHEAT, SPRING, (EXCL DURUM) - PRICE RECEIVED, MEASURED IN $ / BU", "bu", 1),
    "sorghum": ("SORGHUM, GRAIN - PRICE RECEIVED, MEASURED IN $ / CWT", "bu", CWT_PER_BU["sorghum"]),
    "canola": ("CANOLA - PRICE RECEIVED, MEASURED IN $ / CWT", "bu", CWT_PER_BU["canola"]),
    "alfalfa": ("HAY, ALFALFA - PRICE RECEIVED, MEASURED IN $ / TON", "ton", 1),
    "other_hay": ("HAY, (EXCL ALFALFA) - PRICE RECEIVED, MEASURED IN $ / TON", "ton", 1),
}  # fmt: skip


def _get(key: str, **query) -> list[dict]:
    query = {"key": key, "format": "JSON", "source_desc": "SURVEY", "agg_level_desc": "STATE",
             "year__GE": str(START_YEAR), **query}  # fmt: skip
    try:
        with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(query)}", timeout=120) as resp:
            return json.load(resp)["data"]
    except urllib.error.HTTPError as error:  # 400 = no data for the query
        print(f"  NASS returned {error.code} for {query.get('short_desc') or query}")
        return []


def _number(text: str) -> float | None:
    try:
        return float(text.replace(",", "").strip())
    except ValueError:  # (D), (NA), ...
        return None


def _crossing(points: list[tuple[int, float]]) -> float | None:
    """Day of year when weekly percent-complete first reaches 50, linearly interpolated."""
    points = sorted(points)
    for index, (doy, value) in enumerate(points):
        if value >= 50:
            if index == 0:
                return float(doy) if value < 75 else None  # first report already past: unknown
            prev_doy, prev_value = points[index - 1]
            if value == prev_value:
                return float(doy)
            return prev_doy + (50 - prev_value) / (value - prev_value) * (doy - prev_doy)
    return None


def calendars(key: str, today: str) -> list[dict]:
    rows = []
    for crop, (commodity, klass, stages) in PROGRESS.items():
        query = {
            "commodity_desc": commodity,
            "statisticcat_desc": "PROGRESS",
            "freq_desc": "WEEKLY",
        }
        if klass:
            query["class_desc"] = klass
        data = _get(key, **query)
        series: dict[tuple, list] = {}
        for row in data:
            value = _number(row["Value"])
            if value is None or not row.get("week_ending"):
                continue
            unit = row["unit_desc"].replace("PCT ", "")
            doy = date.fromisoformat(row["week_ending"]).timetuple().tm_yday
            series.setdefault((row["state_alpha"], unit, int(row["year"])), []).append((doy, value))
        medians: dict[tuple, tuple[float, int, int, int]] = {}
        for (state, unit), group in _by_state_unit(series).items():
            days = {year: _crossing(points) for year, points in group.items()}
            days = {year: day for year, day in days.items() if day is not None}
            if days:
                medians[(state, unit)] = (
                    statistics.median(days.values()), len(days), min(days), max(days))  # fmt: skip
        states = sorted({state for state, _ in medians})
        for state in states:
            found = {}
            for stage, unit in stages.items():
                if (state, unit) in medians:
                    doy, count, first, last = medians[(state, unit)]
                    found[stage] = (
                        round(doy),
                        f"USDA NASS Crop Progress, {state} {first}-{last} "
                        f"({count} seasons), median day 50% {unit.lower()}",
                    )
            if "flowering" in found and "harvested" in found:
                if "grain_fill" not in found:
                    found["grain_fill"] = (
                        min(
                            found["flowering"][0] + GRAIN_FILL_AFTER_HEADING, found["harvested"][0]
                        ),
                        f"Derived: {GRAIN_FILL_AFTER_HEADING} days after 50% "
                        f"{stages['flowering'].lower()} "
                        "(NASS reports no grain-fill stage)",
                    )
                if "mature" not in found:
                    found["mature"] = (
                        max(found["harvested"][0] - MATURE_BEFORE_HARVEST, found["grain_fill"][0]),
                        f"Derived: {MATURE_BEFORE_HARVEST} days before 50% harvested "
                        "(NASS reports no maturity stage)",
                    )
            if not {"flowering", "harvested"} <= set(found):
                continue  # too little to place the season
            for stage, (doy, source) in found.items():
                rows.append({"region": state, "crop": crop, "stage": stage, "doy_p50": doy,
                             "source": source, "as_of": today})  # fmt: skip
        print(f"  progress {crop}: {len(data):,} rows, {len(states)} states")
    return rows


def _by_state_unit(series: dict) -> dict:
    grouped: dict[tuple, dict] = {}
    for (state, unit, year), points in series.items():
        grouped.setdefault((state, unit), {})[year] = points
    return grouped


def _annual(key: str, short_desc: str, period: str) -> dict[str, dict[int, float]]:
    values: dict[str, dict[int, float]] = {}
    for row in _get(key, short_desc=short_desc, freq_desc="ANNUAL", domain_desc="TOTAL",
                    reference_period_desc=period):  # fmt: skip
        number = _number(row["Value"])
        if number is not None and row.get("state_alpha"):
            values.setdefault(row["state_alpha"], {})[int(row["year"])] = number
    return values


def yields(key: str, today: str) -> list[dict]:
    rows = []
    for crop, (short_desc, unit, multiplier) in YIELDS.items():
        by_state = _annual(key, short_desc, "YEAR")
        for state, values in sorted(by_state.items()):
            recent = [values[y] * multiplier for y in sorted(values)]
            rows.append({
                "region": state, "crop": crop, "level": "state",
                "low": round(min(recent), 2), "mid": round(sum(recent) / len(recent), 2),
                "high": round(max(recent), 2), "unit": unit,
                "source": f"USDA NASS Quick Stats: {short_desc}; {state}, "
                f"{min(values)}-{max(values)} (min, mean, max)",
                "as_of": today, "verified": "true",
            })  # fmt: skip
        print(f"  yield {crop}: {len(by_state)} states")
    return rows


def prices(key: str, today: str) -> list[dict]:
    rows = []
    for crop, (short_desc, unit, multiplier) in PRICES.items():
        by_state = _annual(key, short_desc, "MARKETING YEAR")
        for state, values in sorted(by_state.items()):
            year = max(values)
            rows.append({
                "region": state, "crop": crop, "price_usd": round(values[year] * multiplier, 2),
                "unit": unit,
                "source": f"USDA NASS Quick Stats: {short_desc}; {state}, marketing year {year}",
                "as_of": today, "verified": "true", "level": "state",
            })  # fmt: skip
        print(f"  price {crop}: {len(by_state)} states")
    return rows


def _write(name: str, rows: list[dict]) -> None:
    with (DATA / name).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{name}: {len(rows)} rows")


def main() -> None:
    key, today = _key(), date.today().isoformat()
    _write("state_stage_calendar.csv", calendars(key, today))
    _write("state_reference_yields.csv", yields(key, today))
    _write("state_prices.csv", prices(key, today))


if __name__ == "__main__":
    main()
