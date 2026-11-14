#!/usr/bin/env python3
"""Collect the calibration inputs of m3_window_forecaster.py for a range of years (default 2015 .. last full year).

Needs ext_nass_extra.py and ext_gridded.py in the same folder (their request / download / NetCDF code is re-used).

  nass     weekly NASS Crop Progress (state level) -> ONE ROW PER STATE-YEAR with the same column names the dataset uses:
               nass_corn_planted_p50_doy, nass_corn_silking_p50_doy, nass_corn_mature_p50_doy, nass_corn_harvested_p50_doy,
               nass_soybeans_planted_p50_doy, nass_soybeans_blooming_p50_doy, nass_soybeans_dropping_leaves_p50_doy,
               nass_soybeans_harvested_p50_doy  (+ all other stages and p10 / p90)
           day of year (raw, as in the dataset) at which the stage reached 10 / 50 / 90 %, linear interpolation between weekly reports.
           Differences to `ext_nass_extra.py progress` output:
             * corn SILAGE (and sweet corn etc.) series are dropped - otherwise "harvested" mixes grain and silage;
             * one wide row per state-year with M3's column names, FIPS state code in `state`;
             * a quality report: missing stages per year and stage order violations.
  gridmet  daily gridMET reference ET (pet), tmmx, tmmn averaged over a SAMPLE of points (the POWER cells in --power),
           not over every field cell: M3 only needs one ETo scale factor (Hargreaves vs gridMET), so a few dozen points are enough
           and the all-fields extraction of ext_gridded.py (billions of values) is not needed.
           NOTE: gridMET annual NetCDF files are large (per variable and year); the default is the last 5 full years.

Outputs (in --out)
  nass_stage_dates.parquet      state, state_alpha, year, nass_<commodity>_<stage>_p<10|50|90>_doy
  nass_quality_report.csv       one line per state-year x problem
  gridmet_eto_calib.parquet     date, eto, tn, tx, lat, n_points   (daily, mean over the sample points)
  raw/                          weekly NASS table as downloaded

Examples
  python m3_collect_calibration.py nass    --state IA --years 2015-2025 --out ./calib          # needs NASS_API_KEY
  python m3_collect_calibration.py gridmet --power ./power_1981 --years 2021-2025 --out ./calib --max-points 30
  python m3_collect_calibration.py all     --state IA --power ./power_1981 --out ./calib
Then
  python m3_window_forecaster.py all ... --history power_history_1981_2025.parquet \
         --nass-table calib/nass_stage_dates.parquet --gridmet-table calib/gridmet_eto_calib.parquet

Endpoints / API parameters are those of your two scripts (not tested against the live servers from the author's environment).
Deps: pip install pandas pyarrow numpy requests xarray netCDF4
"""
import argparse
import datetime as dt
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ext_nass_extra as NX  # noqa: E402
import ext_gridded as GX     # noqa: E402

FIPS = dict(AL="01", AK="02", AZ="04", AR="05", CA="06", CO="08", CT="09", DE="10", FL="12", GA="13", HI="15", ID="16", IL="17",
            IN="18", IA="19", KS="20", KY="21", LA="22", ME="23", MD="24", MA="25", MI="26", MN="27", MS="28", MO="29", MT="30",
            NE="31", NV="32", NH="33", NJ="34", NM="35", NY="36", NC="37", ND="38", OH="39", OK="40", OR="41", PA="42", RI="44",
            SC="45", SD="46", TN="47", TX="48", UT="49", VT="50", VA="51", WA="53", WV="54", WI="55", WY="56")
EXCLUDE_SERIES = "SILAGE|SWEET|FRESH|SEED|PREVIOUS|AVG"          # keep the grain / oilseed progress series only
ORDER = {"corn": ["planted", "emerged", "silking", "dough", "dented", "mature", "harvested"],
         "soybeans": ["planted", "emerged", "blooming", "setting_pods", "dropping_leaves", "harvested"]}


def log(*a):
    print(dt.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def parse_years(tokens):
    ys = []
    for t in tokens:
        if "-" in str(t):
            a, b = str(t).split("-")
            ys += list(range(int(a), int(b) + 1))
        else:
            ys.append(int(t))
    return sorted(set(ys))


# ------------------------------------------------------------------ NASS
def weekly_to_stage_dates(w: pd.DataFrame):
    """weekly progress rows -> (wide state-year table, list of quality findings)"""
    w = w.copy()
    unit = w["unit"].astype(str)
    w = w[unit.str.startswith("PCT ") & ~unit.str.contains("EXCELLENT|GOOD|FAIR|POOR|VERY", regex=True)]
    n0 = len(w)
    w = w[~w["short_desc"].astype(str).str.upper().str.contains(EXCLUDE_SERIES, regex=True)]
    findings = []
    if len(w) < n0:
        findings.append(dict(problem="dropped_non_grain_series", detail=f"{n0 - len(w)} weekly rows (silage / sweet corn / averages)"))
    w = w.dropna(subset=["value", "doy"]).drop_duplicates(["state_alpha", "year", "commodity", "unit", "short_desc", "week_ending"], keep="last")
    rec = {}
    for (st, y, com, un), g in w.groupby(["state_alpha", "year", "commodity", "unit"]):
        if g["short_desc"].nunique() > 1:                                   # still several series: prefer the one naming GRAIN
            pick = sorted(g["short_desc"].unique(), key=lambda s: ("GRAIN" not in s.upper(), s))[0]
            findings.append(dict(state_alpha=st, year=int(y), problem="several_series", detail=f"{com} {un}: using '{pick}'"))
            g = g[g["short_desc"] == pick]
        stage = un.replace("PCT ", "").strip().lower().replace(" ", "_")
        base = f"nass_{com.lower()}_{stage}"
        r = rec.setdefault((st, int(y)), dict(state_alpha=st, year=int(y), state=FIPS.get(st)))
        d, v = g["doy"].to_numpy(float), g["value"].to_numpy(float)
        for q in (10, 50, 90):
            r[f"{base}_p{q}_doy"] = NX.doy_cross(d, v, q)
    if not rec:
        sys.exit("no usable PCT progress rows after filtering")
    wide = pd.DataFrame(list(rec.values())).sort_values(["state_alpha", "year"]).reset_index(drop=True)
    # quality: missing + stage order
    for _, r in wide.iterrows():
        for com, stages in ORDER.items():
            cols = [f"nass_{com}_{s}_p50_doy" for s in stages]
            have = [c for c in cols if c in wide.columns]
            for c in have:
                if pd.isna(r[c]):
                    findings.append(dict(state_alpha=r["state_alpha"], year=int(r["year"]), problem="missing_p50", detail=c))
            vals = [(c, r[c]) for c in have if pd.notna(r[c])]
            for (c1, v1), (c2, v2) in zip(vals, vals[1:]):
                if v2 < v1:
                    findings.append(dict(state_alpha=r["state_alpha"], year=int(r["year"]), problem="stage_order",
                                         detail=f"{c2}={v2:.0f} earlier than {c1}={v1:.0f}"))
    return wide, findings


def step_nass(a):
    out = Path(a.out); raw = out / "raw"; raw.mkdir(parents=True, exist_ok=True)
    if not a.api_key:
        sys.exit("NASS API key needed: --api-key or env NASS_API_KEY")
    ns = argparse.Namespace(state=a.state, years=a.years, out=str(raw), api_key=a.api_key, url=a.url,
                            commodities=a.commodities, agg_level="STATE", condition=False)
    log(f"NASS Crop Progress {a.years[0]}-{a.years[-1]}, state {a.state}, commodities {a.commodities}")
    NX.cmd_progress(ns)                                        # writes raw/nass_progress_weekly.parquet (+ its own dates file)
    w = pd.read_parquet(raw / "nass_progress_weekly.parquet")
    wide, findings = weekly_to_stage_dates(w)
    wide.to_parquet(out / "nass_stage_dates.parquet", index=False)
    pd.DataFrame(findings).to_csv(out / "nass_quality_report.csv", index=False)
    need = ["nass_corn_planted_p50_doy", "nass_corn_silking_p50_doy", "nass_corn_mature_p50_doy", "nass_corn_harvested_p50_doy",
            "nass_soybeans_planted_p50_doy", "nass_soybeans_blooming_p50_doy", "nass_soybeans_dropping_leaves_p50_doy",
            "nass_soybeans_harvested_p50_doy"]
    log(f"wrote nass_stage_dates.parquet: {len(wide)} state-years; columns M3 needs, years with a value:")
    for c in need:
        n = int(wide[c].notna().sum()) if c in wide.columns else 0
        print(f"   {c:44s} {n}/{len(wide)}")
    bad = [f for f in findings if f["problem"] in ("missing_p50", "stage_order")]
    if bad:
        log(f"  {len(bad)} quality findings (see nass_quality_report.csv), e.g. {bad[0]}")


# ------------------------------------------------------------------ gridMET (sample points)
def sample_points(power, max_points):
    p = Path(power)
    cand = [p / "cells.parquet"]
    if (p / "weather_daily.parquet").exists():
        cand.append(p / "weather_daily.parquet")
    cand += sorted(p.glob("weather_daily_*.parquet"), key=lambda f: f.name, reverse=True)
    f = next((c for c in cand if c.exists()), None)
    if f is None:
        sys.exit(f"no cells.parquet / weather_daily*.parquet in {power}")
    ids = sorted(set(pq.read_table(f, columns=["cell_id"]).column("cell_id").to_pylist()))
    pts = pd.DataFrame({"cell_id": ids})
    ll = pts["cell_id"].str.split("_", expand=True).astype(float)
    pts["cell_lat"], pts["cell_lon"] = ll[0], ll[1]
    if len(pts) > max_points:
        pts = pts.iloc[np.linspace(0, len(pts) - 1, max_points).round().astype(int)].reset_index(drop=True)
    return pts


def step_gridmet(a):
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    cache = Path(a.cache); cache.mkdir(parents=True, exist_ok=True)
    pts = sample_points(a.power, a.max_points)
    log(f"gridMET {a.years[0]}-{a.years[-1]} at {len(pts)} sample points (POWER cells), variables {a.vars}")
    daily = []
    for y in a.years:
        data, days = {}, None
        for v in a.vars:
            nc = cache / f"{v}_{y}.nc"
            if not nc.exists():
                url = a.url_template.format(var=v, year=y)
                log(f"  {v} {y}: {url}")
                if not GX.get_file(url, nc):
                    log(f"  could not download {v} {y}; year skipped"); data = None; break
            days, arr = GX.read_gridmet_nc(nc, pts)             # (time, point); K -> C already handled for temperature
            data[v] = arr
            if not a.keep_files:
                nc.unlink(missing_ok=True)
        if not data:
            continue
        daily.append(pd.DataFrame({"date": days, "tx": np.nanmean(data["tmmx"], 1), "tn": np.nanmean(data["tmmn"], 1),
                                   "eto": np.nanmean(data["pet"], 1), "lat": float(pts["cell_lat"].mean()), "n_points": len(pts)}))
        log(f"  {y}: {len(days)} days")
    if not daily:
        sys.exit("no gridMET year could be read")
    d = pd.concat(daily, ignore_index=True)
    d.to_parquet(out / "gridmet_eto_calib.parquet", index=False)
    log(f"wrote gridmet_eto_calib.parquet ({len(d):,} days, {d['date'].dt.year.nunique()} years)")


# ------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["nass", "gridmet", "all"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--years", nargs="+", help="e.g. 2015-2025 or 2015 2016 ... (default: 2015..last full year; gridmet: last 5)")
    ap.add_argument("--state", default="IA", help="state alpha, comma list or ALL (NASS)")
    ap.add_argument("--api-key", default=os.environ.get("NASS_API_KEY"))
    ap.add_argument("--url", default=NX.URL)
    ap.add_argument("--commodities", nargs="+", default=["CORN", "SOYBEANS"])
    ap.add_argument("--power", help="csb_power_weather / csb_power_history output dir: its cells are the gridMET sample points")
    ap.add_argument("--max-points", type=int, default=30)
    ap.add_argument("--vars", nargs="+", default=["tmmx", "tmmn", "pet"])
    ap.add_argument("--url-template", default=GX.GRIDMET_URL)
    ap.add_argument("--cache", default="./ext_cache")
    ap.add_argument("--keep-files", action="store_true")
    a = ap.parse_args()
    last = dt.date.today().year - 1
    if a.cmd in ("nass", "all"):
        a.years = parse_years(a.years) if a.years else list(range(2015, last + 1))
        step_nass(a)
    if a.cmd in ("gridmet", "all"):
        if not a.power:
            sys.exit("gridmet needs --power (its cells are the sample points)")
        a.years = parse_years(a.years) if a.years else list(range(last - 4, last + 1))
        step_gridmet(a)


if __name__ == "__main__":
    main()
