"""Cash rent of cropland per county and state, from the USDA NASS Cash Rents Survey (Quick Stats).

    python rule_engine/planner/scripts/fetch_cash_rent.py

Needs USDA_DATA_KEY in .env or the environment. Writes rule_engine/planner/data/cash_rent.csv:
the latest published value per geography and land type, USD per acre per year.

    geography   five-digit county FIPS, or the two-letter state
    land        non_irrigated | irrigated
"""

import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "rule_engine" / "scripts"))
from fetch_nass_reference import API, _key  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "cash_rent.csv"
SERIES = {
    "non_irrigated": "RENT, CASH, CROPLAND, NON-IRRIGATED - EXPENSE, MEASURED IN $ / ACRE",
    "irrigated": "RENT, CASH, CROPLAND, IRRIGATED - EXPENSE, MEASURED IN $ / ACRE",
}
FIRST_YEAR = 2017  # a county not published since then is left to the state value
URL = "https://quickstats.nass.usda.gov/"


def fetch(key: str, short_desc: str, level: str, year: int) -> list[dict]:
    query = {
        "key": key,
        "format": "JSON",
        "short_desc": short_desc,
        "agg_level_desc": level,
        "year": str(year),
        "domain_desc": "TOTAL",
    }
    try:
        with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(query)}", timeout=180) as resp:
            return json.load(resp).get("data", [])
    except urllib.error.HTTPError as error:
        if error.code == 400:  # Quick Stats answers 400 when nothing matches
            return []
        raise SystemExit(f"Quick Stats request failed with HTTP {error.code}") from None


def main() -> None:
    key = _key()
    latest_year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    found: dict[tuple[str, str], tuple[int, float]] = {}
    for land, short_desc in SERIES.items():
        for level in ("COUNTY", "STATE"):
            for year in range(latest_year, FIRST_YEAR - 1, -1):
                rows = fetch(key, short_desc, level, year)
                for row in rows:
                    if level == "COUNTY":
                        if not row["county_ansi"].strip():
                            continue  # "other counties" combined rows
                        geography = row["state_ansi"] + row["county_ansi"]
                    else:
                        geography = row["state_alpha"]
                    try:
                        value = float(row["Value"].replace(",", ""))
                    except ValueError:
                        continue  # (D) withheld
                    found.setdefault((geography, land), (year, value))
                print(f"{land} {level} {year}: {len(rows)} rows", flush=True)
    with OUT.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["geography", "land", "year", "usd_per_acre", "source", "url"])
        for (geography, land), (year, value) in sorted(found.items()):
            writer.writerow(
                [geography, land, year, f"{value:.2f}", "USDA NASS Cash Rents Survey", URL]
            )
    print(f"wrote {len(found):,} rows to {OUT}")


if __name__ == "__main__":
    main()
