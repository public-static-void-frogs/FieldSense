"""Counties where the crops that need a processor nearby are grown: planner/data/processor_counties.csv.

Sugarbeets and sugarcane are sold only to a nearby factory or mill, under a contract (often
with cooperative shares per acre); potatoes need contracts, storage and specialised equipment.
The planner plans such a crop only in a county listed here, or on a field whose own history
shows it. A county is listed when the crop holds at least --min-share of the sampled CSB acres
there, averaged over 2021-2025 (CDL labels: a satellite estimate).

    python rule_engine/planner/scripts/build_processor_counties.py --root data/local/usa_sample_v3
"""

import argparse
import csv
from pathlib import Path

import duckdb

OUT = Path(__file__).resolve().parents[1] / "data" / "processor_counties.csv"
CROPS = {41: "sugarbeets", 45: "sugarcane", 43: "potatoes"}
YEARS = range(2021, 2026)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--min-share", type=float, default=0.005)
    args = parser.parse_args()
    root = args.root.resolve()
    seasons = " UNION ALL ".join(
        f"SELECT CSBID, CDL{y} AS cdl FROM read_parquet('{root}/cdl_history_all.parquet')"
        for y in YEARS
    )
    codes = ", ".join(str(c) for c in CROPS)
    rows = duckdb.sql(
        f"""
        WITH f AS (SELECT CSBID, STATEFIPS || CNTYFIPS AS county, CSBACRES::DOUBLE AS acres
                   FROM read_csv('{root}/fields.csv', all_varchar=true)),
             s AS (SELECT county, cdl, acres FROM ({seasons}) JOIN f USING (CSBID)),
             total AS (SELECT county, sum(acres) AS acres FROM s GROUP BY county)
        SELECT s.cdl, s.county, sum(s.acres) / any_value(total.acres) AS share
        FROM s JOIN total USING (county) WHERE s.cdl IN ({codes})
        GROUP BY s.cdl, s.county HAVING share >= {args.min_share}
        ORDER BY s.cdl, s.county
        """
    ).fetchall()
    source = (
        f"CDL {YEARS[0]}-{YEARS[-1]} on the sampled CSB fields ({root.name}): share of the county's"
        f" sampled acres >= {args.min_share}"
    )
    with OUT.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["crop", "county_fips", "acre_share", "source"])
        for code, county, share in rows:
            writer.writerow([CROPS[code], county, round(share, 4), source])
    print(f"{len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
