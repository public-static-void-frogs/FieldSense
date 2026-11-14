"""State and national prices and state yields since 1980, from USDA NASS Quick Stats.

    python rule_engine/planner/scripts/fetch_long_history.py

Needs USDA_DATA_KEY in .env or the environment. Writes rule_engine/planner/data/
nass_long_history.csv with the columns the planner reads from the rule engine's
nass_reference_history.csv (kind, crop, geography, year, value, unit), for every state that
NASS reports and for the United States. The planner prefers this file where it has a series.
"""

import csv
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "rule_engine" / "scripts"))
from fetch_nass_reference import API, _key  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "nass_long_history.csv"
START_YEAR = 1980

# (kind, crop id, short_desc, reference period, unit)
SERIES = [
    ("price", "corn", "CORN, GRAIN - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu"),
    ("price", "soybeans", "SOYBEANS - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu"),
    ("price", "oats", "OATS - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu"),
    ("price", "alfalfa", "HAY, ALFALFA - PRICE RECEIVED, MEASURED IN $ / TON", "MARKETING YEAR", "usd/ton"),
    ("yield", "oats", "OATS - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre"),
    ("yield", "alfalfa", "HAY, ALFALFA - YIELD, MEASURED IN TONS / ACRE", "YEAR", "ton/acre"),
]  # fmt: skip


def fetch(key: str, short_desc: str, period: str, level: str) -> list[tuple[str, int, float]]:
    query = {
        "key": key,
        "format": "JSON",
        "short_desc": short_desc,
        "freq_desc": "ANNUAL",
        "reference_period_desc": period,
        "domain_desc": "TOTAL",
        "source_desc": "SURVEY",
        "year__GE": str(START_YEAR),
        "agg_level_desc": level,
    }
    try:
        with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(query)}", timeout=120) as resp:
            rows = json.load(resp)["data"]
    except urllib.error.HTTPError as error:  # 400 = no data for the query
        print(f"  NASS returned {error.code} for {short_desc} ({level})")
        return []
    out = []
    for row in rows:
        text = row["Value"].replace(",", "").strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", text):  # skips (D), (NA), ...
            geography = "US" if level == "NATIONAL" else row["state_alpha"]
            out.append((geography, int(row["year"]), float(text)))
    return out


def main() -> None:
    key = _key()
    rows = []
    for kind, crop, short_desc, period, unit in SERIES:
        found = {}
        for level in ("STATE", "NATIONAL"):
            for geography, year, value in fetch(key, short_desc, period, level):
                found[(geography, year)] = value
        states = {g for g, _ in found}
        years = [y for _, y in found]
        print(f"{kind} {crop}: {len(found)} values, {len(states)} geographies, "
              f"{min(years, default=0)}-{max(years, default=0)}")  # fmt: skip
        for (geography, year), value in sorted(found.items()):
            rows.append([kind, crop, geography, year, value, unit, short_desc])
    with OUT.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["kind", "crop", "geography", "year", "value", "unit", "nass_short_desc"])
        writer.writerows(rows)
    print(f"wrote {OUT}: {len(rows)} rows")


if __name__ == "__main__":
    main()
