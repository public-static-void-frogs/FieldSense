"""Pull USDA NASS Quick Stats prices received and state yields into the reference tables.

Usage (from the repo root; needs USDA_DATA_KEY in .env or the environment):

    python rule_engine/scripts/fetch_nass_reference.py

Writes rule_engine/data/nass_reference_history.csv (every annual value since START_YEAR, one row
per series and year) and refreshes the NASS rows of prices.csv and reference_yields.csv. Rows
from other sources (RMA projected prices, unverified placeholders without a NASS series) are kept.
"""

import csv
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

API = "https://quickstats.nass.usda.gov/api/api_GET/"
DATA = Path(__file__).resolve().parents[1] / "data"
ROOT = Path(__file__).resolve().parents[2]
START_YEAR = 2015
YIELD_YEARS = 5  # low/mid/high = min/mean/max of the last N final estimates
CWT_PER_BU_SORGHUM = 0.56  # 56 lb bushel

# (kind, crop id, short_desc, geography, reference period, unit, multiplier)
SERIES = [
    ("price", "corn", "CORN, GRAIN - PRICE RECEIVED, MEASURED IN $ / BU", "IA", "MARKETING YEAR", "bu", 1),
    ("price", "soybeans", "SOYBEANS - PRICE RECEIVED, MEASURED IN $ / BU", "IA", "MARKETING YEAR", "bu", 1),
    ("price", "oats", "OATS - PRICE RECEIVED, MEASURED IN $ / BU", "IA", "MARKETING YEAR", "bu", 1),
    ("price", "alfalfa", "HAY, ALFALFA - PRICE RECEIVED, MEASURED IN $ / TON", "IA", "MARKETING YEAR", "ton", 1),
    ("price", "other_hay", "HAY, (EXCL ALFALFA) - PRICE RECEIVED, MEASURED IN $ / TON", "IA", "MARKETING YEAR", "ton", 1),
    # NASS publishes no Iowa price for these; national marketing-year averages instead.
    ("price", "winter_wheat", "WHEAT, WINTER - PRICE RECEIVED, MEASURED IN $ / BU", "US", "MARKETING YEAR", "bu", 1),
    ("price", "spring_wheat", "WHEAT, SPRING, (EXCL DURUM) - PRICE RECEIVED, MEASURED IN $ / BU", "US", "MARKETING YEAR", "bu", 1),
    ("price", "rye", "RYE - PRICE RECEIVED, MEASURED IN $ / BU", "US", "MARKETING YEAR", "bu", 1),
    ("price", "sorghum", "SORGHUM, GRAIN - PRICE RECEIVED, MEASURED IN $ / CWT", "US", "MARKETING YEAR", "bu", CWT_PER_BU_SORGHUM),
    ("yield", "oats", "OATS - YIELD, MEASURED IN BU / ACRE", "IA", "YEAR", "bu/acre", 1),
    ("yield", "alfalfa", "HAY, ALFALFA - YIELD, MEASURED IN TONS / ACRE", "IA", "YEAR", "ton/acre", 1),
    ("yield", "other_hay", "HAY, (EXCL ALFALFA) - YIELD, MEASURED IN TONS / ACRE", "IA", "YEAR", "ton/acre", 1),
]  # fmt: skip
KEEP_NON_NASS_PRICE = {"corn", "soybeans"}  # RMA projected prices stay the engine's planning price


def _key() -> str:
    key = os.environ.get("USDA_DATA_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        match = re.search(r"^\s*USDA_DATA_KEY\s*=\s*(\S+)", env.read_text(), re.M)
        key = match.group(1).strip("\"'") if match else None
    if not key:
        raise SystemExit("Set USDA_DATA_KEY (free key: https://quickstats.nass.usda.gov/api)")
    return key


def _fetch(key: str, short_desc: str, geography: str, period: str) -> dict[int, float]:
    query = {
        "key": key,
        "format": "JSON",
        "short_desc": short_desc,
        "freq_desc": "ANNUAL",
        "reference_period_desc": period,
        "domain_desc": "TOTAL",
        "source_desc": "SURVEY",
        "year__GE": str(START_YEAR),
        "agg_level_desc": "STATE" if geography != "US" else "NATIONAL",
    }
    if geography != "US":
        query["state_alpha"] = geography
    try:
        with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(query)}", timeout=60) as resp:
            rows = json.load(resp)["data"]
    except urllib.error.HTTPError as error:  # 400 = no data for the query
        raise SystemExit(f"NASS returned {error.code} for {short_desc} ({geography})") from None
    values = {}
    for row in rows:
        text = row["Value"].replace(",", "").strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", text):  # skips (D), (NA), ...
            values[int(row["year"])] = float(text)
    return values


def _rewrite(path: Path, key_fields: tuple[str, ...], new_rows: list[dict], keep) -> None:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields, old = list(reader.fieldnames), list(reader)
    for name in new_rows[0]:
        if name not in fields:
            fields.append(name)
    replaced = {tuple(r[k] for k in key_fields) for r in new_rows}
    rows = [r for r in old if tuple(r[k] for k in key_fields) not in replaced or keep(r)]
    kept = {tuple(r[k] for k in key_fields) for r in rows}
    rows += [r for r in new_rows if tuple(r[k] for k in key_fields) not in kept]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, restval="", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    key, today = _key(), date.today().isoformat()
    history, prices, yields = [], [], []
    for kind, crop, short_desc, geography, period, unit, multiplier in SERIES:
        values = _fetch(key, short_desc, geography, period)
        for year in sorted(values):
            history.append(
                {
                    "kind": kind,
                    "crop": crop,
                    "geography": geography,
                    "year": year,
                    "value": round(values[year] * multiplier, 4),
                    "unit": f"usd/{unit}" if kind == "price" else unit,
                    "nass_value": values[year],
                    "nass_short_desc": short_desc,
                    "reference_period": period,
                    "fetched": today,
                }
            )
        if not values:
            continue
        where = "Iowa" if geography == "IA" else "United States"
        if kind == "price":
            year = max(values)
            prices.append(
                {
                    "crop": crop,
                    "price_usd": round(values[year] * multiplier, 2),
                    "unit": unit,
                    "source": f"USDA NASS Quick Stats: {short_desc}; {where}, marketing year {year}",
                    "as_of": today,
                    "verified": "true",
                    "level": "state" if geography == "IA" else "national",
                }
            )
        else:
            recent = [values[y] for y in sorted(values)[-YIELD_YEARS:]]
            first, last = sorted(values)[-YIELD_YEARS:][0], max(values)
            yields.append(
                {
                    "region": geography,
                    "crop": crop,
                    "level": "state",
                    "low": min(recent),
                    "mid": round(sum(recent) / len(recent), 2),
                    "high": max(recent),
                    "unit": unit,
                    "source": f"USDA NASS Quick Stats: {short_desc}; {where}, {first}-{last} "
                    "(min, mean, max)",
                    "as_of": today,
                    "verified": "true",
                }
            )

    with (DATA / "nass_reference_history.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(history[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(history)
    _rewrite(
        DATA / "prices.csv",
        ("crop",),
        prices,
        keep=lambda r: r["crop"] in KEEP_NON_NASS_PRICE and "NASS" not in r["source"],
    )
    _rewrite(DATA / "reference_yields.csv", ("region", "crop"), yields, keep=lambda r: False)
    print(f"{len(history)} history rows, {len(prices)} prices, {len(yields)} yield ranges")


if __name__ == "__main__":
    main()
