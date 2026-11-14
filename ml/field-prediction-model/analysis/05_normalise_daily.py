"""Split the daily field panel (2025.zip or field_daily_2025_enriched.zip) into one table per grain.

The panel repeats every gridded value on every field row: 134.5 M field-days hold only 68 POWER cells,
1,681 IMERG cells and 1,891 SMAP cells per day. This script writes
- fields.parquet: one row per CSBID (location, area, grid cells, CSB history flags);
- county_yields.parquet: the yield columns, one row per county;
- power_cellday / imerg_cellday / smap_cellday.parquet: one row per cell and day. SMAP also gets
  converted columns (C, mm/day) next to the raw ones (K, kg m-2 s-1);
- drought_field_map.parquet: each field's covering USDM maps (valid date, class).
Every table must be constant on its grain, and the panel rebuilt from them must equal the input in every
column of every row; the script stops otherwise. The four *_share_* columns are empty and are dropped.

Drought in the panel is the last map that covered the field, used from its valid date + 2 days, so a
field that left drought keeps its old class. Current class: drought_dm if drought_map_age_days <= 8, else
-1 (no D0+ polygon). See research/data_sources/fields/field_daily_2025.md.

Usage: python 05_normalise_daily.py --daily path/to/unpacked/2025 --out path/to/field_daily_2025
"""
import argparse
import glob
from pathlib import Path

import duckdb

FIELD = ["county_fips", "county_name", "centroid_lon", "centroid_lat", "area_acres", "power_cell_id",
         "imerg_cell_id", "smap_cell_id", "field_cdl_prev1", "field_cdl_prev2", "field_corn_prev1",
         "field_soy_prev1", "field_corn_to_soy_prev2", "field_soy_to_corn_prev2",
         "min_lon", "min_lat", "max_lon", "max_lat"]       # synthetic squares, only in 2025.zip
SHARES = ["corn_share_prev1", "soy_share_prev1", "corn_to_soy_share_prev2", "soy_to_corn_share_prev2"]
DROUGHT = ["drought_dm", "drought_valid_date", "drought_map_age_days"]
MAP_LAG_DAYS = 2
SMAP_CONVERTED = """smap_surface_temp - 273.15 AS smap_surface_temp_c,
       smap_soil_temp_layer1 - 273.15 AS smap_soil_temp_layer1_c,
       smap_land_evapotranspiration_flux * 86400 AS smap_et_mm,
       smap_overland_runoff_flux * 86400 AS smap_runoff_mm,
       smap_baseflow_flux * 86400 AS smap_baseflow_mm"""


def constant_on(con, key, cols):
    """Collapse the panel to `key`, failing if any column takes two values within one key."""
    k = ", ".join(key)
    check = ", ".join(f"count(DISTINCT {c}) + max(({c} IS NULL)::INT) * (count({c}) > 0)::INT AS {c}" for c in cols)
    worst = con.execute(f"SELECT {', '.join(f'max({c})' for c in cols)} FROM (SELECT {check} FROM p GROUP BY {k})").fetchone()
    bad = {c: v for c, v in zip(cols, worst) if v > 1}
    assert not bad, f"not constant on {key}: {bad}"
    return f"SELECT {k}, {', '.join(f'any_value({c}) AS {c}' for c in cols)} FROM p GROUP BY {k} ORDER BY {k}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--daily", required=True, help="folder with one Parquet file per county")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit = '6GB'; SET preserve_insertion_order = false")
    con.execute(f"CREATE VIEW p AS SELECT * FROM read_parquet('{args.daily}/*.parquet', union_by_name = true)")
    cols = [r[0] for r in con.execute("DESCRIBE p").fetchall()]
    power = [c for c in cols if c.startswith("power_") and c != "power_cell_id"]
    imerg = [c for c in cols if c.startswith("imerg_") and c != "imerg_cell_id"]
    smap = [c for c in cols if c.startswith("smap_") and c != "smap_cell_id"]
    yields = [c for c in cols if c.startswith("yield_")]
    field = [c for c in FIELD if c in cols]
    known = {"CSBID", "date", "year", "doy", *field, *SHARES, *DROUGHT, *power, *imerg, *smap, *yields}
    assert set(cols) <= known, f"unexpected columns: {set(cols) - known}"

    n, filled = con.execute(f"SELECT count(*), {' + '.join(f'count({c})' for c in SHARES if c in cols) or '0'} FROM p").fetchone()
    assert filled == 0, "share columns are no longer empty: keep them"
    assert con.execute("SELECT count(*) FROM p WHERE year <> year(date) OR doy <> dayofyear(date)").fetchone()[0] == 0
    print(f"{n:,} field-days, {len(cols)} columns")

    tables = {"fields": constant_on(con, ["CSBID"], field),
              "county_yields": constant_on(con, ["county_fips", "year"], yields),
              "power_cellday": constant_on(con, ["power_cell_id", "date"], power),
              "imerg_cellday": constant_on(con, ["imerg_cell_id", "date"], imerg)}
    if smap:
        tables["smap_cellday"] = f"SELECT *, {SMAP_CONVERTED} FROM ({constant_on(con, ['smap_cell_id', 'date'], smap)})"
    # one row per field and covering map; the panel never shows a map before valid date + MAP_LAG_DAYS
    lag = con.execute("SELECT min(drought_map_age_days) FROM p").fetchone()[0]
    assert lag == MAP_LAG_DAYS, f"map lag is {lag} days, not {MAP_LAG_DAYS}"
    tables["drought_field_map"] = constant_on(con, ["CSBID", "drought_valid_date"], ["drought_dm"]).replace(
        "FROM p GROUP BY", "FROM p WHERE drought_valid_date IS NOT NULL GROUP BY")
    for name, sql in tables.items():
        path = out / f"{name}.parquet"
        con.execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
        rows = con.execute(f"SELECT count(*) FROM '{path}'").fetchone()[0]
        print(f"{name:18s} {rows:>12,} rows {path.stat().st_size / 1e6:8.1f} MB")

    # rebuild every county file from the tables and compare all columns
    for name in tables:
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM '{out / name}.parquet'")
    smap_join = f"LEFT JOIN smap_cellday s ON s.smap_cell_id = f.smap_cell_id AND s.date = k.date" if smap else ""
    rebuilt = f"""
        SELECT k.CSBID, k.date, year(k.date) AS year, dayofyear(k.date) AS doy,
               {', '.join(f'f.{c}' for c in field)}, {', '.join(f'y.{c}' for c in yields)},
               {', '.join(f'w.{c}' for c in power)}, {', '.join(f'i.{c}' for c in imerg)},
               {', '.join(f's.{c}' for c in smap) + ',' if smap else ''}
               d.drought_dm, d.drought_valid_date, (k.date - d.drought_valid_date) AS drought_map_age_days
        FROM keys k JOIN fields f USING (CSBID)
        LEFT JOIN county_yields y ON y.county_fips = f.county_fips AND y.year = year(k.date)
        LEFT JOIN power_cellday w ON w.power_cell_id = f.power_cell_id AND w.date = k.date
        LEFT JOIN imerg_cellday i ON i.imerg_cell_id = f.imerg_cell_id AND i.date = k.date
        {smap_join}
        ASOF LEFT JOIN (SELECT *, drought_valid_date + {MAP_LAG_DAYS} AS available FROM drought_field_map) d
               ON d.CSBID = k.CSBID AND k.date >= d.available"""
    compare = [c for c in cols if c not in SHARES and c not in ("CSBID", "date")]
    total, checked = {c: 0 for c in compare}, 0
    for f in sorted(glob.glob(f"{args.daily}/*.parquet")):
        con.execute(f"CREATE OR REPLACE TEMP VIEW orig AS SELECT * FROM read_parquet('{f}')")
        con.execute("CREATE OR REPLACE TEMP VIEW keys AS SELECT CSBID, date FROM orig")
        r = con.execute(f"SELECT count(*), count(o.CSBID), {', '.join(f'sum((o.{c} IS DISTINCT FROM b.{c})::INT)' for c in compare)} "
                        f"FROM ({rebuilt}) b LEFT JOIN orig o USING (CSBID, date)").fetchone()
        assert r[0] == r[1], f"{f}: rebuilt rows without a match"
        checked += r[0]
        for c, v in zip(compare, r[2:]):
            total[c] += v
    bad = {c: v for c, v in total.items() if v}
    assert checked == n and not bad, f"rebuild differs: {bad}, {checked:,} of {n:,} rows"
    print(f"rebuilt {checked:,} field-days from the tables: all {len(compare)} columns identical")


if __name__ == "__main__":
    main()
