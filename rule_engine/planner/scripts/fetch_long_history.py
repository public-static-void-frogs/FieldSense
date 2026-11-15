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
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "rule_engine" / "scripts"))
from fetch_nass_reference import API, _key  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "nass_long_history.csv"
START_YEAR = 1980

# (kind, crop id, short_desc, reference period, unit, factor from the NASS unit to `unit`)
SERIES = [
    ("price", "corn", "CORN, GRAIN - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu", 1.0),
    ("price", "soybeans", "SOYBEANS - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu", 1.0),
    ("price", "oats", "OATS - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu", 1.0),
    ("price", "alfalfa", "HAY, ALFALFA - PRICE RECEIVED, MEASURED IN $ / TON", "MARKETING YEAR", "usd/ton", 1.0),
    # sorghum is priced per hundredweight; a bushel is 56 lb
    ("price", "sorghum", "SORGHUM, GRAIN - PRICE RECEIVED, MEASURED IN $ / CWT", "MARKETING YEAR", "usd/bu", 0.56),
    ("price", "winter_wheat", "WHEAT, WINTER - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu", 1.0),
    ("price", "spring_wheat", "WHEAT, SPRING, (EXCL DURUM) - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu", 1.0),
    ("price", "barley", "BARLEY - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu", 1.0),
    ("yield", "oats", "OATS - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    ("yield", "alfalfa", "HAY, ALFALFA - YIELD, MEASURED IN TONS / ACRE", "YEAR", "ton/acre", 1.0),
    ("yield", "sorghum", "SORGHUM, GRAIN - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    ("yield", "winter_wheat", "WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    ("yield", "spring_wheat", "WHEAT, SPRING, (EXCL DURUM) - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    ("yield", "barley", "BARLEY - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    ("price", "durum_wheat", "WHEAT, SPRING, DURUM - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu", 1.0),
    ("price", "cotton", "COTTON, UPLAND - PRICE RECEIVED, MEASURED IN $ / LB", "MARKETING YEAR", "usd/lb", 1.0),
    ("price", "rice", "RICE - PRICE RECEIVED, MEASURED IN $ / CWT", "MARKETING YEAR", "usd/cwt", 1.0),
    ("price", "peanuts", "PEANUTS - PRICE RECEIVED, MEASURED IN $ / LB", "MARKETING YEAR", "usd/lb", 1.0),
    ("price", "sugarbeets", "SUGARBEETS - PRICE RECEIVED, MEASURED IN $ / TON", "MARKETING YEAR", "usd/ton", 1.0),
    ("price", "potatoes", "POTATOES - PRICE RECEIVED, MEASURED IN $ / CWT", "MARKETING YEAR", "usd/cwt", 1.0),
    ("price", "sugarcane", "SUGARCANE, SUGAR - PRICE RECEIVED, MEASURED IN $ / TON", "MARKETING YEAR", "usd/ton", 1.0),
    ("price", "dry_peas", "PEAS, DRY EDIBLE - PRICE RECEIVED, MEASURED IN $ / CWT", "MARKETING YEAR", "usd/cwt", 1.0),
    ("price", "lentils", "LENTILS - PRICE RECEIVED, MEASURED IN $ / CWT", "MARKETING YEAR", "usd/cwt", 1.0),
    ("price", "chickpeas", "CHICKPEAS - PRICE RECEIVED, MEASURED IN $ / CWT", "MARKETING YEAR", "usd/cwt", 1.0),
    ("price", "millet", "MILLET, PROSO - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu", 1.0),
    ("price", "flax", "FLAXSEED - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu", 1.0),
    ("yield", "durum_wheat", "WHEAT, SPRING, DURUM - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    ("yield", "cotton", "COTTON - YIELD, MEASURED IN LB / ACRE", "YEAR", "lb/acre", 1.0),
    # pounds reported, hundredweight kept: the catalog's display unit
    ("yield", "rice", "RICE - YIELD, MEASURED IN LB / ACRE", "YEAR", "cwt/acre", 0.01),
    ("yield", "peanuts", "PEANUTS - YIELD, MEASURED IN LB / ACRE", "YEAR", "lb/acre", 1.0),
    ("yield", "sugarbeets", "SUGARBEETS - YIELD, MEASURED IN TONS / ACRE", "YEAR", "ton/acre", 1.0),
    ("yield", "potatoes", "POTATOES - YIELD, MEASURED IN CWT / ACRE", "YEAR", "cwt/acre", 1.0),
    ("yield", "sugarcane", "SUGARCANE, SUGAR - YIELD, MEASURED IN TONS / ACRE", "YEAR", "ton/acre", 1.0),
    ("yield", "dry_peas", "PEAS, DRY EDIBLE - YIELD, MEASURED IN LB / ACRE", "YEAR", "cwt/acre", 0.01),
    ("yield", "lentils", "LENTILS - YIELD, MEASURED IN LB / ACRE", "YEAR", "cwt/acre", 0.01),
    ("yield", "chickpeas", "CHICKPEAS - YIELD, MEASURED IN LB / ACRE", "YEAR", "cwt/acre", 0.01),
    ("yield", "millet", "MILLET, PROSO - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    ("yield", "flax", "FLAXSEED - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    # hay other than alfalfa (the catalog's other_hay)
    ("price", "other_hay", "HAY, (EXCL ALFALFA) - PRICE RECEIVED, MEASURED IN $ / TON", "MARKETING YEAR", "usd/ton", 1.0),
    ("yield", "other_hay", "HAY, (EXCL ALFALFA) - YIELD, MEASURED IN TONS / ACRE", "YEAR", "ton/acre", 1.0),
    # grain yields by state, for the states that publish no county yield and the ones whose
    # county series ended; NASS publishes corn grain only where it is grown for grain (the New
    # England states and Nevada report silage alone)
    ("yield", "corn", "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    ("yield", "soybeans", "SOYBEANS - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    # NASS counted chickpeas with dry beans until 2018 (yield) and 2019 (price) and reports them
    # apart since: the two names are one series here, joined at that year
    ("price", "dry_beans", "BEANS, DRY EDIBLE, INCL CHICKPEAS - PRICE RECEIVED, MEASURED IN $ / CWT | BEANS, DRY EDIBLE, (EXCL CHICKPEAS) - PRICE RECEIVED, MEASURED IN $ / CWT", "MARKETING YEAR", "usd/cwt", 1.0),
    ("yield", "dry_beans", "BEANS, DRY EDIBLE, INCL CHICKPEAS - YIELD, MEASURED IN LB / ACRE | BEANS, DRY EDIBLE, (EXCL CHICKPEAS) - YIELD, MEASURED IN LB / ACRE", "YEAR", "cwt/acre", 0.01),
    # priced per hundredweight, kept per pound: the catalog's display unit is lb/acre
    ("price", "sunflower", "SUNFLOWER - PRICE RECEIVED, MEASURED IN $ / CWT", "MARKETING YEAR", "usd/lb", 0.01),
    ("yield", "sunflower", "SUNFLOWER - YIELD, MEASURED IN LB / ACRE", "YEAR", "lb/acre", 1.0),
    ("price", "rye", "RYE - PRICE RECEIVED, MEASURED IN $ / BU", "MARKETING YEAR", "usd/bu", 1.0),
    ("yield", "rye", "RYE - YIELD, MEASURED IN BU / ACRE", "YEAR", "bu/acre", 1.0),
    # a bushel of canola is 50 lb
    ("price", "canola", "CANOLA - PRICE RECEIVED, MEASURED IN $ / CWT", "MARKETING YEAR", "usd/bu", 0.5),
    ("yield", "canola", "CANOLA - YIELD, MEASURED IN LB / ACRE", "YEAR", "bu/acre", 0.02),
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
    for attempt in range(6):
        try:
            with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(query)}", timeout=120) as r:
                rows = json.load(r)["data"]
            break
        except urllib.error.HTTPError as error:  # 400 = no data for the query
            if error.code == 403 and attempt < 5:  # Quick Stats throttles bursts: wait, retry
                time.sleep(30 * (attempt + 1))
                continue
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
    """Fetch every series, or with `--new` only the ones the file does not hold yet (appended)."""
    key = _key()
    rows = []
    kept = []
    if "--new" in sys.argv and OUT.exists():
        with OUT.open(newline="") as handle:
            kept = list(csv.reader(handle))[1:]
        held = {(r[0], r[1]) for r in kept}
        series = [s for s in SERIES if (s[0], s[1]) not in held]
    else:
        series = SERIES
    for kind, crop, short_desc, period, unit, factor in series:
        found = {}
        for name in short_desc.split(" | "):  # a renamed series: the later name wins a shared year
            for level in ("STATE", "NATIONAL"):
                for geography, year, value in fetch(key, name, period, level):
                    found[(geography, year)] = round(value * factor, 4)
        states = {g for g, _ in found}
        years = [y for _, y in found]
        print(f"{kind} {crop}: {len(found)} values, {len(states)} geographies, "
              f"{min(years, default=0)}-{max(years, default=0)}")  # fmt: skip
        for (geography, year), value in sorted(found.items()):
            rows.append([kind, crop, geography, year, value, unit, short_desc])
    with OUT.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["kind", "crop", "geography", "year", "value", "unit", "nass_short_desc"])
        writer.writerows(kept + rows)
    print(f"wrote {OUT}: {len(kept) + len(rows)} rows")


if __name__ == "__main__":
    main()
