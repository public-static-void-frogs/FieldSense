#!/usr/bin/env python3
"""Step 7 - ENRICH the per-field DAILY dataset of yield_fields_assemble.py (--granularity day) with the tables of the ext_*.py scripts.

Reads  <dataset>/<year>/<county>.parquet  (one row per field x day, keys CSBID, county_fips, date, year, ...)
Writes <out>/<year>/<county>.parquet      (same rows, same order of columns first, new columns appended). Finished files are skipped on re-run.

Sources are looked up in --ext (the --out folder of the ext_*.py scripts); a table that is missing is simply skipped:
  gridmet_daily/ (or .parquet) + gridmet_field_cell_map.parquet    daily      join on (cell, date)             -> gridmet_pr_mm, gridmet_tmax_c, gridmet_eto_grass_mm ...
  nldas_daily.parquet        + nldas_field_cell_map.parquet        daily      join on (cell, date)             -> nldas_vsm_0_100, nldas_soilm_0_100 ...
  eddi_weekly.parquet        + eddi_field_cell_map.parquet         weekly     ASOF (latest map <= day, max age) -> eddi_04wk, eddi_map_age_days
  ssurgo_field.parquet                                             static     join on CSBID                    -> ssurgo_aws_0_150_mm, ssurgo_drainage_class ...
  irrigation_field.parquet                                         static     join on CSBID                    -> irr_<label>, irr_share_<label>
  mslsp_field_year.parquet                                         per year   join on (CSBID, year)            -> mslsp_greenup_onset_c1 ... (day of year; see note)
  gw_grid_year.parquet + gw_field_grid_map.parquet                 per year   join on (grid, year)             -> gw_depth_spring_m, gw_trend_5y_m_per_yr ...
  pumping_grid_year.parquet  (same map)                            per year   join on (grid, year)             -> pump_af_within_radius, pump_mm_equiv
  rma_col_county_year_all_crops.parquet                            county-year join on (county, year - --rma-lag) -> rma_lag1_drought_indemnity_usd ...
  nass_progress_dates.parquet                                      state-year join on (state, year)            -> nass_corn_planted_p50_doy ... (see note)
  nass_census_wide.parquet                                         county     ASOF: latest census year <= row year -> census_* , census_year_used

TIME ALIGNMENT (what a row is allowed to know on its date)
  * daily weather: same year up to and including that day (as in the dataset itself).
  * eddi: only maps dated <= the day, and not older than --eddi-max-age-days.
  * nass progress: a value (pXX_doy) is shown only from the day-of-year it was reached, earlier rows get NULL (no look-ahead).
    Use --no-nass-mask to disable.
  * rma: published after the season; the default --rma-lag 1 joins the PREVIOUS year's losses (columns rma_lag1_*). --rma-lag 0 uses the same year (an outcome, leaks the season).
  * mslsp / gw spring levels / pumping are annual values of the row's own year (mslsp lags months, wells are spring readings): for strict
    in-season models either shift them by one year (--year-lag-annual 1, applies to mslsp, gw and pumping) or drop them before the date they became known.
  * ssurgo / irrigation are static (map-year of the irrigation raster is in the column name).

Join keys: CSBID, cell ids come from the maps written by the ext scripts, county key = 5-digit state+county (state = first 2 characters of a numeric CSBID, or the
state part of a 5-digit county_fips, or --state). Existing columns of the dataset are never overwritten (a new column with the same name is skipped).
Memory: one county file at a time in DuckDB (--memory); the CSBID -> cell maps are loaded once into a disk-backed DuckDB (<out>/_enrich_tmp), restricted to the states of the dataset.
At the end a coverage table shows, per source, the share of rows that got a value: ~0 % means a key mismatch (wrong map / state / year range).

Example:
  python yield_enrich.py --dataset E:\\NASA\\yield_work\\field_daily_2025_enriched --out E:\\NASA\\yield_work\\field_daily_2025_ext --ext E:\\NASA\\ext --years 2025
Deps: pip install duckdb
"""
import argparse, re, shutil, sys, time
from pathlib import Path

FIPS_ALPHA = {"01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA",
              "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD", "25": "MA",
              "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY",
              "37": "NC", "38": "ND", "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX",
              "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY"}


def q(c):
    return '"' + str(c).replace('"', '""') + '"'


def sqlp(p):
    return str(Path(p).as_posix()).replace("'", "''")


def pq_src(p):
    p = Path(p)
    return f"read_parquet('{sqlp(p / '*.parquet')}', union_by_name=true)" if p.is_dir() else f"read_parquet('{sqlp(p)}', union_by_name=true)"


def find(ext, *names):
    for n in names:
        p = Path(ext) / n
        if p.exists() and (p.is_file() or any(p.glob("*.parquet"))):
            return p
    return None


class Enricher:
    def __init__(self, a):
        import duckdb
        self.a = a
        tmp = Path(a.out) / "_enrich_tmp"; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(tmp / "maps.duckdb"))
        self.con.execute(f"PRAGMA memory_limit='{a.memory}'"); self.con.execute(f"PRAGMA temp_directory='{sqlp(tmp / 'spill')}'")
        self.tmp = tmp
        self.src = {}                       # name -> path
        self.maps = {}                      # name -> table in the disk DB (CSBID, key)
        self.cov = {}                       # source -> [non-null rows of its first new column, rows]

    # -------------------------------------------------------------- setup
    def discover(self, files):
        a, ext, con = self.a, self.a.ext, self.con
        want = lambda n: (not a.tables) or n in a.tables
        cand = {"gridmet": find(ext, "gridmet_daily", "gridmet_daily.parquet"), "nldas": find(ext, "nldas_daily.parquet"), "eddi": find(ext, "eddi_weekly.parquet"),
                "ssurgo": find(ext, "ssurgo_field.parquet"), "irrigation": find(ext, "irrigation_field.parquet"), "mslsp": find(ext, "mslsp_field_year.parquet"),
                "gw": find(ext, "gw_grid_year.parquet"), "pumping": find(ext, "pumping_grid_year.parquet"),
                "rma": find(ext, "rma_col_county_year_all_crops.parquet"), "nass_progress": find(ext, "nass_progress_dates.parquet"),
                "census": find(ext, "nass_census_wide.parquet")}
        for k, v in cand.items():
            if v is not None and want(k): self.src[k] = v
        # states present in the dataset (numeric CSBID prefix) -> restrict the big maps
        sample = con.execute(f"SELECT CSBID FROM read_parquet('{sqlp(files[0])}') LIMIT 1").fetchone()
        numeric = bool(sample and re.match(r"^\d{2}", str(sample[0])))
        self.states = None
        if numeric:
            st = set()
            for f in files:
                st |= {r[0] for r in con.execute(f"SELECT DISTINCT left(CSBID, 2) FROM read_parquet('{sqlp(f)}')").fetchall()}
            self.states = sorted(st)
        flt = f"WHERE left(CSBID, 2) IN ({','.join(repr(s) for s in self.states)})" if self.states else ""
        for name, mapf, col in (("gridmet", "gridmet_field_cell_map.parquet", "cell_id"), ("nldas", "nldas_field_cell_map.parquet", "cell_id"),
                                ("eddi", "eddi_field_cell_map.parquet", "cell_id"), ("gw", "gw_field_grid_map.parquet", "grid_id")):
            mp = find(ext, mapf)
            if name in self.src and mp is None and name != "gw":
                print(f"  {name}: table found but {mapf} is missing -> skipped"); del self.src[name]; continue
            if name == "gw" and ("gw" in self.src or "pumping" in self.src):
                if mp is None:
                    print("  gw/pumping: gw_field_grid_map.parquet missing -> skipped"); self.src.pop("gw", None); self.src.pop("pumping", None); continue
            if name in self.src or (name == "gw" and "pumping" in self.src):
                con.execute(f"CREATE TABLE m_{name} AS SELECT CSBID, {col} AS key FROM read_parquet('{sqlp(mp)}') {flt}")
                n = con.execute(f"SELECT count(*) FROM m_{name}").fetchone()[0]
                print(f"  map {name}: {n:,} fields", flush=True); self.maps[name] = f"m_{name}"
        # NASS progress -> wide table (state, year, one column per commodity/stage/pXX)
        if "nass_progress" in self.src:
            src = f"read_parquet('{sqlp(self.src['nass_progress'])}')"
            com = ", ".join(repr(c.upper()) for c in a.nass_commodities)
            combos = con.execute(f"SELECT DISTINCT commodity, stage FROM {src} WHERE upper(commodity) IN ({com}) ORDER BY 1, 2").fetchall()
            cols = []
            for cm, stg in combos:
                for p in a.nass_pcts:
                    nm = "nass_" + re.sub(r"[^a-z0-9]+", "_", cm.lower()).strip("_") + "_" + re.sub(r"[^a-z0-9]+", "_", str(stg).lower()).strip("_") + f"_p{p}_doy"
                    cols.append(f"max(CASE WHEN commodity = {cm!r} AND stage = {stg!r} THEN p{p}_doy END) AS {nm}")
            if cols:
                con.execute(f"CREATE TABLE np_wide AS SELECT state_alpha, CAST(year AS INTEGER) AS year, {', '.join(cols)} FROM {src} "
                            f"WHERE upper(commodity) IN ({com}) AND district IS NULL GROUP BY 1, 2")
                print(f"  nass progress: {len(cols)} columns", flush=True)
            else:
                self.src.pop("nass_progress")
        print("sources:", ", ".join(sorted(self.src)) or "none", flush=True)
        if not self.src: sys.exit("no ext table found in --ext (expected names as written by the ext_*.py scripts)")

    # -------------------------------------------------------------- one file
    def run_file(self, src, dst):
        a, con = self.a, self.con
        con.execute("DROP TABLE IF EXISTS d")
        sf = a.state
        con.execute(f"""CREATE TEMP TABLE d AS SELECT *,
            CAST(date AS DATE) AS _d,
            CASE WHEN length(CAST(county_fips AS VARCHAR)) >= 5 THEN CAST(county_fips AS VARCHAR)
                 WHEN regexp_matches(CAST(CSBID AS VARCHAR), '^[0-9]{{2}}') THEN left(CAST(CSBID AS VARCHAR), 2) || lpad(CAST(county_fips AS VARCHAR), 3, '0')
                 ELSE '{str(sf).zfill(2)}' || lpad(CAST(county_fips AS VARCHAR), 3, '0') END AS _county5
            FROM read_parquet('{sqlp(src)}')""")
        con.execute("ALTER TABLE d ADD COLUMN _state VARCHAR"); con.execute("UPDATE d SET _state = left(_county5, 2)")
        n = con.execute("SELECT count(*) FROM d").fetchone()[0]
        if n == 0: return 0
        have = {r[0] for r in con.execute("DESCRIBE d").fetchall()}
        dmin, dmax = con.execute("SELECT min(_d), max(_d) FROM d").fetchone()
        con.execute("CREATE OR REPLACE TEMP TABLE ids AS SELECT DISTINCT CSBID FROM d")
        cur = ["d"]; k = [0]; first = {}

        def step(select):
            k[0] += 1; nm = f"t{k[0]}"
            con.execute(f"CREATE OR REPLACE TEMP TABLE {nm} AS {select}")
            if cur[0] != "d": con.execute(f"DROP TABLE IF EXISTS {cur[0]}")
            cur[0] = nm

        def newcols(tbl, skip):
            cols = [r[0] for r in con.execute(f"DESCRIBE {tbl}").fetchall() if r[0] not in skip and r[0] not in have]
            have.update(cols); return cols

        def cellmap(name, alias):
            con.execute(f"CREATE OR REPLACE TEMP TABLE cm_{name} AS SELECT m.CSBID AS _id, m.key AS {alias} FROM {self.maps[name]} m SEMI JOIN ids ON m.CSBID = ids.CSBID")
            lst = [r[0] for r in con.execute(f"SELECT DISTINCT {alias} FROM cm_{name} WHERE {alias} IS NOT NULL").fetchall()]
            return lst

        def inlist(vals):
            return ",".join("'" + str(v).replace("'", "''") + "'" for v in vals) or "NULL"

        # ---- daily cell sources
        for name in ("gridmet", "nldas"):
            if name not in self.src or name not in self.maps: continue
            cells = cellmap(name, f"{name}_cell_id")
            con.execute(f"CREATE OR REPLACE TEMP TABLE s_{name} AS SELECT * EXCLUDE (date), CAST(date AS DATE) AS _sd FROM {pq_src(self.src[name])} "
                        f"WHERE cell_id IN ({inlist(cells)}) AND CAST(date AS DATE) BETWEEN '{dmin}' AND '{dmax}'")
            cols = newcols(f"s_{name}", {"cell_id", "_sd"}); have.add(f"{name}_cell_id")
            if cols:
                first[name] = cols[0]
                step(f"SELECT t.*, c.{name}_cell_id, {', '.join('s.' + q(c) for c in cols)} FROM {cur[0]} t LEFT JOIN cm_{name} c ON c._id = t.CSBID "
                     f"LEFT JOIN s_{name} s ON s.cell_id = c.{name}_cell_id AND s._sd = t._d")
        # ---- EDDI (ASOF)
        if "eddi" in self.src and "eddi" in self.maps:
            cells = cellmap("eddi", "eddi_cell_id")
            con.execute(f"CREATE OR REPLACE TEMP TABLE s_eddi AS SELECT * EXCLUDE (date), CAST(date AS DATE) AS _sd FROM {pq_src(self.src['eddi'])} "
                        f"WHERE cell_id IN ({inlist(cells)}) AND CAST(date AS DATE) BETWEEN CAST('{dmin}' AS DATE) - {int(a.eddi_max_age_days)} AND '{dmax}'")
            cols = newcols("s_eddi", {"cell_id", "_sd"}); have.add("eddi_cell_id")
            if cols:
                first["eddi"] = cols[0]
                age = "date_diff('day', e._sd, t._d)"
                step(f"SELECT t.*, c.eddi_cell_id FROM {cur[0]} t LEFT JOIN cm_eddi c ON c._id = t.CSBID")
                step(f"SELECT t.*, {', '.join(f'CASE WHEN {age} <= {int(a.eddi_max_age_days)} THEN e.{q(c)} END AS {q(c)}' for c in cols)}, "
                     f"CASE WHEN {age} <= {int(a.eddi_max_age_days)} THEN {age} END AS eddi_map_age_days "
                     f"FROM {cur[0]} t ASOF LEFT JOIN s_eddi e ON t.eddi_cell_id = e.cell_id AND t._d >= e._sd")
                have.add("eddi_map_age_days")
        # ---- static per field
        yl = int(a.year_lag_annual)
        for name, join_year in (("ssurgo", False), ("irrigation", False), ("mslsp", True)):
            if name not in self.src: continue
            con.execute(f"CREATE OR REPLACE TEMP TABLE s_{name} AS SELECT s.* FROM {pq_src(self.src[name])} s SEMI JOIN ids ON s.CSBID = ids.CSBID")
            cols = newcols(f"s_{name}", {"CSBID", "year"})
            if cols:
                first[name] = cols[0]
                on = f"s.CSBID = t.CSBID" + (f" AND s.year = t.year - {yl}" if join_year else "")
                step(f"SELECT t.*, {', '.join('s.' + q(c) for c in cols)} FROM {cur[0]} t LEFT JOIN s_{name} s ON {on}")
        # ---- grid-year (groundwater, pumping)
        if "gw" in self.maps:
            cells = cellmap("gw", "gw_grid_id")
            step(f"SELECT t.*, c.gw_grid_id FROM {cur[0]} t LEFT JOIN cm_gw c ON c._id = t.CSBID"); have.add("gw_grid_id")
            for name in ("gw", "pumping"):
                if name not in self.src: continue
                con.execute(f"CREATE OR REPLACE TEMP TABLE s_{name} AS SELECT * FROM {pq_src(self.src[name])} WHERE grid_id IN ({inlist(cells)})")
                cols = newcols(f"s_{name}", {"grid_id", "year"})
                if cols:
                    first[name] = cols[0]
                    step(f"SELECT t.*, {', '.join('s.' + q(c) for c in cols)} FROM {cur[0]} t LEFT JOIN s_{name} s ON s.grid_id = t.gw_grid_id AND s.year = t.year - {yl}")
        # ---- county-year (RMA) with lag
        if "rma" in self.src:
            cols_all = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {pq_src(self.src['rma'])}").fetchall() if r[0] not in ("county_fips", "year")]
            lag = int(a.rma_lag)
            ren = {c: (f"rma_lag{lag}_" + c[4:] if (lag and c.startswith("rma_")) else c) for c in cols_all}
            use = [c for c in cols_all if ren[c] not in have]
            have.update(ren[c] for c in use)
            if use:
                first["rma"] = ren[use[0]]
                step(f"SELECT t.*, {', '.join('r.' + q(c) + ' AS ' + q(ren[c]) for c in use)} FROM {cur[0]} t LEFT JOIN {pq_src(self.src['rma'])} r "
                     f"ON r.county_fips = t._county5 AND r.year = t.year - {lag}")
        # ---- NASS progress (state-year), masked by day-of-year
        if "nass_progress" in self.src:
            cols = [r[0] for r in con.execute("DESCRIBE np_wide").fetchall() if r[0] not in ("state_alpha", "year") and r[0] not in have]
            have.update(cols)
            if cols:
                first["nass_progress"] = cols[0]
                expr = ", ".join((f"n.{q(c)} AS {q(c)}" if a.no_nass_mask else f"CASE WHEN n.{q(c)} <= dayofyear(t._d) THEN n.{q(c)} END AS {q(c)}") for c in cols)
                states = "state_alpha"
                step(f"SELECT t.*, {expr} FROM {cur[0]} t LEFT JOIN np_wide n ON n.year = t.year AND n.state_alpha = CASE t._state "
                     + " ".join(f"WHEN '{f}' THEN '{al}'" for f, al in FIPS_ALPHA.items()) + " END")
        # ---- census (ASOF on year)
        if "census" in self.src:
            con.execute(f"CREATE OR REPLACE TEMP TABLE s_census AS SELECT * FROM {pq_src(self.src['census'])} WHERE county_fips IN (SELECT DISTINCT _county5 FROM d)")
            cols = newcols("s_census", {"county_fips", "year"})
            if cols:
                first["census"] = cols[0]
                step(f"SELECT t.*, {', '.join('c.' + q(x) for x in cols)}, c.year AS census_year_used FROM {cur[0]} t "
                     f"ASOF LEFT JOIN s_census c ON t._county5 = c.county_fips AND t.year >= c.year"); have.add("census_year_used")
        # ---- write
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmpf = Path(str(dst) + ".tmp")
        con.execute(f"COPY (SELECT * EXCLUDE (_d, _county5, _state) FROM {cur[0]}) TO '{sqlp(tmpf)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        tmpf.replace(dst)
        for nm, col in first.items():
            nn = con.execute(f"SELECT count({q(col)}) FROM {cur[0]}").fetchone()[0]
            c = self.cov.setdefault(nm, [0, 0, col]); c[0] += nn; c[1] += n
        con.execute("DROP TABLE IF EXISTS d")
        return n


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", required=True, help="output folder of yield_fields_assemble.py --granularity day (<year>/<county>.parquet)")
    p.add_argument("--out", required=True, help="where the enriched copy is written (must differ from --dataset)")
    p.add_argument("--ext", required=True, help="--out folder of the ext_*.py scripts")
    p.add_argument("--years", type=int, nargs="+"); p.add_argument("--county", nargs="+", help="only these county files (e.g. 19015 or 015)")
    p.add_argument("--state", default="19", help="state FIPS used when it cannot be read from CSBID / 5-digit county_fips")
    p.add_argument("--tables", nargs="+", choices=["gridmet", "nldas", "eddi", "ssurgo", "irrigation", "mslsp", "gw", "pumping", "rma", "nass_progress", "census"],
                   help="only these sources (default: every table found)")
    p.add_argument("--eddi-max-age-days", type=int, default=14)
    p.add_argument("--rma-lag", type=int, default=1, help="years: row year - lag is joined (default 1 = previous year, no leakage)")
    p.add_argument("--year-lag-annual", type=int, default=0, help="shift mslsp / gw / pumping by this many years (1 = previous year's values)")
    p.add_argument("--nass-commodities", nargs="+", default=["CORN", "SOYBEANS"]); p.add_argument("--nass-pcts", type=int, nargs="+", default=[50], choices=[10, 50, 90])
    p.add_argument("--no-nass-mask", action="store_true", help="show the NASS progress dates on every day (look-ahead!)")
    p.add_argument("--memory", default="4GB"); p.add_argument("--force", action="store_true")
    a = p.parse_args()
    ds, out = Path(a.dataset), Path(a.out)
    if ds.resolve() == out.resolve(): sys.exit("--out must differ from --dataset")
    files = sorted(f for f in ds.glob("*/*.parquet") if f.parent.name.isdigit())
    if a.years: files = [f for f in files if int(f.parent.name) in a.years]
    if a.county:
        want = {c.zfill(5)[-5:] for c in a.county} | {c.zfill(3)[-3:] for c in a.county}
        files = [f for f in files if f.stem in want or f.stem.zfill(5)[-5:] in want]
    if not files: sys.exit(f"no <year>/<county>.parquet files in {ds} for the selection")
    out.mkdir(parents=True, exist_ok=True)
    en = Enricher(a); en.discover(files)
    t0 = time.time(); done = skipped = rows = 0
    for i, f in enumerate(files, 1):
        dst = out / f.parent.name / f.name
        if dst.exists() and not a.force:
            skipped += 1; continue
        n = en.run_file(f, dst); rows += n; done += 1
        if done % 10 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] {f.parent.name}/{f.name}: {n:,} rows ({rows:,} total, {(time.time() - t0) / 60:.1f} min)", flush=True)
    print(f"\nenriched {done} files ({rows:,} rows), skipped {skipped} existing -> {out}")
    if en.cov:
        print("\nCoverage (share of rows with a value in the source's first new column):")
        for nm, (nn, tot, col) in sorted(en.cov.items()):
            print(f"  {nm:14s} {100 * nn / max(tot, 1):6.1f} %   ({col})")
        print("0 % usually means a key mismatch: wrong map file, different state / year range, or a cell grid not covering the field.")
    shutil.rmtree(en.tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
