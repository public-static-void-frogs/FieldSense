"""A field sample that covers every weather cell: one CSB field per gridMET cell and county.

    python rule_engine/planner/scripts/sample_weather_cells.py \
        --fields data/local/usa_sample_v2/all_fields.csv \
        --keep data/local/usa_sample_v2/fields.csv --out data/local/usa_sample_v3

gridMET weather is the same for every field inside one 1/24 degree cell, and county yields and
losses are the same inside one county. So one sampled field per (cell, county) gives every CSB
field a sampled field with the same weather and county record; `weather_cells.parquet` is the
index a reader uses to find it. Within a cell the field is drawn at random (fixed hash order),
fields of 10 acres or more first. Fields listed in --keep stay in the sample.

Writes <out>/fields.csv (with the cell `ix`, `iy` and a build `chunk` of whole counties) and
<out>/weather_cells.parquet (ix, iy, county_fips, CSBID).
"""

import argparse
from pathlib import Path

import duckdb

# edges of the gridMET grid: cell centres start at 124.7667 W, 49.4 N, 1/24 degree apart
WEST_EDGE, NORTH_EDGE, CELLS_PER_DEGREE = -124.7875, 49.4208, 24
TYPES = "{'source_id': 'VARCHAR', 'state_fips': 'VARCHAR', 'county_fips': 'VARCHAR'}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fields", required=True, help="every CSB field: id, county, position")
    parser.add_argument("--keep", help="fields.csv of an earlier sample to keep")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--chunk-size", type=int, default=30000)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    keep = (
        f"SELECT CSBID FROM read_csv('{args.keep}', types={{'CSBID': 'VARCHAR'}})"
        if args.keep
        else "SELECT NULL::VARCHAR AS CSBID WHERE false"
    )
    con.execute(f"""
        CREATE TABLE picked AS
        WITH f AS (
            SELECT *, floor((longitude - {WEST_EDGE}) * {CELLS_PER_DEGREE})::INTEGER AS ix,
                   floor(({NORTH_EDGE} - latitude) * {CELLS_PER_DEGREE})::INTEGER AS iy
            FROM read_csv('{args.fields}', types={TYPES})
        ), ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY ix, iy, state_fips, county_fips
                ORDER BY (acres >= 10) DESC, hash(source_id), source_id) AS place
            FROM f
        )
        SELECT source_id AS CSBID, lpad(state_fips, 2, '0') AS STATEFIPS,
               lpad(county_fips, 3, '0') AS CNTYFIPS, county AS CNTY,
               round(acres, 2) AS CSBACRES, longitude AS centroid_lon, latitude AS centroid_lat,
               ix, iy, place = 1 AS cell_field
        FROM ranked WHERE place = 1 OR source_id IN ({keep})
    """)
    con.execute(f"""
        CREATE TABLE chunked AS
        WITH county AS (
            SELECT STATEFIPS, CNTYFIPS, count(*) AS n FROM picked GROUP BY ALL
        ), placed AS (
            SELECT *, (sum(n) OVER (ORDER BY STATEFIPS, CNTYFIPS) - n) // {args.chunk_size} AS chunk
            FROM county
        )
        SELECT p.*, placed.chunk::INTEGER AS chunk
        FROM picked p JOIN placed USING (STATEFIPS, CNTYFIPS)
    """)
    con.execute(f"""
        COPY (SELECT * EXCLUDE (cell_field) FROM chunked ORDER BY CSBID)
        TO '{args.out}/fields.csv' (HEADER)
    """)
    con.execute(f"""
        COPY (SELECT ix, iy, STATEFIPS || CNTYFIPS AS county_fips, CSBID
              FROM chunked WHERE cell_field ORDER BY iy, ix)
        TO '{args.out}/weather_cells.parquet' (FORMAT PARQUET)
    """)
    fields, cells, counties, chunks = con.execute(
        "SELECT count(*), count(*) FILTER (cell_field), count(DISTINCT STATEFIPS || CNTYFIPS), "
        "count(DISTINCT chunk) FROM chunked"
    ).fetchone()
    print(f"{fields:,} fields ({cells:,} cell fields) in {counties:,} counties, {chunks} chunks")


if __name__ == "__main__":
    main()
