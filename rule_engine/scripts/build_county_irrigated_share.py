"""Irrigated share of each crop's harvested acres per county (Census of Agriculture 2022).

    python rule_engine/scripts/build_county_irrigated_share.py

Needs USDA_DATA_KEY in .env or the environment. Writes rule_engine/data/county_irrigated_share.csv
(crop, county_fips, share, harvested_acres), read as the `county.irrigated_share` fact.

A county with harvested acres and no irrigated row has no irrigated acres (share 0). A county whose
harvested or irrigated acres are withheld (D) is left out, so the fact is missing there and rules
gated on it still fire. The share is a county average, not the field's own practice.
"""

import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

from fetch_nass_reference import API, _key

OUT = Path(__file__).resolve().parents[1] / "data" / "county_irrigated_share.csv"
CENSUS_YEAR = "2022"
SERIES = {  # catalog crop id: Census short_desc stem; the irrigated series appends ", IRRIGATED"
    "corn": "CORN, GRAIN",
    "soybeans": "SOYBEANS",
    "winter_wheat": "WHEAT, WINTER",
    "spring_wheat": "WHEAT, SPRING, (EXCL DURUM)",
    "durum_wheat": "WHEAT, SPRING, DURUM",
    "sorghum": "SORGHUM, GRAIN",
    "barley": "BARLEY",
    "oats": "OATS",
    "cotton": "COTTON",
    "peanuts": "PEANUTS",
    "rice": "RICE",
}


def fetch(key: str, short_desc: str) -> dict[str, float | None]:
    """{county FIPS: harvested acres, or None when withheld}."""
    query = {
        "key": key,
        "format": "JSON",
        "source_desc": "CENSUS",
        "year": CENSUS_YEAR,
        "agg_level_desc": "COUNTY",
        "short_desc": f"{short_desc} - ACRES HARVESTED",
        "domain_desc": "TOTAL",
    }
    with urllib.request.urlopen(f"{API}?{urllib.parse.urlencode(query)}", timeout=300) as resp:
        data = json.load(resp)["data"]
    found = {}
    for r in data:
        if r["county_code"] in ("", "998"):
            continue
        value = r["Value"].replace(",", "").strip()
        acres = float(value) if value.replace(".", "").isdigit() else None
        found[r["state_fips_code"] + r["county_code"]] = acres
    return found


def main() -> None:
    key, rows = _key(), []
    for crop, series in SERIES.items():
        total = fetch(key, series)
        irrigated = fetch(key, f"{series}, IRRIGATED")
        for fips, acres in sorted(total.items()):
            wet = irrigated.get(fips, 0.0)
            if not acres or wet is None:
                continue
            rows.append(
                {
                    "crop": crop,
                    "county_fips": fips,
                    "share": round(min(wet, acres) / acres, 4),
                    "harvested_acres": round(acres),
                }
            )
        print(crop, len(rows), flush=True)
    with OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
