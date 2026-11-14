"""County corn and soybean yields for earlier years, from USDA NASS Quick Stats.

    python rule_engine/planner/scripts/fetch_county_yields.py --start 1978 --end 2014

Needs USDA_DATA_KEY in .env or the environment. Writes data/local/planner/yields/
nass_yield.parquet with the columns build_history_summaries.py reads: county_fips, crop, year,
yield_bu_acre, yield_lag1_bu_acre (latest earlier published year), yield_mean_prev3_bu_acre
(mean of the latest three earlier published years). One request per crop and state; raw
responses are cached next to the output.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "rule_engine" / "scripts"))
from fetch_nass_reference import API, _key  # noqa: E402

SERIES = {
    "CORN": "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE",
    "SOYBEANS": "SOYBEANS - YIELD, MEASURED IN BU / ACRE",
}
STATES = (
    "AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
    "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY"
).split()


def fetch(key: str, crop: str, state: str, start: int, end: int, cache: Path) -> list[dict]:
    path = cache / f"{crop}_{state}_{start}_{end}.json"
    if path.exists():
        return json.loads(path.read_text())
    query = {
        "key": key,
        "format": "JSON",
        "short_desc": SERIES[crop],
        "source_desc": "SURVEY",
        "agg_level_desc": "COUNTY",
        "freq_desc": "ANNUAL",
        "domain_desc": "TOTAL",
        "state_alpha": state,
        "year__GE": str(start),
        "year__LE": str(end),
    }
    rows: list[dict] = []
    for attempt in range(5):
        try:
            url = f"{API}?{urllib.parse.urlencode(query)}"
            with urllib.request.urlopen(url, timeout=120) as resp:
                rows = json.load(resp)["data"]
            break
        except urllib.error.HTTPError as error:
            if error.code == 400:  # nothing matches: the state has no county series
                break
            time.sleep(2**attempt)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2**attempt)
    else:
        raise SystemExit(f"NASS failed for {crop} {state}")
    keep = (
        "year",
        "state_fips_code",
        "county_code",
        "Value",
        "short_desc",
        "reference_period_desc",
    )
    rows = [{k: r.get(k) for k in keep} for r in rows]
    path.write_text(json.dumps(rows))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--start", type=int, default=1978)
    parser.add_argument("--end", type=int, default=2014)
    parser.add_argument("--out", type=Path, default=ROOT / "data/local/planner/yields")
    args = parser.parse_args()
    cache = args.out / "nass_raw"
    cache.mkdir(parents=True, exist_ok=True)
    key = _key()
    records = []
    for crop, short_desc in SERIES.items():
        for state in STATES:
            for row in fetch(key, crop, state, args.start, args.end, cache):
                text = str(row["Value"]).replace(",", "").strip()
                county = str(row["county_code"] or "")
                if row["short_desc"] != short_desc or row["reference_period_desc"] != "YEAR":
                    continue
                if not args.start <= int(row["year"]) <= args.end:
                    continue
                if county in ("", "998") or not text.replace(".", "", 1).isdigit():
                    continue  # combined counties and (D), (NA)
                records.append(
                    (str(row["state_fips_code"]).zfill(2) + county.zfill(3), crop,
                     int(row["year"]), float(text))
                )  # fmt: skip
        print(f"{crop}: {sum(r[1] == crop for r in records):,} county-years", flush=True)
    frame = pd.DataFrame(records, columns=["county_fips", "crop", "year", "yield_bu_acre"])
    frame = frame.drop_duplicates(["county_fips", "crop", "year"]).sort_values(
        ["county_fips", "crop", "year"]
    )
    group = frame.groupby(["county_fips", "crop"])["yield_bu_acre"]
    frame["yield_lag1_bu_acre"] = group.shift(1)
    frame["yield_mean_prev3_bu_acre"] = group.transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    frame.to_parquet(args.out / "nass_yield.parquet", index=False)
    print(f"wrote {len(frame):,} rows, {frame.county_fips.nunique():,} counties, "
          f"{frame.year.min()}-{frame.year.max()}")  # fmt: skip


if __name__ == "__main__":
    main()
