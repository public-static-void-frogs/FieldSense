"""Crop history, soil and engine field records for a field sample drawn by sample_fields.py.

    python rule_engine/planner/scripts/build_sample.py --root data/local/usa_sample_v2 \
        --cdl data/local/usa_sample/cdl_history_all.parquet \
        --soil data/local/usa_sample_v2/soil_candidates.parquet

Reads <root>/fields.csv. Writes, in the layout of the first national sample (data/usa_sample):
<root>/cdl_history.parquet, <root>/soil.parquet and <root>/fields.jsonl. CDL labels are
satellite estimates, not farmer declarations; soil values are SSURGO map-unit estimates.
"""

import argparse
import json
from pathlib import Path

import duckdb

ACRE_TO_HA = 0.404686
TYPES = "types={'CSBID': 'VARCHAR', 'STATEFIPS': 'VARCHAR', 'CNTYFIPS': 'VARCHAR'}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--cdl", required=True)
    parser.add_argument("--soil", required=True)
    args = parser.parse_args()
    root = args.root
    con = duckdb.connect()
    con.execute(f"CREATE VIEW f AS SELECT * FROM read_csv('{root}/fields.csv', {TYPES})")
    con.execute(f"""
        COPY (SELECT c.*, f.CSBACRES, f.STATEFIPS, f.CNTYFIPS
              FROM read_parquet('{args.cdl}') c JOIN f USING (CSBID) ORDER BY CSBID)
        TO '{root}/cdl_history.parquet' (FORMAT PARQUET)
    """)
    con.execute(f"""
        COPY (SELECT s.* FROM read_parquet('{args.soil}') s JOIN f USING (CSBID) ORDER BY CSBID)
        TO '{root}/soil.parquet' (FORMAT PARQUET)
    """)
    described = con.execute(f"DESCRIBE SELECT * FROM '{root}/cdl_history.parquet'").fetchall()
    cdl = [row[0] for row in described if row[0].startswith("CDL")]
    soil_keys = [
        row[0]
        for row in con.execute(f"DESCRIBE SELECT * FROM '{root}/soil.parquet'").fetchall()
        if row[0] != "CSBID"
    ]
    rows = con.execute(f"""
        SELECT f.CSBID, lpad(f.STATEFIPS, 2, '0') AS state_fips,
               lpad(f.STATEFIPS, 2, '0') || lpad(f.CNTYFIPS, 3, '0') AS county_fips,
               f.CNTY, f.CSBACRES, f.centroid_lon, f.centroid_lat,
               {", ".join("c." + name for name in cdl)},
               {", ".join("s." + key + " AS soil_" + key for key in soil_keys)}
        FROM f LEFT JOIN '{root}/cdl_history.parquet' c USING (CSBID)
        LEFT JOIN '{root}/soil.parquet' s USING (CSBID)
        ORDER BY f.CSBID
    """).fetchdf()
    with_soil = 0
    with (root / "fields.jsonl").open("w") as handle:
        for row in rows.to_dict("records"):

            def known(value) -> bool:
                return value is not None and value == value

            props = {"CSBID": row["CSBID"], "CSBACRES": row["CSBACRES"], "CNTY": row["CNTY"]}
            props.update({name: int(row[name]) for name in cdl if known(row[name])})
            soil = {k: row[f"soil_{k}"] for k in soil_keys if known(row[f"soil_{k}"])}
            record = {
                "id": row["CSBID"],
                "sourceId": row["CSBID"],
                "stateFips": row["state_fips"],
                "countyFips": row["county_fips"],
                "county": row["CNTY"],
                "longitude": row["centroid_lon"],
                "latitude": row["centroid_lat"],
                "area": round(float(row["CSBACRES"]) * ACRE_TO_HA, 3),  # hectares
                "sourceYear": 2025,
                "sourceProperties": props,
            }
            if len(soil) > 1:  # more than the source label
                record["soil"] = soil
                with_soil += 1
            handle.write(json.dumps(record) + "\n")
    print(f"fields.jsonl: {len(rows):,} records, {with_soil:,} with soil")


if __name__ == "__main__":
    main()
