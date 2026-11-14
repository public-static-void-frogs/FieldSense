#!/usr/bin/env python3
"""Step 3 - county x year weather features from the per-cell daily tables of csb_power_weather.py / csb_imerg.py / csb_smap.py.

  python yield_weather.py power --attrs ./csb_work/attrs --cellmap ./power/field_cell_map.parquet --daily ./power/weather_daily.parquet --out ./yield_work
  python yield_weather.py imerg --attrs ./csb_work/attrs --cellmap ./imerg/field_cell_map.parquet --daily ./imerg/imerg_daily.parquet --out ./yield_work
  python yield_weather.py smap  --attrs ./csb_work/attrs --cellmap ./smap/field_cell_map.parquet  --daily ./smap/smap_daily.parquet  --out ./yield_work

Per-field datasets: add `--level cell` (no --attrs needed). It writes <src>_cell_year.parquet = one row per cell x target year with the same features
and NO weighting; yield_fields_assemble.py joins it to each field through field_cell_map (CSBID -> cell_id), so every field keeps its own cell.

Outputs in <out>: power_county_year.parquet, imerg_county_year.parquet, smap_county_year.parquet (+ power_meta.json), one row per county x TARGET year t.

How the numbers are made (all in DuckDB, out-of-core, limited by --memory; the daily tables are never loaded whole)
  1. Weights: every Iowa field (centroid cell from field_cell_map) adds its CSBACRES to (county, cell). Weight of a cell = its share of the
     county's cropland acres. Cells that hold no CSB field do not count.
  2. Per cell and window: the feature (mean, sum, count of days, longest dry spell) is computed inside the window. A cell-year with fewer than
     --min-coverage of the window's days with data is dropped for that feature (a short window never looks like a cold/dry year).
  3. County value = acre-weighted mean of the cell values (weights renormalised over the cells that have a value).
     Day counts therefore are weighted means of per-cell counts (can be fractional). `<src>_weight_covered` = share of the county's weight with data.

Windows (target year t; defaults are conventional guesses, tune them)
  POWER, IMERG : "previous season" = --season-start .. --season-end (default 05-01 .. 09-30) of year t-1.
  SMAP         : "preplant"       = --preplant-start .. --preplant-end (default 03-15 .. 04-15) of year t.
Thresholds (POWER): cold day T2M_MIN <= --cold-c (0 C), hot day T2M_MAX >= --hot-c (32 C), dry day PRECTOTCORR < --dry-mm (1 mm).
IMERG dry day: precipitation < --dry-mm; dry spell = longest run of CONSECUTIVE calendar days that are dry (a missing day ends a run).
POWER solar: SUM of daily ALLSKY_SFC_SW_DWN over the window, in (units.json unit) x days, e.g. MJ/m2 per season; unit recorded in power_meta.json.
IMERG Final has ~3.5 months latency: the season ending 30 Sep is complete from about mid January.

Needs the daily files to exist for the years you want; years without enough data give no row (the assembler leaves NaN).
Deps: pip install duckdb pandas pyarrow
"""
import argparse, datetime as dt, json, re, sys
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq


def state_cond(state, col="STATEFIPS"):
    """SQL predicate for --state: 'all', one FIPS ('19') or a comma list ('19,20')"""
    s = str(state).strip().lower()
    if s in ("all", "*", ""):
        return "TRUE"
    return f"lpad(CAST({col} AS VARCHAR), 2, '0') IN (" + ",".join(f"'{x.strip().zfill(2)}'" for x in s.split(",")) + ")"


CKEY = ("CASE WHEN length(CAST(CNTYFIPS AS VARCHAR)) <= 3 THEN lpad(CAST(STATEFIPS AS VARCHAR), 2, '0') || lpad(CAST(CNTYFIPS AS VARCHAR), 3, '0') "
        "ELSE lpad(CAST(CNTYFIPS AS VARCHAR), 5, '0') END")      # 5-digit state+county key (so counties of different states never collide)


def clean(c):
    return f"CASE WHEN isnan({c}) THEN NULL ELSE {c} END"


def expected_days(s, e):
    m1, d1 = map(int, s.split("-")); m2, d2 = map(int, e.split("-"))
    return (dt.date(2001, m2, d2) - dt.date(2001, m1, d1)).days + 1


def weights(con, a):
    if a.level == "cell":                       # no weighting: just the cells that hold fields
        con.execute(f"CREATE TABLE w AS SELECT DISTINCT cell_id FROM read_parquet('{Path(a.cellmap).as_posix()}')")
        print("cells:", con.execute("SELECT count(*) FROM w").fetchone()[0], flush=True)
        return
    if not a.attrs:
        sys.exit("--attrs is required for --level county")
    attrs = (Path(a.attrs) / "batch_*.parquet").as_posix()
    con.execute(f"""CREATE TABLE w AS
        SELECT county_fips, cell_id, acres / sum(acres) OVER (PARTITION BY county_fips) AS wt FROM (
          SELECT {CKEY.replace('CNTYFIPS', 'f.CNTYFIPS').replace('STATEFIPS', 'f.STATEFIPS')} AS county_fips, m.cell_id, sum(f.CSBACRES) AS acres
          FROM read_parquet('{attrs}') f JOIN read_parquet('{Path(a.cellmap).as_posix()}') m USING (CSBID)
          WHERE {state_cond(a.state, 'f.STATEFIPS')} GROUP BY 1, 2)""")
    n, c = con.execute("SELECT count(DISTINCT county_fips), count(DISTINCT cell_id) FROM w").fetchone()
    if not n:
        sys.exit("no fields matched between --attrs (state filter) and --cellmap; check CSBID/state")
    print(f"weights: {n} counties, {c} cells", flush=True)
    return n


def build(a, prefix, feats, win, shift, datecol, extra_cte="", extra_join="", extra_cols=(), extra_names=()):
    """feats: list of (name, sql aggregate over s, needed_col_or_None). Returns county-year DataFrame."""
    import duckdb
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{a.memory}'")
    con.execute(f"PRAGMA temp_directory='{(Path(a.out) / '_duckdb_spill').as_posix()}'")
    weights(con, a)
    daily = Path(a.daily).as_posix()
    have = set(pq.read_schema(a.daily).names)
    use = [f for f in feats if f[2] is None or f[2] in have]
    for f in feats:
        if f not in use:
            print(f"  skipping {f[0]}: column {f[2]} not in {a.daily}")
    if not use:
        sys.exit("no usable columns")
    cols = sorted({f[2] for f in use if f[2]} | {c for c in extra_cols if c in have})
    thr = max(1, int(a.min_coverage * expected_days(*win)))
    sel = ", ".join(f"{clean(c)} AS {c}" for c in cols)
    dcol = f"CAST({datecol} AS DATE)"
    fexpr = ", ".join(f"CASE WHEN count({f[2]}) >= {thr} THEN {f[1]} END AS {f[0]}" if f[2] else f"{f[1]} AS {f[0]}" for f in use)
    names = [f[0] for f in use] + list(extra_names)
    wsel = ", ".join(f"sum(w.wt * c.{n}) / nullif(sum(CASE WHEN c.{n} IS NOT NULL THEN w.wt END), 0) AS {n}" for n in names)
    q = f"""
      WITH d AS (SELECT cell_id, {dcol} AS dt, {sel} FROM read_parquet('{daily}') WHERE cell_id IN (SELECT cell_id FROM w)),
           s AS (SELECT *, year(dt) + {shift} AS sy FROM d WHERE strftime(dt, '%m-%d') BETWEEN '{win[0]}' AND '{win[1]}'),
           {extra_cte}
           c AS (SELECT s.cell_id, s.sy, {fexpr} {extra_join[0] if extra_join else ''}
                 FROM s {extra_join[1] if extra_join else ''} GROUP BY s.cell_id, s.sy {extra_join[2] if extra_join else ''})
      SELECT w.county_fips, c.sy AS year, {wsel}, sum(w.wt) AS {prefix}_weight_covered
      FROM c JOIN w USING (cell_id) GROUP BY 1, 2 ORDER BY 1, 2"""
    if a.level == "cell":
        q = q[:q.index("      SELECT w.county_fips")] + f"      SELECT c.cell_id, c.sy AS year, {', '.join(names)} FROM c ORDER BY 1, 2"""
    r = con.execute(q).df()
    r = r[r[names].notna().any(axis=1)]
    return r


def outfile(a, src):
    return Path(a.out) / f"{src}_{'cell' if a.level == 'cell' else 'county'}_year.parquet"


def cmd_power(a):
    s, e = a.season_start, a.season_end
    feats = [("power_t2m_prev_season_mean", "avg(T2M)", "T2M"),
             ("power_tmin_prev_season_mean", "avg(T2M_MIN)", "T2M_MIN"),
             ("power_tmax_prev_season_mean", "avg(T2M_MAX)", "T2M_MAX"),
             ("power_cold_days_prev_season", f"count(*) FILTER (WHERE T2M_MIN <= {a.cold_c})", "T2M_MIN"),
             ("power_hot_days_prev_season", f"count(*) FILTER (WHERE T2M_MAX >= {a.hot_c})", "T2M_MAX"),
             ("power_precip_prev_season_sum", "sum(PRECTOTCORR)", "PRECTOTCORR"),
             ("power_dry_days_prev_season", f"count(*) FILTER (WHERE PRECTOTCORR < {a.dry_mm})", "PRECTOTCORR"),
             ("power_solar_prev_season", "sum(ALLSKY_SFC_SW_DWN)", "ALLSKY_SFC_SW_DWN")]
    r = build(a, "power", feats, (s, e), 1, "date")
    fn = outfile(a, "power"); r.to_parquet(fn, compression="zstd", index=False)
    up = Path(a.units) if a.units else Path(a.daily).with_name("units.json")
    units = json.loads(up.read_text()) if up.exists() else {}
    meta = {"season": [s, e, "of year t-1"], "cold_c": a.cold_c, "hot_c": a.hot_c, "dry_mm": a.dry_mm,
            "solar_daily_unit": units.get("ALLSKY_SFC_SW_DWN", "UNKNOWN (units.json not found)"),
            "solar_feature": "sum of daily values over the window = <daily unit> x days"}
    (Path(a.out) / "power_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {fn} ({len(r)} rows); solar unit: {meta['solar_daily_unit']}")


def cmd_imerg(a):
    s, e = a.season_start, a.season_end
    feats = [("imerg_precip_prev_season_sum", "sum(precipitation)", "precipitation")]
    cte = f"""dry AS (SELECT cell_id, sy, max(run) AS spell FROM (
                    SELECT cell_id, sy, g, count(*) AS run FROM (
                      SELECT cell_id, sy, (dt - DATE '1970-01-01') - row_number() OVER (PARTITION BY cell_id, sy ORDER BY dt) AS g
                      FROM s WHERE precipitation < {a.dry_mm}) GROUP BY cell_id, sy, g) GROUP BY cell_id, sy),
              cov AS (SELECT cell_id, sy, count(precipitation) AS n FROM s GROUP BY cell_id, sy),"""
    # dry spell joins on the same cell-year; coverage guard uses the same threshold
    thr = max(1, int(a.min_coverage * expected_days(s, e)))
    ej = (f", CASE WHEN max(cov.n) >= {thr} THEN coalesce(max(dry.spell), 0) END AS imerg_dry_spell_prev_season",
          "JOIN cov ON cov.cell_id = s.cell_id AND cov.sy = s.sy LEFT JOIN dry ON dry.cell_id = s.cell_id AND dry.sy = s.sy", "")
    r = build(a, "imerg", feats, (s, e), 1, "date", cte, ej, ("precipitation",), ("imerg_dry_spell_prev_season",))
    fn = outfile(a, "imerg"); r.to_parquet(fn, compression="zstd", index=False)
    print(f"wrote {fn} ({len(r)} rows)")


def cmd_smap(a):
    have = set(pq.read_schema(a.daily).names)
    datecol = "date" if "date" in have else "timestamp"
    feats = [("smap_rootzone_preplant_mean", "avg(sm_rootzone)", "sm_rootzone"),
             ("smap_surface_preplant_mean", "avg(sm_surface)", "sm_surface"),
             ("smap_rootzone_pctl_preplant_mean", "avg(sm_rootzone_pctl)", "sm_rootzone_pctl")]
    r = build(a, "smap", feats, (a.preplant_start, a.preplant_end), 0, datecol)
    fn = outfile(a, "smap"); r.to_parquet(fn, compression="zstd", index=False)
    print(f"wrote {fn} ({len(r)} rows)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    def common(s):
        s.add_argument("--attrs"); s.add_argument("--level", choices=["county", "cell"], default="county"); s.add_argument("--cellmap", required=True); s.add_argument("--daily", required=True)
        s.add_argument("--out", required=True); s.add_argument("--state", default="all", help="all | FIPS | FIPS,FIPS (default all)"); s.add_argument("--memory", default="2GB")
        s.add_argument("--min-coverage", type=float, default=0.9, help="min share of window days with data per cell (default 0.9)")
    for name, fn in (("power", cmd_power), ("imerg", cmd_imerg), ("smap", cmd_smap)):
        s = sp.add_parser(name); common(s); s.set_defaults(fn=fn)
        if name != "smap":
            s.add_argument("--season-start", default="05-01"); s.add_argument("--season-end", default="09-30")
            s.add_argument("--dry-mm", type=float, default=1.0)
        if name == "power":
            s.add_argument("--cold-c", type=float, default=0.0); s.add_argument("--hot-c", type=float, default=32.0)
            s.add_argument("--units", help="units.json (default: next to --daily)")
        if name == "smap":
            s.add_argument("--preplant-start", default="03-15"); s.add_argument("--preplant-end", default="04-15")
    a = p.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    a.fn(a)


if __name__ == "__main__":
    main()
