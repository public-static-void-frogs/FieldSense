#!/usr/bin/env python3
"""Add SMAP L4 columns to the daily dataset written by yield_enrich.py (or yield_fields_assemble.py --granularity day).

Reads   <dataset>/<year>/<county>.parquet      one row per field x day (keys CSBID, date; year, county_fips ...)
        --smap-daily  smap_daily.parquet        cell_id, date, n_files, sm_rootzone, leaf_area_index, snow_mass     (csb_smap.py merge, daily)
        --cellmap     field_cell_map.parquet    CSBID, cell_id                                                       (csb_smap.py plan)
Writes  <out>/<year>/<county>.parquet           same rows and column order, SMAP columns added; finished files are skipped on re-run.

Columns added (name = "smap_" + SMAP column):
  smap_cell_id            9 km SMAP EASE-Grid cell the field was assigned to
  smap_sm_rootzone        root-zone soil moisture (0-100 cm), m3/m3, daily mean of the 8 three-hourly L4 files
  smap_leaf_area_index    leaf area index, m2/m2, daily mean
  smap_snow_mass          snow mass (snow water equivalent), kg/m2, daily mean
  (n_files is not added; --with-n-files adds smap_n_files, the number of 3-houclrly files behind the daily mean, 8 = complete day)
Join: (cell, calendar date) = the same day, no look-ahead. Days outside the SMAP record (before 2015-03-31) or without a file get NULL.
All fields of one 9 km cell get the same values (model grid, not a field measurement).

Existing smap_* columns (e.g. from the 2023-2025 SMAP of yield_fields_assemble.py): by default they are REPLACED by the new values, so the whole
history comes from one file and is consistent; they keep their position in the table. --keep-existing keeps the old values and only fills the NULLs
(do not mix sources if the old file was built differently).

At the end a coverage table shows the share of rows with a value per column and per year: ~0 % = key mismatch (wrong cell map / date range).

Example:
  python yield_enrich_smap.py --dataset E:\\NASA\\yield_work\\field_daily_2025_ext --out E:\\NASA\\yield_work\\field_daily_2025_smap \\
         --smap-daily E:\\NASA\\smap\\smap_daily.parquet --cellmap E:\\NASA\\smap\\field_cell_map.parquet
Deps: pip install duckdb
Tested on synthetic files only.
"""
import argparse, re, shutil, sys, time
from pathlib import Path

SKIP = {"cell_id", "date", "timestamp", "n_files", "elevation_m"}


def q(c):
    return '"' + str(c).replace('"', '""') + '"'


def sqlp(p):
    return str(Path(p).as_posix()).replace("'", "''")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", required=True, help="folder with <year>/<county>.parquet (output of yield_enrich.py)")
    p.add_argument("--out", required=True, help="enriched copy (must differ from --dataset)")
    p.add_argument("--smap-daily", required=True); p.add_argument("--cellmap", required=True)
    p.add_argument("--years", type=int, nargs="+"); p.add_argument("--county", nargs="+", help="5-digit county file names to process")
    p.add_argument("--columns", nargs="+", help="SMAP columns to add (default: all except n_files)")
    p.add_argument("--with-n-files", action="store_true"); p.add_argument("--keep-existing", action="store_true")
    p.add_argument("--memory", default="8GB"); p.add_argument("--force", action="store_true", help="redo files that already exist in --out")
    a = p.parse_args()
    import duckdb
    ds, out = Path(a.dataset).resolve(), Path(a.out).resolve()
    if ds == out:
        sys.exit("--out must differ from --dataset")
    files = sorted(ds.glob("*/*.parquet"))
    if a.years:
        files = [f for f in files if f.parent.name in {str(y) for y in a.years}]
    if a.county:
        files = [f for f in files if f.stem in {str(c).zfill(5) for c in a.county}]
    if not files:
        sys.exit(f"no <year>/<county>.parquet under {ds}")
    tmp = out / "_smap_tmp"; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(tmp / "w.duckdb"))
    con.execute(f"PRAGMA memory_limit='{a.memory}'"); con.execute(f"PRAGMA temp_directory='{sqlp(tmp / 'spill')}'")
    sm = f"read_parquet('{sqlp(a.smap_daily)}')"
    names = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {sm}").fetchall()]
    for need in ("cell_id", "date"):
        if need not in names:
            sys.exit(f"{a.smap_daily} has no '{need}' column (found {names}); use the daily file, not smap_3hourly")
    cols = a.columns or [c for c in names if c not in SKIP]
    if a.with_n_files and "n_files" in names:
        cols.append("n_files")
    bad = [c for c in cols if c not in names]
    if bad:
        sys.exit(f"columns not in smap_daily: {bad}; available: {names}")
    new = {c: f"smap_{c}" for c in cols}
    mp = f"read_parquet('{sqlp(a.cellmap)}')"
    mn = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {mp}").fetchall()]
    if "CSBID" not in mn or "cell_id" not in mn:
        sys.exit(f"--cellmap needs CSBID and cell_id columns, found {mn}")
    print(f"{len(files)} files; adding {', '.join(['smap_cell_id'] + list(new.values()))}", flush=True)
    cov, t0 = {}, time.time()
    for i, f in enumerate(files, 1):
        dst = out / f.parent.name / f.name
        if dst.exists() and not a.force:
            continue
        have = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{sqlp(f)}')").fetchall()]
        if "CSBID" not in have or "date" not in have:
            print(f"  skip {f}: no CSBID/date", file=sys.stderr); continue
        con.execute(f"CREATE OR REPLACE TEMP TABLE d AS SELECT *, CAST(date AS DATE) AS _d FROM read_parquet('{sqlp(f)}')")
        con.execute(f"CREATE OR REPLACE TEMP TABLE cm AS SELECT m.CSBID AS _id, m.cell_id AS _cell FROM {mp} m SEMI JOIN (SELECT DISTINCT CSBID FROM d) x ON m.CSBID = x.CSBID")
        dmin, dmax = con.execute("SELECT min(_d), max(_d) FROM d").fetchone()
        con.execute(f"CREATE OR REPLACE TEMP TABLE s AS SELECT cell_id AS _cell, CAST(date AS DATE) AS _sd, {', '.join(q(c) + ' AS ' + q('n_' + c) for c in cols)} "
                    f"FROM {sm} WHERE cell_id IN (SELECT DISTINCT _cell FROM cm) AND CAST(date AS DATE) BETWEEN '{dmin}' AND '{dmax}'")
        sel = []
        for c in have:
            if c == "smap_cell_id":
                sel.append("c._cell AS smap_cell_id" if not a.keep_existing else "COALESCE(t.smap_cell_id, c._cell) AS smap_cell_id")
            elif c in new.values():
                src = "s." + q("n_" + next(k for k, v in new.items() if v == c))
                sel.append(f"COALESCE(t.{q(c)}, {src}) AS {q(c)}" if a.keep_existing else f"{src} AS {q(c)}")
            elif c != "_d":
                sel.append("t." + q(c))
        if "smap_cell_id" not in have:
            sel.append("c._cell AS smap_cell_id")
        for c, nm in new.items():
            if nm not in have:
                sel.append(f"s.{q('n_' + c)} AS {q(nm)}")
        dst.parent.mkdir(parents=True, exist_ok=True); tf = Path(str(dst) + ".tmp")
        con.execute(f"COPY (SELECT {', '.join(sel)} FROM (SELECT *, row_number() OVER () AS _rn FROM d) t LEFT JOIN cm c ON c._id = t.CSBID "
                    f"LEFT JOIN s ON s._cell = c._cell AND s._sd = t._d ORDER BY t._rn) TO '{sqlp(tf)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        tf.replace(dst)
        first = next(iter(new.values()))
        n, nn = con.execute(f"SELECT count(*), count({q(first)}) FROM read_parquet('{sqlp(dst)}')").fetchone()
        c = cov.setdefault(f.parent.name, [0, 0]); c[0] += nn; c[1] += n
        if i % 50 == 0 or i == len(files):
            print(f"  {i}/{len(files)} files ({time.time() - t0:.0f}s)", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"coverage of {next(iter(new.values()))} (rows with a value / rows):")
    for y in sorted(cov):
        print(f"  {y}: {cov[y][0]:,} / {cov[y][1]:,} = {100 * cov[y][0] / max(cov[y][1], 1):.1f}%")
    if cov and all(v[0] == 0 for v in cov.values()):
        print("WARNING: 0 % coverage - the cell map does not match the dataset's CSBID or the dates are outside smap_daily", file=sys.stderr)


if __name__ == "__main__":
    main()
