#!/usr/bin/env python3
"""Step 6b - PER-FIELD dataset: one row per CSB field x candidate crop x year, field IDs and coordinates preserved.

  python yield_fields_assemble.py --attrs ./csb_work/attrs --work ./yield_work --out ./yield_work/field_dataset --min-year 2020 \\
      --cellmap-power ./power/field_cell_map.parquet --cellmap-imerg ./imerg/field_cell_map.parquet --cellmap-smap ./smap/field_cell_map.parquet

IMPORTANT about the label. NASS publishes yield only per COUNTY. `yield_bu_acre` (and the baseline and yield lags) is the county value, repeated
on every field of that county. It is not a field yield. Consequences: all fields of a county-year share the same Y; validate with a split by YEAR
(and, to test spatial transfer, by county); never split fields of one county-year between train and test; weight or aggregate when scoring.

Inputs (small per-county/cell tables + per-field tables from the earlier steps; missing optional ones are skipped)
  <work>/nass_yield.parquet                        yield_nass.py
  <work>/csb_county_year.parquet                   yield_csb_features.py (county crop shares, copied onto each field of the county)
  <work>/{power,imerg,smap}_cell_year.parquet      yield_weather.py <src> --level cell      + the matching field_cell_map.parquet (CSBID -> cell_id)
  <work>/drought_field_year/year=<t>.parquet       yield_drought.py --level field
  <work>/soil_field/part_*.parquet                 yield_soil.py sample --level field
  --attrs  csb_pipeline.py ingest output (CSBID, CNTYFIPS, CSBACRES, centroid_lon/lat, CDL<yyyy>)
  --bounds (optional) csb_bounds output dir: adds min_lon, min_lat, max_lon, max_lat (an ESTIMATED box, see csb_bounds_columns.md)

Output: <out>/year=<t>/part.parquet (Hive-style, one folder per year; read the whole dataset with pandas/pyarrow/DuckDB:
        duckdb: SELECT * FROM read_parquet('field_dataset/*/*.parquet', hive_partitioning=true)). Built one year at a time in DuckDB,
        so memory stays bounded by --memory. Add --csv-sample N to also write a small CSV of N rows for inspection.

Columns
  ids/coords : CSBID, county_fips, county_name, centroid_lon, centroid_lat, area_acres, [min_lon, min_lat, max_lon, max_lat],
               power_cell_id, imerg_cell_id, smap_cell_id (the grid cell each field was assigned to)
  keys/label : crop (CORN | SOYBEANS), year, yield_bu_acre (COUNTY value), baseline_prev3_mean_bu_acre, yield_lag1_bu_acre,
               yield_mean_prev3_bu_acre, yield_prev3_count               (county-level, see above)
  field crop history (from the field's own CDL; null when that year is unknown/0):
               field_cdl_prev1, field_cdl_prev2 (CDL codes of t-1, t-2), field_corn_prev1, field_soy_prev1 (0/1),
               field_corn_to_soy_prev2, field_soy_to_corn_prev2 (0/1), field_prev1_is_candidate_crop (1 = the candidate crop was grown in t-1)
  county crop shares : corn_share_prev1, soy_share_prev1, corn_to_soy_share_prev2, soy_to_corn_share_prev2   (county level)
  weather    : power_* , imerg_* , smap_*  (value of the field's cell; same names as in the county dataset)
  drought    : drought_dm (0-4 = D0-D4 at the field's centroid, null = none), drought_valid_date
  soil       : soil_clay_0_5_mean ... soil_cec_0_5_mean (250 m pixel at the field centroid)

DAILY MODE (--granularity day): one row per field x calendar day
  python yield_fields_assemble.py --granularity day --attrs ./csb_work/attrs --work ./yield_work --out ./yield_work/field_daily \
      --years 2021 2022 2023 2024 2025 --start 04-01 --end 10-31 \
      --power-daily ./power/weather_daily.parquet --cellmap-power ./power/field_cell_map.parquet \
      --imerg-daily ./imerg/imerg_daily.parquet   --cellmap-imerg ./imerg/field_cell_map.parquet \
      --smap-daily  ./smap/smap_daily.parquet     --cellmap-smap  ./smap/field_cell_map.parquet \
      --drought-weekly ./drought/ia_weekly.parquet [--county 19015 ...] [--layout long] [--bounds ./csb_bounds]
  Output <out>/<year>/<county_fips>.parquet (plain folders, so pandas.read_parquet(out) works; DuckDB: read_parquet('field_daily/*/*.parquet')).
  Built county by county and year by year from small temp tables, so memory stays low; finished files are skipped on re-run. Mind the size:
  fields x days x years rows (1M fields x 214 days x 5 years ~ 1 billion rows) - restrict --county / --years / --start/--end first.
  Columns: keys CSBID, county_fips, county_name, centroid_lon/lat, area_acres, (bbox), <src>_cell_id, date, year, doy;
    daily weather of the field's cell with the source's own names prefixed: power_T2M, power_PRECTOTCORR ..., imerg_precipitation ..., smap_sm_rootzone ...
    drought_dm / drought_valid_date / drought_map_age_days = the latest USDM map whose release_date_est <= that day (ASOF join; null dm = no drought);
    field_cdl_prev1/2 + rotation flags (from the field's own CDL), county crop shares, soil_* (static), county yields:
      --layout wide (default): yield_bu_acre_corn, yield_lag1_bu_acre_corn, yield_mean_prev3_bu_acre_corn, yield_prev3_count_corn and the same for soybeans
      --layout long: crop, yield_bu_acre, baseline_prev3_mean_bu_acre, yield_lag1_bu_acre, ..., field_prev1_is_candidate_crop (rows x number of crops)
  The yield is still ONE annual COUNTY number repeated on every day of every field of the county (see the warning above).
  Unlike the yearly table (previous-season weather only), the daily rows contain the weather of the same year up to and including that day: it is fine for
  in-season / nowcast models, but a "before planting" model must only use rows of days before planting. Filter by date accordingly.
  Missing daily values stay null (no interpolation); a weather source that is not given is simply absent.

Deps: pip install duckdb pandas pyarrow
"""
import argparse, re, sys
from pathlib import Path
import pyarrow.parquet as pq

# ======================================================================== daily mode

def state_cond(state, col="STATEFIPS"):
    """SQL predicate for --state: 'all', one FIPS ('19') or a comma list ('19,20')"""
    s = str(state).strip().lower()
    if s in ("all", "*", ""):
        return "TRUE"
    return f"lpad(CAST({col} AS VARCHAR), 2, '0') IN (" + ",".join(f"'{x.strip().zfill(2)}'" for x in s.split(",")) + ")"


def run_daily(a):
    """One row per CSB field x calendar day. Built county by county and year by year (DuckDB, small temp tables), written as
    <out>/<year>/<county_fips>.parquet; finished files are skipped on re-run."""
    import duckdb, datetime as dt
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    w = Path(a.work)
    st = str(a.state)
    atts = (Path(a.attrs) / "batch_*.parquet").as_posix()
    first = sorted(Path(a.attrs).glob("batch_*.parquet"))
    if not first: sys.exit("no batches in --attrs")
    sch = pq.read_schema(first[0]).names
    cdl = {int(c[3:]) for c in sch if re.fullmatch(r"CDL\d{4}", c)}
    if not (w / "nass_yield.parquet").exists(): sys.exit("nass_yield.parquet missing in --work")
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{a.memory}'")
    con.execute(f"PRAGMA temp_directory='{(out / '_duckdb_spill').as_posix()}'")
    con.execute(f"CREATE VIEW nass AS SELECT * FROM read_parquet('{(w / 'nass_yield.parquet').as_posix()}')")
    crops = [c.upper() for c in a.crops]
    nyears = [r[0] for r in con.execute(f"SELECT DISTINCT year FROM nass WHERE crop IN ({','.join(repr(c) for c in crops)}) ORDER BY 1").fetchall()]
    years = a.years or [y for y in nyears if (not a.min_year or y >= a.min_year) and (not a.max_year or y <= a.max_year)]
    if not years: sys.exit("no years to build (check --years/--min-year/--max-year)")
    ckey = ("CASE WHEN length(CAST(CNTYFIPS AS VARCHAR)) <= 3 THEN lpad(CAST(STATEFIPS AS VARCHAR), 2, '0') || lpad(CAST(CNTYFIPS AS VARCHAR), 3, '0') "
            "ELSE lpad(CAST(CNTYFIPS AS VARCHAR), 5, '0') END")
    counties = [r[0] for r in con.execute(
        f"SELECT DISTINCT {ckey} FROM read_parquet('{atts}') WHERE {state_cond(a.state)} ORDER BY 1").fetchall()]
    attr_counties = list(counties)
    if a.county: counties = [c for c in counties if c in {str(x).zfill(5) for x in a.county}]
    nc = {r[0] for r in con.execute("SELECT DISTINCT county_fips FROM nass").fetchall()}
    counties = [c for c in counties if c in nc]
    if not counties:
        raw = con.execute(f"SELECT DISTINCT STATEFIPS, CNTYFIPS FROM read_parquet('{atts}') LIMIT 5").fetchall()
        sys.exit(f"no county present in both --attrs and nass_yield.parquet.\n  attrs (state {st}): {len(attr_counties)} counties, e.g. {attr_counties[:5]}; raw (STATEFIPS, CNTYFIPS) examples: {raw}\n"
                 f"  nass_yield.parquet: {len(nc)} counties, e.g. {sorted(nc)[:5]}"
                 + ("\n  note: --county filter is applied too" if a.county else ""))

    # daily sources: (prefix, daily parquet, cellmap)
    srcs = []
    for key, daily_f, cm in (("power", a.power_daily, a.cellmap_power), ("imerg", a.imerg_daily, a.cellmap_imerg), ("smap", a.smap_daily, a.cellmap_smap)):
        if daily_f and cm:
            names = pq.read_schema(daily_f).names
            if "date" not in names:
                print(f"  (skip {key}: no 'date' column in {daily_f}; for 3-hourly SMAP use the daily file)"); continue
            cols = [c for c in names if c not in ("cell_id", "date", "timestamp", "elevation_m", "n_files")]
            srcs.append((key, daily_f, cm, cols))
        else:
            print(f"  (skip {key}: need --{key}-daily and --cellmap-{key})")
    csbf = w / "csb_county_year.parquet"
    soil = w / "soil_field"; has_soil = soil.exists() and any(soil.glob("part_*.parquet"))
    drf = a.drought_weekly
    if drf and "release_date_est" not in pq.read_schema(drf).names: sys.exit("--drought-weekly needs release_date_est (csb_drought.py weekly output)")
    bsel = ""
    if a.bounds:
        con.execute(f"CREATE VIEW bnd AS SELECT CSBID, min_lon, min_lat, max_lon, max_lat FROM read_parquet('{(Path(a.bounds) / 'batch_*.parquet').as_posix()}')")

    ms, ds_ = a.start, a.end
    def span(t): return f"DATE '{t}-{ms}'", f"DATE '{t}-{ds_}'"
    lo_all, hi_all = f"DATE '{min(years)}-{ms}'", f"DATE '{max(years)}-{ds_}'"
    ndays = (dt.date(2001, int(ds_[:2]), int(ds_[3:])) - dt.date(2001, int(ms[:2]), int(ms[3:]))).days + 1
    nfields = con.execute(f"SELECT count(*) FROM read_parquet('{atts}') WHERE {state_cond(a.state)}"
                          + (f" AND CNTYFIPS IN ({','.join(repr(c) for c in counties)})" if a.county else "")).fetchone()[0]
    est = nfields * ndays * len(years) * (len(crops) if a.layout == "long" else 1)
    print(f"estimated rows: {nfields:,} fields x {ndays} days x {len(years)} years" + (f" x {len(crops)} crops" if a.layout == "long" else "") + f" = {est:,} (about {est * 150 / 1e9:.0f} GB on disk)")
    if est > a.max_rows and not a.force:
        sys.exit(f"{est:,} rows is more than --max-rows ({a.max_rows:,}). Narrow --county / --years / --start/--end, or add --force.")
    print(f"daily mode: {len(counties)} counties x {len(years)} years {years[0]}-{years[-1]}, window {ms}..{ds_} (~{ndays} days), layout {a.layout}, "
          f"sources: {[s[0] for s in srcs] + (['drought'] if drf else []) + (['soil'] if has_soil else [])}", flush=True)
    short = {c: c.lower() for c in crops}
    tot = 0
    for ci, cty in enumerate(counties, 1):
        todo = [t for t in years if not (out / str(t) / f"{cty}.parquet").exists()]
        if not todo:
            continue
        con.execute("DROP TABLE IF EXISTS fc"); con.execute("DROP TABLE IF EXISTS fields_c")
        con.execute(f"""CREATE TEMP TABLE fields_c AS SELECT f.* REPLACE (CASE WHEN length(CAST(CNTYFIPS AS VARCHAR)) <= 3
              THEN lpad(CAST(STATEFIPS AS VARCHAR), 2, '0') || lpad(CAST(CNTYFIPS AS VARCHAR), 3, '0') ELSE lpad(CAST(CNTYFIPS AS VARCHAR), 5, '0') END AS CNTYFIPS)
              FROM read_parquet('{atts}') f WHERE {state_cond(a.state)} AND {ckey} = '{cty}'""")
        nf = con.execute("SELECT count(*) FROM fields_c").fetchone()[0]
        if nf == 0: continue
        joins_fc, selfc = [], ["f.CSBID"]
        for i, (key, df_, cm, cols) in enumerate(srcs):
            joins_fc.append(f"LEFT JOIN read_parquet('{Path(cm).as_posix()}') m{i} ON m{i}.CSBID = f.CSBID"); selfc.append(f"m{i}.cell_id AS {key}_cell_id")
        con.execute(f"CREATE TEMP TABLE fc AS SELECT {', '.join(selfc)} FROM fields_c f {' '.join(joins_fc)}")
        sel_src, join_src = [], []
        for i, (key, df_, cm, cols) in enumerate(srcs):
            con.execute(f"DROP TABLE IF EXISTS d_{key}")
            cl = ", ".join(f'CASE WHEN isnan("{c}") THEN NULL ELSE "{c}" END AS "{c}"' for c in cols)
            con.execute(f"""CREATE TEMP TABLE d_{key} AS SELECT cell_id, CAST(date AS DATE) AS d, {cl} FROM read_parquet('{Path(df_).as_posix()}')
                WHERE cell_id IN (SELECT DISTINCT {key}_cell_id FROM fc) AND CAST(date AS DATE) BETWEEN {lo_all} AND {hi_all}""")
            join_src.append(f"LEFT JOIN d_{key} s{i} ON s{i}.cell_id = fc.{key}_cell_id AND s{i}.d = dd.d")
            sel_src += [f's{i}."{c}" AS {key}_{c}' for c in cols]
        if drf:
            con.execute("DROP TABLE IF EXISTS d_dr")
            con.execute(f"""CREATE TEMP TABLE d_dr AS SELECT CSBID, CAST(release_date_est AS DATE) AS rel, CAST(valid_date AS DATE) AS valid, dm
                FROM read_parquet('{Path(drf).as_posix()}') WHERE CSBID IN (SELECT CSBID FROM fields_c)""")
        if has_soil:
            con.execute("DROP TABLE IF EXISTS d_soil")
            con.execute(f"CREATE TEMP TABLE d_soil AS SELECT * FROM read_parquet('{(soil / 'part_*.parquet').as_posix()}') WHERE CSBID IN (SELECT CSBID FROM fields_c)")
        for t in todo:
            lo, hi = span(t)
            d1 = f"f.CDL{t - 1}" if (t - 1) in cdl else "NULL::SMALLINT"
            d2 = f"f.CDL{t - 2}" if (t - 2) in cdl else "NULL::SMALLINT"
            sel = ["f.CSBID", "f.CNTYFIPS AS county_fips", "f.centroid_lon", "f.centroid_lat", "f.CSBACRES AS area_acres"]
            if a.bounds: sel.append("b.min_lon, b.min_lat, b.max_lon, b.max_lat")
            sel += [f"fc.{k}_cell_id" for k, *_ in srcs]
            sel += ["dd.d AS date", f"{t} AS year", "dayofyear(dd.d) AS doy"]
            joins = []
            if a.layout == "wide":
                sel += [f"n.yield_bu_acre_{short[c]}, n.yield_lag1_bu_acre_{short[c]}, n.yield_mean_prev3_bu_acre_{short[c]}, n.yield_prev3_count_{short[c]}" for c in crops]
                agg = ", ".join(f"max(CASE WHEN crop = '{c}' THEN yield_bu_acre END) AS yield_bu_acre_{short[c]}, "
                                f"max(CASE WHEN crop = '{c}' THEN yield_lag1_bu_acre END) AS yield_lag1_bu_acre_{short[c]}, "
                                f"max(CASE WHEN crop = '{c}' THEN yield_mean_prev3_bu_acre END) AS yield_mean_prev3_bu_acre_{short[c]}, "
                                f"max(CASE WHEN crop = '{c}' THEN yield_prev3_count END) AS yield_prev3_count_{short[c]}" for c in crops)
                joins.append(f"LEFT JOIN (SELECT county_fips, any_value(county_name) AS county_name, {agg} FROM nass WHERE year = {t} GROUP BY 1) n ON n.county_fips = f.CNTYFIPS")
                sel.insert(2, "n.county_name")
            else:
                lab = "" if a.keep_unlabeled else "AND target_available"
                crs_ = ",".join(repr(c) for c in crops)
                joins.append(f"JOIN (SELECT * FROM nass WHERE year = {t} AND crop IN ({crs_}) {lab}) n ON n.county_fips = f.CNTYFIPS")
                sel.insert(2, "n.county_name")
                sel += ["n.crop", "n.yield_bu_acre", "n.yield_mean_prev3_bu_acre AS baseline_prev3_mean_bu_acre", "n.yield_lag1_bu_acre", "n.yield_mean_prev3_bu_acre", "n.yield_prev3_count",
                        f"CASE WHEN {d1} > 0 THEN ({d1} = CASE n.crop WHEN 'CORN' THEN 1 ELSE 5 END)::TINYINT END AS field_prev1_is_candidate_crop"]
            sel += [f"{d1}::SMALLINT AS field_cdl_prev1", f"{d2}::SMALLINT AS field_cdl_prev2",
                    f"CASE WHEN {d1} > 0 THEN ({d1} = 1)::TINYINT END AS field_corn_prev1", f"CASE WHEN {d1} > 0 THEN ({d1} = 5)::TINYINT END AS field_soy_prev1",
                    f"CASE WHEN {d1} > 0 AND {d2} > 0 THEN ({d2} = 1 AND {d1} = 5)::TINYINT END AS field_corn_to_soy_prev2",
                    f"CASE WHEN {d1} > 0 AND {d2} > 0 THEN ({d2} = 5 AND {d1} = 1)::TINYINT END AS field_soy_to_corn_prev2"]
            if csbf.exists():
                joins.append(f"LEFT JOIN read_parquet('{csbf.as_posix()}') cs ON cs.county_fips = f.CNTYFIPS AND cs.year = {t}")
                sel.append("cs.* EXCLUDE (county_fips, year, known_acres_prev1, known_acres_prev2)")
            sel += sel_src
            if drf:
                sel += ["dr.dm AS drought_dm", "dr.valid AS drought_valid_date", "date_diff('day', dr.valid, dd.d) AS drought_map_age_days"]
            if has_soil:
                joins.append("LEFT JOIN d_soil so ON so.CSBID = f.CSBID"); sel.append("so.* EXCLUDE (CSBID)")
            if a.bounds: joins.append("LEFT JOIN bnd b ON b.CSBID = f.CSBID")
            asof = "ASOF LEFT JOIN d_dr dr ON dr.CSBID = f.CSBID AND dd.d >= dr.rel" if drf else ""
            q = f"""COPY (
                SELECT {', '.join(sel)}
                FROM fields_c f
                CROSS JOIN (SELECT CAST(unnest(generate_series({lo}, {hi}, INTERVAL 1 DAY)) AS DATE) AS d) dd
                JOIN fc ON fc.CSBID = f.CSBID
                {' '.join(join_src)} {' '.join(joins)} {asof}
            ) TO '{(out / str(t) / (cty + '.parquet.tmp')).as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)"""
            (out / str(t)).mkdir(exist_ok=True)
            con.execute(q)
            (out / str(t) / (cty + ".parquet.tmp")).replace(out / str(t) / f"{cty}.parquet")
            n = con.execute(f"SELECT count(*) FROM read_parquet('{(out / str(t) / (cty + '.parquet')).as_posix()}')").fetchone()[0]
            tot += n
            if n == 0: (out / str(t) / f"{cty}.parquet").unlink()
        print(f"  county {cty} ({ci}/{len(counties)}): {nf:,} fields, years {todo[0]}-{todo[-1]}; {tot:,} rows so far", flush=True)
    allp = (out / "*" / "*.parquet").as_posix()
    nfiles = len(list(out.glob("*/*.parquet")))
    if not nfiles: sys.exit("no rows written (check --attrs/--work/--years and the sources above)")
    meta = con.execute(f"SELECT count(*) AS rows, count(DISTINCT CSBID) AS fields, min(date) AS d0, max(date) AS d1 FROM read_parquet('{allp}', union_by_name=true)").fetchone()
    print(f"wrote {out}: {nfiles} files, {meta[0]:,} rows, {meta[1]:,} fields, dates {meta[2]} .. {meta[3]}")
    smp = con.execute(f"SELECT * FROM read_parquet('{allp}', union_by_name=true) USING SAMPLE 200000 ROWS").df()
    nl = (smp.isna().mean() * 100).round(1)
    print("null % in a 200k-row sample (columns with nulls):\n", nl[nl > 0].to_string() if (nl > 0).any() else "  none")
    import shutil; shutil.rmtree(out / "_duckdb_spill", ignore_errors=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--attrs", required=True); p.add_argument("--work", required=True); p.add_argument("--out", required=True)
    p.add_argument("--state", default="all", help="all | FIPS | FIPS,FIPS (default all)"); p.add_argument("--county"); p.add_argument("--bounds")
    p.add_argument("--cellmap-power"); p.add_argument("--cellmap-imerg"); p.add_argument("--cellmap-smap")
    p.add_argument("--min-year", type=int); p.add_argument("--max-year", type=int)
    p.add_argument("--crops", nargs="+", default=["CORN", "SOYBEANS"])
    p.add_argument("--keep-unlabeled", action="store_true", help="also write rows without a published county yield (e.g. the year to predict)")
    p.add_argument("--memory", default="4GB"); p.add_argument("--csv-sample", type=int, default=0)
    p.add_argument("--granularity", choices=["year", "day"], default="year", help="year = one row per field x crop x year (default); day = one row per field x day")
    p.add_argument("--years", type=int, nargs="*", help="day mode: years to build (default: all years in nass_yield.parquet)")
    p.add_argument("--start", default="01-01", help="day mode: first day of every year, MM-DD"); p.add_argument("--end", default="12-31", help="day mode: last day, MM-DD")
    p.add_argument("--layout", choices=["wide", "long"], default="wide", help="day mode: wide = yields of all crops as columns (default), long = one row per field x crop x day")
    p.add_argument("--max-rows", type=int, default=1_000_000_000, help="day mode: refuse to start above this estimated row count (unless --force)")
    p.add_argument("--force", action="store_true")
    p.add_argument("--power-daily"); p.add_argument("--imerg-daily"); p.add_argument("--smap-daily"); p.add_argument("--drought-weekly")
    a = p.parse_args()
    if a.granularity == "day":
        return run_daily(a)
    import duckdb
    w, out = Path(a.work), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{a.memory}'")
    con.execute(f"PRAGMA temp_directory='{(out / '_duckdb_spill').as_posix()}'")
    atts = (Path(a.attrs) / "batch_*.parquet").as_posix()
    first = sorted(Path(a.attrs).glob("batch_*.parquet"))
    if not first:
        sys.exit("no batches in --attrs")
    cdl = {int(c[3:]) for c in pq.read_schema(first[0]).names if re.fullmatch(r"CDL\d{4}", c)}
    if not (w / "nass_yield.parquet").exists():
        sys.exit("nass_yield.parquet missing in --work")
    con.execute(f"CREATE VIEW nass AS SELECT * FROM read_parquet('{(w / 'nass_yield.parquet').as_posix()}')")
    years = [r[0] for r in con.execute("SELECT DISTINCT year FROM nass ORDER BY 1").fetchall()]
    years = [y for y in years if (not a.min_year or y >= a.min_year) and (not a.max_year or y <= a.max_year)]

    srcs = []                                   # (alias, prefix, cellmap, cell_year file)
    for key, pre in (("power", "power"), ("imerg", "imerg"), ("smap", "smap")):
        cm, cy = getattr(a, f"cellmap_{key}"), w / f"{key}_cell_year.parquet"
        if cm and cy.exists():
            srcs.append((key, cm, cy))
        else:
            print(f"  (skip {key}: need --cellmap-{key} and {cy.name})")
    csbf = w / "csb_county_year.parquet"
    soil = w / "soil_field"
    has_soil = soil.exists() and any(soil.glob("part_*.parquet"))
    if not has_soil: print("  (skip soil: soil_field/ not found)")
    if not csbf.exists(): print("  (skip county crop shares: csb_county_year.parquet not found)")

    bsel = bjoin = ""
    if a.bounds:
        con.execute(f"CREATE VIEW bnd AS SELECT CSBID, min_lon, min_lat, max_lon, max_lat FROM read_parquet('{(Path(a.bounds) / 'batch_*.parquet').as_posix()}')")
        bsel, bjoin = ", b.min_lon, b.min_lat, b.max_lon, b.max_lat", "LEFT JOIN bnd b ON b.CSBID = f.CSBID"
    crops = ",".join("'" + c + "'" for c in a.crops)
    lab = "" if a.keep_unlabeled else "AND target_available"
    cnty = f"AND CNTYFIPS = '{str(a.county).zfill(5)}'" if a.county else ""
    st = str(a.state)
    nf, nc = con.execute(f"SELECT count(*), count(DISTINCT CNTYFIPS) FROM read_parquet('{atts}') WHERE {state_cond(a.state)}").fetchone()
    lbl = con.execute(f"SELECT count(*), count(DISTINCT county_fips), min(year), max(year) FROM nass WHERE target_available AND crop IN ({crops})").fetchone()
    print(f"diagnostics: fields with STATEFIPS={st}: {nf:,} in {nc} counties; NASS labeled rows: {lbl[0]:,} in {lbl[1]} counties, years {lbl[2]}-{lbl[3]}; years to build: {years}")
    if nf == 0:
        sam = con.execute(f"SELECT DISTINCT STATEFIPS FROM read_parquet('{atts}') LIMIT 10").fetchall()
        sys.exit(f"no fields for --state {a.state}. STATEFIPS values in --attrs include: {[x[0] for x in sam]}")
    ov = con.execute(f"""SELECT count(DISTINCT n.county_fips) FROM nass n JOIN (SELECT DISTINCT CASE WHEN length(CAST(CNTYFIPS AS VARCHAR)) <= 3
        THEN lpad(CAST(STATEFIPS AS VARCHAR), 2, '0') || lpad(CAST(CNTYFIPS AS VARCHAR), 3, '0') ELSE lpad(CAST(CNTYFIPS AS VARCHAR), 5, '0') END AS k
        FROM read_parquet('{atts}') WHERE {state_cond(a.state)}) f ON f.k = n.county_fips""").fetchone()[0]
    print(f"counties present in both CSB attrs and NASS: {ov}")
    if ov == 0:
        ex1 = [r[0] for r in con.execute(f"SELECT DISTINCT CNTYFIPS FROM read_parquet('{atts}') WHERE {state_cond(a.state)} LIMIT 5").fetchall()]
        ex2 = [r[0] for r in con.execute("SELECT DISTINCT county_fips FROM nass LIMIT 5").fetchall()]
        sys.exit(f"no county matches. CNTYFIPS in attrs e.g. {ex1}; county_fips in nass_yield.parquet e.g. {ex2}")
    if not years:
        sys.exit("no years to build (check --min-year/--max-year against nass_yield.parquet)")
    done = 0
    for t in years:
        d1 = f"f.CDL{t - 1}" if (t - 1) in cdl else "NULL::SMALLINT"
        d2 = f"f.CDL{t - 2}" if (t - 2) in cdl else "NULL::SMALLINT"
        cols = [f"f.CSBID", "f.CNTYFIPS AS county_fips", "n.county_name", "f.centroid_lon", "f.centroid_lat", "f.CSBACRES AS area_acres"]
        joins = []
        sel = [c for c in cols]
        if bsel: sel.append(bsel.lstrip(", "))
        for i, (key, cm, cy) in enumerate(srcs):
            sel.append(f"m{i}.cell_id AS {key}_cell_id")
        sel += ["n.crop", f"{t} AS year", "n.yield_bu_acre", "n.yield_mean_prev3_bu_acre AS baseline_prev3_mean_bu_acre", "n.yield_lag1_bu_acre",
                "n.yield_mean_prev3_bu_acre", "n.yield_prev3_count",
                f"{d1}::SMALLINT AS field_cdl_prev1", f"{d2}::SMALLINT AS field_cdl_prev2",
                f"CASE WHEN {d1} > 0 THEN ({d1} = 1)::TINYINT END AS field_corn_prev1",
                f"CASE WHEN {d1} > 0 THEN ({d1} = 5)::TINYINT END AS field_soy_prev1",
                f"CASE WHEN {d1} > 0 AND {d2} > 0 THEN ({d2} = 1 AND {d1} = 5)::TINYINT END AS field_corn_to_soy_prev2",
                f"CASE WHEN {d1} > 0 AND {d2} > 0 THEN ({d2} = 5 AND {d1} = 1)::TINYINT END AS field_soy_to_corn_prev2",
                f"CASE WHEN {d1} > 0 THEN ({d1} = CASE n.crop WHEN 'CORN' THEN 1 ELSE 5 END)::TINYINT END AS field_prev1_is_candidate_crop"]
        if csbf.exists():
            joins.append(f"LEFT JOIN read_parquet('{csbf.as_posix()}') cs ON cs.county_fips = f.CNTYFIPS AND cs.year = {t}")
            sel.append("cs.* EXCLUDE (county_fips, year, known_acres_prev1, known_acres_prev2)")
        for i, (key, cm, cy) in enumerate(srcs):
            joins.append(f"LEFT JOIN read_parquet('{Path(cm).as_posix()}') m{i} ON m{i}.CSBID = f.CSBID")
            joins.append(f"LEFT JOIN read_parquet('{cy.as_posix()}') c{i} ON c{i}.cell_id = m{i}.cell_id AND c{i}.year = {t}")
            sel.append(f"c{i}.* EXCLUDE (cell_id, year)")
        dfile = w / "drought_field_year" / f"year={t}.parquet"
        if dfile.exists():
            joins.append(f"LEFT JOIN read_parquet('{dfile.as_posix()}') dr ON dr.CSBID = f.CSBID")
            sel.append("dr.drought_dm, dr.drought_valid_date")
        elif (w / "drought_field_year").exists():                    # no usable map for this year: keep the columns, all null
            sel.append("NULL::TINYINT AS drought_dm, NULL::DATE AS drought_valid_date")
        if has_soil:
            joins.append(f"LEFT JOIN read_parquet('{(soil / 'part_*.parquet').as_posix()}') so ON so.CSBID = f.CSBID")
            sel.append("so.* EXCLUDE (CSBID)")
        q = f"""COPY (
            SELECT {', '.join(sel)}
            FROM (SELECT * REPLACE (CASE WHEN length(CAST(CNTYFIPS AS VARCHAR)) <= 3 THEN lpad(CAST(STATEFIPS AS VARCHAR), 2, '0') || lpad(CAST(CNTYFIPS AS VARCHAR), 3, '0')
                                         ELSE lpad(CAST(CNTYFIPS AS VARCHAR), 5, '0') END AS CNTYFIPS)
                  FROM read_parquet('{atts}') WHERE {state_cond(a.state)} {cnty}) f
            JOIN (SELECT * FROM nass WHERE year = {t} AND crop IN ({crops}) {lab}) n ON n.county_fips = f.CNTYFIPS
            {bjoin} {' '.join(joins)}
        ) TO '{(out / f'year={t}' / 'part.parquet.tmp').as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)"""
        (out / f"year={t}").mkdir(exist_ok=True)
        for old in (out / f"year={t}").glob("*"): old.unlink()          # rerun replaces the year
        con.execute(q)
        (out / f"year={t}" / "part.parquet.tmp").replace(out / f"year={t}" / "part.parquet")
        n = con.execute(f"SELECT count(*) FROM read_parquet('{(out / f'year={t}').as_posix()}/*.parquet')").fetchone()[0]
        done += n
        print(f"  year {t}: {n:,} rows", flush=True)
        if n == 0:
            (out / f"year={t}").rmdir() if not any((out / f"year={t}").iterdir()) else None
    if not done:
        sys.exit("no rows written")
    allp = (out / "year=*" / "*.parquet").as_posix()
    cols_ = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{allp}', union_by_name=true)").fetchall()]
    nl = con.execute("SELECT " + ", ".join(f'round(100 * avg(("{c}" IS NULL)::INT), 1) AS "{c}"' for c in cols_) + f" FROM read_parquet('{allp}', union_by_name=true)").df().iloc[0]
    print(f"wrote {out}: {done:,} rows x {len(cols_)} columns, {con.execute(f'SELECT count(DISTINCT CSBID) FROM read_parquet({chr(39)}{allp}{chr(39)}, union_by_name=true)').fetchone()[0]:,} fields")
    print("null % (columns with nulls):\n", nl[nl > 0].to_string() if (nl > 0).any() else "  none")
    if a.csv_sample:
        con.execute(f"COPY (SELECT * FROM read_parquet('{allp}', union_by_name=true) USING SAMPLE {int(a.csv_sample)} ROWS) TO '{(out / 'sample.csv').as_posix()}' (HEADER)")
        print("sample:", out / "sample.csv")
    import shutil; shutil.rmtree(out / "_duckdb_spill", ignore_errors=True)


if __name__ == "__main__":
    main()