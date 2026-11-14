#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIVOZMINA  -  M3  Window Forecaster  (ChronoShift + Fallow-Zero)
=================================================================

Implements proposal section 4.4 for the `field_daily_2025_enriched` dataset
(one row = CSB field x day, Iowa 2023-2025, window 04-01..10-31).

    A. ChronoShift  : frost / sowing / flowering / maturity windows per weather cell,
                      heat-overlap probability at the sensitive stage, adaptation margin
                      ("tolerates N days later sowing"), now and under CMIP6 deltas.
    B. Fallow-Zero  : FAO-56-style daily water ledger, harvest -> next sowing, bare fallow
                      vs cereal-rye cover; ML (LightGBM) residual correction against SMAP L4;
                      probability that the next crop starts below a plant-available-water
                      threshold (metric m9) and the autumn rain needed for the cover to be "safe".

Field Memory (M1) is NOT required. Substitutes used (all from the dataset):
    * observed phenology  -> NASS Crop Progress state dates (`nass_*_doy`), used to calibrate
                             the sowing lag and the GDD-to-flowering / GDD-to-maturity constants
                             and to validate leave-one-year-out;
    * harvest dates       -> NASS `*_harvested_p50_doy` (state level) or a default.

IMPORTANT - what the dataset alone cannot do (see `check` output):
    * It only holds 3 seasons and only Apr 1 - Oct 31. Quantile models need ~15+ years and
      frost / winter water balance need Nov-Mar. Provide `--history` (daily weather per cell,
      1981-present, full year). Without it the script still runs but reports the results as
      NOT calibrated (n_years = 3, censored frost dates) and Fallow-Zero scenarios are skipped.
    * Future (2040) windows need `--deltas` (NEX-GDDP-CMIP6 monthly deltas per cell).

Sub-commands
    check             data-readiness report (what is present / missing)
    chronoshift       part A
    ledger-calibrate  fit ledger parameters + LightGBM residual on SMAP L4 (dataset only)
    fallow-zero       part B (needs --history)
    all               check -> chronoshift -> ledger-calibrate -> fallow-zero

Example
    python m3_window_forecaster.py all --dataset field_daily_2025_enriched \
        --history power_history_1981_2025.parquet --deltas cmip6_deltas_2040.parquet \
        --out m3_out --target-year 2027

Conventions
    * Day index: 0-based position in a 365-day calendar (Feb 29 dropped). Outputs add 1 (doy).
    * Weather cell = POWER cell (`power_cell_id`) by default (`--cell-source gridmet` possible).
    * Every table carries n_years / censoring flags: nothing is silently extrapolated.
"""
from __future__ import annotations

import argparse
import calendar
import copy
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None
try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover
    lgb = None

warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=FutureWarning)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# =====================================================================================
# 0. PARAMETERS  (everything that is a judgement call lives here; override with --params)
# =====================================================================================
DEFAULTS = dict(
    cell_source="power",            # power | gridmet
    # --- ChronoShift ---
    frost_c=0.0,                    # frost if daily min <= this (proposal: T2M_MIN <= 0 C)
    spring_frost_last_md=[6, 30],   # last-spring-frost search stops here
    autumn_frost_first_md=[8, 1],   # first-autumn-frost search starts here
    dry_day_mm=2.0,                 # workable-day rule: rain today <= this ...
    dry_3d_mm=12.0,                 # ... and 3-day rain <= this
    ready_k=3, ready_n=5,           # "first workable date" = >=k workable days in the next n
    sow_lag_days=7,                 # default lag first-workable -> typical sowing (calibrated to NASS if present)
    delays=[0, 5, 10, 15, 20, 25, 30],   # sowing-delay scan for the adaptation margin
    heat_limit=0.40,                # m5 flag level from the proposal
    fbm_limit=0.10,                 # max accepted P(frost before maturity)
    heat_rise_tol=0.05,             # margin: P(heat overlap) may rise by this much over delay 0 (sampling noise)
    normal_years=30,                # years used for the "now" probabilities
    min_years_ml=15,                # LightGBM quantile models only with >= this many years
    holdout_years=5,
    quantiles=[0.1, 0.5, 0.9],
    lgbm_trees=200,
    # --- Fallow-Zero ---
    awc_bin_mm=20.0,                # units = (weather cell, AWC bin)
    default_awc_mm=150.0,           # when SSURGO AWS is missing
    kc_bare=0.35, p_dep=0.5, snow_ddf=2.5,
    rye=dict(seed_lag_days=7, gdd_base=4.0, gdd_full=500.0, kc_max=0.9),   # PLACEHOLDERS - biggest uncertainty, set from FAO-56/extension/OpenET
    paw_threshold_frac=0.50,        # "starts below threshold": PAW at sowing < frac * AWC
    m9_limit=0.30,                  # proposal rule: cover-crop opportunity if m9 <= 0.3
    spin_years=2,                   # years discarded at the start of the continuous ledger run
    min_scenario_years=10,
    lai_bare_max=0.5, snow_bare_max=1.0,   # calibration only on bare-soil, snow-free days
    calib_max_triples=4000, calib_max_rows=400000,
    rollout_days=14,
    hs_scale=1.0,                   # Hargreaves scale (calibrated against gridMET ETo if present)
)

DEFAULT_CROPS = {
    "corn": dict(
        earliest_md=[4, 11], latest_md=[5, 31],          # RMA Iowa earliest / final planting dates: CHECK
        sow_tmean_c=10.0,
        gdd_base=10.0, gdd_cap=30.0,
        gdd_flower=780.0, gdd_mature=1500.0,            # C-days placeholders, replaced by NASS calibration
        heat_c=35.0, heat_days_min=2, flower_window=[-3, 12],
        harvest_md=[10, 15],
        nass=dict(planted="nass_corn_planted_p50_doy", flower="nass_corn_silking_p50_doy",
                  mature="nass_corn_mature_p50_doy", harvest="nass_corn_harvested_p50_doy"),
        kc_knots=[["sow", 0, 0.30], ["flower", -10, 1.10], ["flower", 25, 1.10],
                  ["mature", 0, 0.60], ["harvest", 0, 0.35]],
        cover_term_lead_days=14,                          # rye terminated this long before sowing THIS crop
    ),
    "soybeans": dict(
        earliest_md=[4, 21], latest_md=[6, 15],
        sow_tmean_c=10.0,
        gdd_base=10.0, gdd_cap=30.0,
        gdd_flower=450.0, gdd_mature=1300.0,
        heat_c=35.0, heat_days_min=2, flower_window=[0, 25],
        harvest_md=[10, 3],
        nass=dict(planted="nass_soybeans_planted_p50_doy", flower="nass_soybeans_blooming_p50_doy",
                  mature="nass_soybeans_dropping_leaves_p50_doy", harvest="nass_soybeans_harvested_p50_doy"),
        kc_knots=[["sow", 0, 0.30], ["flower", 15, 1.10], ["flower", 50, 1.10],
                  ["mature", 0, 0.60], ["harvest", 0, 0.35]],
        cover_term_lead_days=3,
    ),
}
OTHER = {"corn": "soybeans", "soybeans": "corn"}

CELL_SOURCES = {
    "power": dict(cell="power_cell_id", tmin="power_T2M_MIN", tmax="power_T2M_MAX", pr="power_PRECTOTCORR"),
    "gridmet": dict(cell="gridmet_cell_id", tmin="gridmet_tmin_c", tmax="gridmet_tmax_c", pr="gridmet_pr_mm"),
}
HIST_SYNONYMS = dict(
    cell_id=["cell_id", "power_cell_id", "gridmet_cell_id"],
    tmin_c=["tmin_c", "T2M_MIN", "power_T2M_MIN", "gridmet_tmin_c"],
    tmax_c=["tmax_c", "T2M_MAX", "power_T2M_MAX", "gridmet_tmax_c"],
    pr_mm=["pr_mm", "PRECTOTCORR", "power_PRECTOTCORR", "gridmet_pr_mm"],
)


def load_params(path: str | None):
    p, crops = copy.deepcopy(DEFAULTS), copy.deepcopy(DEFAULT_CROPS)
    if path:
        o = json.loads(Path(path).read_text())
        for k, v in o.get("crops", {}).items():
            crops.setdefault(k, {}).update(v)
        for k, v in o.items():
            if k != "crops":
                p[k] = {**p[k], **v} if isinstance(p.get(k), dict) else v
    return p, crops


# =====================================================================================
# 1. CALENDAR / ARRAY HELPERS
# =====================================================================================
_REF = pd.date_range("2001-01-01", periods=365)
MONTH_OF_IDX = _REF.month.to_numpy() - 1


def md_to_idx(md) -> int:
    return int(pd.Timestamp(2001, int(md[0]), int(md[1])).dayofyear) - 1


def idx_to_md(i) -> str | None:
    if i is None or not np.isfinite(i):
        return None
    return (pd.Timestamp(2001, 1, 1) + pd.Timedelta(days=int(round(i)))).strftime("%m-%d")


def std_idx(dates):
    """0-based index in a 365-day calendar; second return flags Feb 29 (dropped)."""
    d = pd.DatetimeIndex(pd.to_datetime(dates))
    doy = d.dayofyear.to_numpy().copy()
    leap = np.asarray(d.is_leap_year)
    m = d.month.to_numpy()
    doy = doy - (leap & (m > 2)).astype(int)
    feb29 = leap & (m == 2) & (d.day.to_numpy() == 29)
    return doy - 1, feb29


def raw_doy_to_idx(doy, year):
    doy = np.asarray(doy, float)
    leap = np.array([calendar.isleap(int(y)) for y in np.atleast_1d(year)])
    return doy - 1 - (leap & (doy > 60))


def to_cube(df: pd.DataFrame, cols, cell_ids, years):
    """long (cell_id,date,cols) -> {col: (C, Y, 365) float64 with NaN where missing}."""
    ci = pd.Index(cell_ids).get_indexer(df["cell_id"])
    dt = pd.to_datetime(df["date"])
    yi = pd.Index(years).get_indexer(dt.dt.year)
    di, f29 = std_idx(dt)
    ok = (ci >= 0) & (yi >= 0) & (~f29)
    out = {}
    for c in cols:
        a = np.full((len(cell_ids), len(years), 365), np.nan)
        a[ci[ok], yi[ok], di[ok]] = df[c].to_numpy(float)[ok]
        out[c] = a
    return out


def wilson(k, n, z=1.2816):
    """80% Wilson interval."""
    k = np.asarray(k, float)
    n = np.asarray(n, float)
    with np.errstate(all="ignore"):
        ph = k / n
        den = 1 + z * z / n
        c = (ph + z * z / (2 * n)) / den
        h = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return np.where(n > 0, np.clip(c - h, 0, 1), np.nan), np.where(n > 0, np.clip(c + h, 0, 1), np.nan)


def first_true(mask):
    has = mask.any(-1)
    return np.where(has, mask.argmax(-1).astype(float), np.nan)


def last_true(mask, stop):
    m = mask[..., : stop + 1]
    has = m.any(-1)
    return np.where(has, (m.shape[-1] - 1 - m[..., ::-1].argmax(-1)).astype(float), np.nan)


def trailing(a, n, fn="mean"):
    ap = np.concatenate([np.full(a.shape[:-1] + (n - 1,), np.nan), a], -1)
    w = np.lib.stride_tricks.sliding_window_view(ap, n, axis=-1)
    return w.mean(-1) if fn == "mean" else w.sum(-1)


def forward_sum(a, n):
    ap = np.concatenate([a, np.zeros(a.shape[:-1] + (n - 1,))], -1)
    return np.lib.stride_tricks.sliding_window_view(ap, n, axis=-1).sum(-1)


def merge_chunks(parts):
    if isinstance(parts[0], dict):
        return {k: merge_chunks([x[k] for x in parts]) for k in parts[0]}
    return np.concatenate(parts, axis=0)


# =====================================================================================
# 2. DATA ACCESS  (DuckDB over the field-day parquet; field rows are collapsed to cells)
# =====================================================================================
class Dataset:
    def __init__(self, path: str, p: dict):
        if duckdb is None:
            sys.exit("duckdb is required: pip install duckdb")
        pth = Path(path)
        self.glob = str(pth) if pth.is_file() else str(pth / "**" / "*.parquet")
        self.con = duckdb.connect()
        self.src = f"read_parquet('{self.glob}', union_by_name=true, hive_partitioning=false)"
        self.cols = [r[0] for r in self.con.execute(f"DESCRIBE SELECT * FROM {self.src}").fetchall()]
        self.p = p
        self.m = CELL_SOURCES[p["cell_source"]]

    def has(self, *c):
        return all(x in self.cols for x in c)

    def q(self, sql):
        return self.con.execute(sql).df()

    # --- weather per cell --------------------------------------------------------
    def weather(self) -> pd.DataFrame:
        m = self.m
        miss = [c for c in m.values() if c not in self.cols]
        if miss:
            sys.exit(f"dataset lacks weather columns {miss} (cell source '{self.p['cell_source']}')")
        df = self.q(f"""SELECT {m['cell']} AS cell_id, CAST(date AS DATE) AS date,
                        avg({m['tmin']}) AS tmin_c, avg({m['tmax']}) AS tmax_c, avg({m['pr']}) AS pr_mm
                        FROM {self.src} WHERE {m['cell']} IS NOT NULL GROUP BY 1,2""")
        df["date"] = pd.to_datetime(df["date"])
        for c in ("tmin_c", "tmax_c", "pr_mm"):
            df.loc[df[c] < -900, c] = np.nan
        return df

    # --- one row per field (static attributes) ----------------------------------
    def fields(self) -> pd.DataFrame:
        cell = self.m["cell"]
        sel = [f"any_value({cell}) AS cell_id", "any_value(county_fips) AS county_fips",
               "avg(centroid_lat) AS lat", "avg(centroid_lon) AS lon"]
        sel.append("any_value(smap_cell_id) AS smap_cell_id" if self.has("smap_cell_id") else "NULL AS smap_cell_id")
        sel.append("any_value(area_acres) AS area_acres" if self.has("area_acres") else "NULL AS area_acres")
        sel.append("any_value(ssurgo_aws_0_100_mm) AS aws_mm" if self.has("ssurgo_aws_0_100_mm") else "CAST(NULL AS DOUBLE) AS aws_mm")
        # static attributes repeat on every day: read only the days around 1 July (integer filter is fast)
        flt = "doy IN (182, 183)" if self.has("doy") else "strftime(CAST(date AS DATE), '%m-%d') = '07-01'"
        return self.q(f"""SELECT CSBID, {', '.join(sel)} FROM {self.src}
                          WHERE {flt} AND {cell} IS NOT NULL GROUP BY CSBID""")

    def smap(self) -> pd.DataFrame | None:
        need = ["smap_cell_id", "smap_sm_rootzone"]
        if not self.has(*need):
            return None
        opt = {"smap_leaf_area_index": "lai", "smap_snow_mass": "snow", "smap_soil_temp_layer1": "soilt_k"}
        sel = ["avg(smap_sm_rootzone) AS sm_rz"] + [f"avg({k}) AS {v}" for k, v in opt.items() if self.has(k)]
        df = self.q(f"""SELECT smap_cell_id, CAST(date AS DATE) AS date, {', '.join(sel)}
                        FROM {self.src} WHERE smap_cell_id IS NOT NULL GROUP BY 1,2""")
        df["date"] = pd.to_datetime(df["date"])
        for v in opt.values():
            if v not in df:
                df[v] = np.nan
        return df

    def nass(self) -> pd.DataFrame | None:
        cols = [c for c in self.cols if c.startswith("nass_") and c.endswith("_doy")]
        if not cols or not self.has("year", "county_fips"):
            return None
        sel = ", ".join(f"max({c}) AS {c}" for c in cols)
        df = self.q(f"SELECT year, substr(county_fips,1,2) AS state, {sel} FROM {self.src} GROUP BY 1,2")
        return df  # value shows only from the day reached, so max() over the season = the date

    def gridmet_eto_state_mean(self) -> pd.DataFrame | None:
        if not self.has("gridmet_eto_grass_mm", "gridmet_tmin_c", "gridmet_tmax_c", "centroid_lat"):
            return None
        return self.q(f"""SELECT CAST(date AS DATE) AS date, avg(gridmet_eto_grass_mm) AS eto,
                          avg(gridmet_tmin_c) AS tn, avg(gridmet_tmax_c) AS tx, avg(centroid_lat) AS lat
                          FROM {self.src} GROUP BY 1""")

    def date_coverage(self) -> pd.DataFrame:
        return self.q(f"""SELECT year, min(CAST(date AS DATE)) AS first_date, max(CAST(date AS DATE)) AS last_date,
                          count(DISTINCT CAST(date AS DATE)) AS n_days, count(DISTINCT CSBID) AS n_fields
                          FROM {self.src} GROUP BY 1 ORDER BY 1""")


def load_history(path: str | None):
    if not path:
        return None
    df = pd.read_csv(path) if str(path).endswith(".csv") else pd.read_parquet(path)
    ren = {}
    for std, syn in HIST_SYNONYMS.items():
        hit = next((s for s in syn if s in df.columns), None)
        if hit is None:
            sys.exit(f"--history lacks a column for '{std}' (accepted: {syn})")
        ren[hit] = std
    df = df.rename(columns=ren)[["cell_id", "date", "tmin_c", "tmax_c", "pr_mm"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    for c in ("tmin_c", "tmax_c", "pr_mm"):
        df.loc[df[c] < -900, c] = np.nan
    return df


def prepare(ds: Dataset, p: dict):
    """Collapse the field-day table into the objects every stage needs."""
    log("loading weather cells ...")
    w = ds.weather()
    fields = ds.fields()
    fields["cell_id"] = fields["cell_id"].astype(str)
    fields["state"] = fields["county_fips"].astype(str).str[:2]
    cell_ids = sorted(w["cell_id"].unique())
    years = sorted(w["date"].dt.year.unique())
    meta = fields.groupby("cell_id").agg(lat=("lat", "mean"), lon=("lon", "mean"),
                                         state=("state", lambda s: s.mode().iat[0]),
                                         n_fields=("CSBID", "size")).reindex(cell_ids).reset_index()
    cube = to_cube(w, ["tmin_c", "tmax_c", "pr_mm"], cell_ids, years)
    # units for Fallow-Zero
    f = fields.copy()
    f["aws_filled"] = f["aws_mm"].fillna(f.groupby("cell_id")["aws_mm"].transform("median"))
    f["aws_filled"] = f["aws_filled"].fillna(f["aws_mm"].median()).fillna(p["default_awc_mm"])
    b = p["awc_bin_mm"]
    f["awc_bin_mm"] = (np.round(f["aws_filled"] / b) * b).clip(lower=b)
    f["unit_id"] = f["cell_id"] + "|" + f["awc_bin_mm"].astype(int).astype(str)
    return dict(w=w, fields=f, cell_ids=cell_ids, years=years, meta=meta, cube=cube, nass=ds.nass())


def history_cube(hist, cell_ids, lat_by_cell=None):
    h = hist[hist["cell_id"].isin(cell_ids)]
    if h.empty:
        sys.exit("--history shares no cell_id with the dataset (check the cell id format)")
    years = sorted(h["date"].dt.year.unique())
    return to_cube(h, ["tmin_c", "tmax_c", "pr_mm"], cell_ids, years), years


def load_nass_table(path):
    if not path:
        return None
    df = pd.read_csv(path) if str(path).endswith(".csv") else pd.read_parquet(path)
    if "state" not in df or "year" not in df:
        sys.exit("--nass-table needs columns state (FIPS) and year (m3_collect_calibration.py nass writes it)")
    df["state"] = df["state"].astype(str).str.zfill(2)
    df["year"] = df["year"].astype(int)
    return df


def calibration_view(D, hist, nass_tbl, p):
    """D as seen by the NASS calibration: NASS table (if given) and, when a history is given, the history weather for the NASS years
    (so 2015-2025 stage dates are used even though the dataset has 3 seasons). Falls back to D unchanged."""
    nass = nass_tbl if nass_tbl is not None else D["nass"]
    if nass is None:
        return D
    if hist is None:
        if nass_tbl is None:
            return D
        have = [y for y in D["years"] if y in set(nass["year"])]
        log(f"NASS calibration on dataset seasons only: {have} (add --history for more years)")
        return dict(D, nass=nass)
    cube, hy = history_cube(hist, D["cell_ids"])
    cnt = hist.groupby(hist["date"].dt.year).size()
    full = [y for y in hy if cnt.get(y, 0) >= 360]                         # complete calendar years only
    ys = [y for y in full if y in set(nass["year"])]
    if not ys:
        log("NASS table and history share no complete year -> calibrating on dataset seasons")
        return dict(D, nass=nass)
    ix = [hy.index(y) for y in ys]
    log(f"NASS calibration on history weather, {len(ys)} seasons ({ys[0]}-{ys[-1]})")
    return dict(D, cube={k: v[:, ix] for k, v in cube.items()}, years=ys, nass=nass)


# =====================================================================================
# 3. CHRONOSHIFT CORE  (vectorised over cells x years x 365 days)
# =====================================================================================
def gdd_daily(tmin, tmax, base, cap):
    tx = np.maximum(np.minimum(tmax, cap), base)
    tn = np.maximum(tmin, base)
    return np.maximum((tx + tn) / 2.0 - base, 0.0)


def frost_events(tmin, p):
    obs = ~np.isnan(tmin)
    frost = obs & (tmin <= p["frost_c"])
    sp_end = md_to_idx(p["spring_frost_last_md"])
    au0 = md_to_idx(p["autumn_frost_first_md"])
    anyobs = obs.any(-1)
    first_obs = np.where(anyobs, obs.argmax(-1), np.nan)
    last_obs = np.where(anyobs, 364 - obs[..., ::-1].argmax(-1), np.nan)
    lsf = last_true(frost, sp_end)
    lsf_cens = np.isnan(lsf) & (first_obs > 0)            # record starts after Jan 1: frost may be earlier
    lsf = np.where(np.isnan(lsf), first_obs, lsf)
    afm = frost.copy()
    afm[..., :au0] = False
    faf = first_true(afm)
    faf_cens = np.isnan(faf) & (last_obs < 364)          # record ends before Dec 31: frost may be later
    faf = np.where(np.isnan(faf), np.where(anyobs, last_obs + 1, np.nan), faf)
    return dict(last_spring_frost=lsf, last_spring_frost_censored=lsf_cens,
                first_autumn_frost=faf, first_autumn_frost_censored=faf_cens,
                first_obs=first_obs, last_obs=last_obs)


def phenology(sow, gdd, tmax, cp, ff_obs):
    """sow (C,Y) idx (NaN allowed). Returns flower, mature idx, heat days in the flowering window,
    heat-overlap flag and frost-before-maturity flag."""
    g = np.nan_to_num(gdd, nan=0.0)
    cum = np.cumsum(g, -1)
    s = np.where(np.isnan(sow), 364, sow).astype(int)[..., None]
    before = np.take_along_axis(cum, s, -1)[..., 0] - np.take_along_axis(g, s, -1)[..., 0]
    since = cum - before[..., None]
    after = np.arange(365) >= s
    flower = first_true((since >= cp["gdd_flower"]) & after)
    mature = first_true((since >= cp["gdd_mature"]) & after)
    heat = np.nan_to_num((tmax >= cp["heat_c"]).astype(float))
    ch0 = np.concatenate([np.zeros(heat.shape[:-1] + (1,)), np.cumsum(heat, -1)], -1)   # ch0[i] = sum before i
    a, b = cp["flower_window"]
    lo = np.clip(np.nan_to_num(flower, nan=0) + a, 0, 364).astype(int)[..., None]
    hi = np.clip(np.nan_to_num(flower, nan=0) + b, 0, 364).astype(int)[..., None]
    hd = (np.take_along_axis(ch0, hi + 1, -1) - np.take_along_axis(ch0, lo, -1))[..., 0]
    hd = np.where(np.isnan(flower) | np.isnan(sow), np.nan, hd)
    ho = np.where(np.isnan(hd), np.nan, (hd >= cp["heat_days_min"]).astype(float))
    known = ~np.isnan(ff_obs)
    fbm = np.where(known, np.where(np.isnan(mature), 1.0, (ff_obs < mature).astype(float)),
                   np.where(np.isnan(mature), np.nan, 0.0))
    fbm = np.where(np.isnan(sow), np.nan, fbm)
    return flower, mature, hd, ho, fbm


def season_core(tmin, tmax, pr, crops, p, calib):
    fr = frost_events(tmin, p)
    out = {"common": fr}
    tmean = (tmin + tmax) / 2.0
    dry = (pr <= p["dry_day_mm"]) & (trailing(pr, 3, "sum") <= p["dry_3d_mm"])
    t5 = trailing(tmean, 5)
    ff_obs = np.where(fr["first_autumn_frost_censored"], np.nan, fr["first_autumn_frost"])
    d = np.arange(365)
    for crop, cp in crops.items():
        e0, e1 = md_to_idx(cp["earliest_md"]), md_to_idx(cp["latest_md"])
        win = (d >= e0) & (d <= e1)
        ready = (t5 >= cp["sow_tmean_c"]) & dry
        cand = ready & (forward_sum(ready.astype(float), p["ready_n"]) >= p["ready_k"]) & win
        obs_win = (~np.isnan(tmean[..., e0:e1 + 1])).mean(-1) >= 0.9
        first_ready = np.where(obs_win, first_true(cand), np.nan)
        workable = np.where(obs_win, (ready & win).sum(-1).astype(float), np.nan)
        lag = calib.get("sow_lag", {}).get(crop, p["sow_lag_days"])
        sow = np.where(obs_win, np.clip(np.where(np.isnan(first_ready), e1, first_ready + lag), e0, e1), np.nan)
        cpc = copy.deepcopy(cp)
        cpc["gdd_flower"] = calib.get("gdd_flower", {}).get(crop, cp["gdd_flower"])
        cpc["gdd_mature"] = calib.get("gdd_mature", {}).get(crop, cp["gdd_mature"])
        gdd = gdd_daily(tmin, tmax, cp["gdd_base"], cp["gdd_cap"])
        scan = {}
        for dly in p["delays"]:
            fl, mt, hd, ho, fbm = phenology(np.minimum(sow + dly, 364), gdd, tmax, cpc, ff_obs)
            scan[int(dly)] = dict(heat_overlap=ho, fbm=fbm)
            if dly == 0:
                base = dict(flower=fl, mature=mt, heat_days=hd)
        out[crop] = dict(first_ready=first_ready, workable_days=workable, sow=sow, scan=scan, **base)
    return out


def season_core_chunked(tmin, tmax, pr, crops, p, calib, chunk=400):
    parts = []
    for i in range(0, tmin.shape[0], chunk):
        parts.append(season_core(tmin[i:i + chunk], tmax[i:i + chunk], pr[i:i + chunk], crops, p, calib))
    return merge_chunks(parts) if len(parts) > 1 else parts[0]


# =====================================================================================
# 4. CHRONOSHIFT - NASS calibration / validation, quantile models, risk tables, CMIP6
# =====================================================================================
def nass_cube(nass, meta, years, col):
    """(C,Y) 0-based day index of a NASS stage for the state of each cell; NaN where absent."""
    out = np.full((len(meta), len(years)), np.nan)
    if nass is None or col not in nass.columns:
        return out
    key = nass.set_index(["state", "year"])[col]
    for j, y in enumerate(years):
        v = np.array([key.get((s, y), np.nan) for s in meta["state"]], float)
        out[:, j] = raw_doy_to_idx(v, [y] * len(v))
    return out


def calibrate_from_nass(D, crops, p):
    """Sowing lag and GDD constants per year from NASS state dates; medians over years."""
    cube, years, meta = D["cube"], D["years"], D["meta"]
    calib = {"sow_lag": {}, "gdd_flower": {}, "gdd_mature": {}, "harvest_idx": {}, "per_year": {}, "notes": []}
    base = season_core_chunked(cube["tmin_c"], cube["tmax_c"], cube["pr_mm"], crops, p, {})
    for crop, cp in crops.items():
        pl = nass_cube(D["nass"], meta, years, cp["nass"]["planted"])
        fl = nass_cube(D["nass"], meta, years, cp["nass"]["flower"])
        mt = nass_cube(D["nass"], meta, years, cp["nass"]["mature"])
        hv = nass_cube(D["nass"], meta, years, cp["nass"]["harvest"])
        gdd = np.nan_to_num(gdd_daily(cube["tmin_c"], cube["tmax_c"], cp["gdd_base"], cp["gdd_cap"]))
        cum = np.cumsum(gdd, -1)

        def between(i0, i1):
            ok = ~np.isnan(i0) & ~np.isnan(i1)
            a = np.take_along_axis(cum, np.where(ok, i1, 0).astype(int)[..., None], -1)[..., 0]
            b = np.take_along_axis(cum, np.clip(np.where(ok, i0, 0) - 1, 0, 364).astype(int)[..., None], -1)[..., 0]
            return np.where(ok, a - b, np.nan)

        lag_y = np.nanmedian(pl - base[crop]["first_ready"], axis=0)
        gf_y = np.nanmedian(between(np.round(pl), np.round(fl)), axis=0)
        gm_y = np.nanmedian(between(np.round(pl), np.round(mt)), axis=0)
        hv_y = np.nanmedian(hv, axis=0)
        calib["per_year"][crop] = dict(years=[int(y) for y in years], sow_lag=lag_y.tolist(),
                                       gdd_flower=gf_y.tolist(), gdd_mature=gm_y.tolist(), harvest_idx=hv_y.tolist())
        if np.isfinite(lag_y).any():
            calib["sow_lag"][crop] = float(np.clip(np.nanmedian(lag_y), 0, 28))
        else:
            calib["notes"].append(f"{crop}: no NASS planted dates -> default sowing lag {p['sow_lag_days']} d")
        for k, arr in (("gdd_flower", gf_y), ("gdd_mature", gm_y)):
            if np.isfinite(arr).any():
                calib[k][crop] = float(np.nanmedian(arr))
            else:
                calib["notes"].append(f"{crop}: no NASS stage dates for {k} -> default constant")
        calib["harvest_idx"][crop] = float(np.nanmedian(hv_y)) if np.isfinite(hv_y).any() else float(md_to_idx(cp["harvest_md"]))
    return calib


def validate_nass(D, crops, p, calib):
    """Leave-one-year-out: calibrate on the other seasons, predict the held-out one, compare to NASS."""
    cube, years, meta = D["cube"], D["years"], D["meta"]
    rows = []
    if D["nass"] is None or len(years) < 2:
        return pd.DataFrame(rows)
    for crop, cp in crops.items():
        py = calib["per_year"].get(crop)
        if py is None:
            continue
        for j, y in enumerate(years):
            oth = [k for k in range(len(years)) if k != j]
            c2 = {"sow_lag": {}, "gdd_flower": {}, "gdd_mature": {}}
            for key, src in (("sow_lag", py["sow_lag"]), ("gdd_flower", py["gdd_flower"]), ("gdd_mature", py["gdd_mature"])):
                v = np.array(src, float)[oth]
                if np.isfinite(v).any():
                    c2[key][crop] = float(np.nanmedian(v))
            sl = slice(j, j + 1)
            r = season_core_chunked(cube["tmin_c"][:, sl], cube["tmax_c"][:, sl], cube["pr_mm"][:, sl], {crop: cp}, p, c2)[crop]
            for stage, pred in (("planted", r["sow"]), ("flower", r["flower"]), ("mature", r["mature"])):
                obs = nass_cube(D["nass"], meta, [y], cp["nass"][stage])[:, 0]
                if not np.isfinite(obs).any():
                    continue
                pr_ = pred[:, 0]
                rows.append(dict(crop=crop, stage=stage, year=int(y), nass_doy=float(np.nanmedian(obs)) + 1,
                                 model_mean_doy=float(np.nanmean(pr_)) + 1, model_p10_doy=float(np.nanpercentile(pr_, 10)) + 1,
                                 model_p90_doy=float(np.nanpercentile(pr_, 90)) + 1,
                                 error_days=float(np.nanmean(pr_) - np.nanmedian(obs)), scheme="leave-one-year-out"))
    return pd.DataFrame(rows)


# ---- quantile models ---------------------------------------------------------------
def pinball(y, qp, qs):
    qs = np.asarray(qs)
    e = y[:, None] - qp
    return float(np.mean(np.maximum(qs * e, (qs - 1) * e)))


def pred_clim(tr, te, qs, **_):
    q = tr.groupby("cell_id")["y"].quantile(qs).unstack()
    return q.reindex(te["cell_id"]).to_numpy()


def pred_trend(tr, te, qs, **_):
    t = tr.copy()
    t["ym"] = t.groupby("cell_id")["y"].transform("mean")
    t["tm"] = t.groupby("cell_id")["year"].transform("mean")
    x, yv = t["year"] - t["tm"], t["y"] - t["ym"]
    b = float((x * yv).sum() / max((x * x).sum(), 1e-9))
    t["res"] = yv - b * x
    rq = t.groupby("cell_id")["res"].quantile(qs).unstack().reindex(te["cell_id"]).to_numpy()
    cm = t.groupby("cell_id")[["ym", "tm"]].first().reindex(te["cell_id"])
    base = cm["ym"].to_numpy() + b * (te["year"].to_numpy() - cm["tm"].to_numpy())
    return base[:, None] + rq


def pred_lgbm(tr, te, qs, feats, p):
    out = np.zeros((len(te), len(qs)))
    for j, q in enumerate(qs):
        m = lgb.LGBMRegressor(objective="quantile", alpha=q, n_estimators=p["lgbm_trees"], learning_rate=0.05,
                              num_leaves=15, min_child_samples=20, subsample=0.8, subsample_freq=1,
                              random_state=0, verbose=-1)
        m.fit(tr[feats], tr["y"])
        out[:, j] = m.predict(te[feats])
    return np.sort(out, axis=1)


def fit_event_quantiles(panel, ev, p, target_year):
    qs = p["quantiles"]
    years = np.sort(panel["year"].unique())
    ny = len(years)
    feats = ["year", "lat", "lon"] + (["clim_state"] if panel["clim_state"].notna().any() else [])
    methods = {"climatology": lambda tr, te: pred_clim(tr, te, qs), "trend": lambda tr, te: pred_trend(tr, te, qs)}
    if lgb is not None and ny >= p["min_years_ml"]:
        methods["lgbm"] = lambda tr, te: pred_lgbm(tr, te, qs, feats, p)
    hy = p["holdout_years"]
    if ny >= hy + 10:
        folds, scheme = [(years[:-hy], years[-hy:])], f"time-split (last {hy} y)"
    elif ny >= 3:
        folds, scheme = [(years[years != y], np.array([y])) for y in years], "leave-one-year-out"
    else:
        folds, scheme = [], "none"
    ev_rows = []
    for name, f in methods.items():
        losses, covs, n = [], [], 0
        for tr_y, te_y in folds:
            tr, te = panel[panel["year"].isin(tr_y)], panel[panel["year"].isin(te_y)]
            if tr.empty or te.empty:
                continue
            qp = f(tr, te)
            ok = ~np.isnan(qp).any(1)
            if not ok.any():
                continue
            y = te["y"].to_numpy()[ok]
            losses.append(pinball(y, qp[ok], qs))
            covs.append(float(np.mean((y >= qp[ok][:, 0]) & (y <= qp[ok][:, -1]))))
            n += int(ok.sum())
        ev_rows.append(dict(event=ev, method=name, pinball=np.mean(losses) if losses else np.nan,
                            coverage_q10_q90=np.mean(covs) if covs else np.nan, n_test=n, scheme=scheme, n_years=ny))
    evdf = pd.DataFrame(ev_rows)
    sel = "climatology"
    if evdf["pinball"].notna().any():
        sel = evdf.sort_values(["pinball", "method"]).iloc[0]["method"]
    cells = panel.groupby("cell_id").agg(lat=("lat", "first"), lon=("lon", "first"),
                                         clim_state=("clim_state", "mean")).reset_index()
    cells["year"] = target_year
    pred_rows = []
    for name, f in methods.items():
        qp = f(panel, cells)
        d = pd.DataFrame(qp, columns=[f"q{int(q * 100)}" for q in qs])
        d.insert(0, "cell_id", cells["cell_id"].to_numpy())
        d["method"], d["event"], d["selected"] = name, ev, name == sel
        pred_rows.append(d)
    return pd.concat(pred_rows, ignore_index=True), evdf


def event_arrays(res, crops):
    ev = {"last_spring_frost": res["common"]["last_spring_frost"],
          "first_autumn_frost": res["common"]["first_autumn_frost"]}
    for c in crops:
        for k in ("first_ready", "flower", "mature"):
            ev[f"{c}:{k}"] = res[c][k]
    return ev


def build_panel(arr, cell_ids, years, meta, cs):
    C, Y = arr.shape
    df = pd.DataFrame({"cell_id": np.repeat(cell_ids, Y), "year": np.tile(years, C),
                       "y": arr.ravel(), "clim_state": cs.ravel()})
    df = df.merge(meta[["cell_id", "lat", "lon"]], on="cell_id", how="left")
    return df.dropna(subset=["y"]).reset_index(drop=True)


def emp_quant(arr, qs, min_n=3):
    C = arr.shape[0]
    out = np.full((C, len(qs)), np.nan)
    n = (~np.isnan(arr)).sum(1)
    ok = n >= min_n
    if ok.any():
        out[ok] = np.nanquantile(arr[ok], qs, axis=1).T
    return out, n


def add_dates(df, qcols):
    for c in qcols:
        df[c.replace("q", "date_q")] = [idx_to_md(v) for v in df[c]]
        df[c] = df[c] + 1.0  # -> day of year (1-based)
    return df


def summarize_risk(res, cell_ids, ysel, crops, p, period, scenario="obs", model="obs"):
    rr, ss = [], []
    delays = p["delays"]
    for crop in crops:
        r = res[crop]
        ph, pf, nn_h, nn_f = [], [], [], []
        for d in delays:
            s = r["scan"][d]
            h, f = s["heat_overlap"][:, ysel], s["fbm"][:, ysel]
            nn_h.append((~np.isnan(h)).sum(1))
            nn_f.append((~np.isnan(f)).sum(1))
            ph.append(np.where(nn_h[-1] > 0, np.nanmean(h, 1), np.nan))
            pf.append(np.where(nn_f[-1] > 0, np.nanmean(f, 1), np.nan))
            ss.append(pd.DataFrame(dict(cell_id=cell_ids, crop=crop, period=period, scenario=scenario, model=model,
                                        delay_days=d, p_heat_overlap=ph[-1], p_frost_before_maturity=pf[-1],
                                        n_years=nn_h[-1])))
        ph, pf = np.array(ph), np.array(pf)
        ok = (pf <= p["fbm_limit"]) & (ph <= np.maximum(p["heat_limit"], ph[0] + p["heat_rise_tol"]))      # NaN -> False
        pref = np.cumprod(ok, axis=0).astype(bool)
        margin = np.where(pref[0], np.array(delays)[pref.sum(0) - 1], np.nan)
        h0 = r["scan"][0]["heat_overlap"][:, ysel]
        n0 = (~np.isnan(h0)).sum(1)
        lo, hi = wilson(np.nansum(h0, 1), n0)
        wd = r["workable_days"][:, ysel]
        wq, _ = emp_quant(wd, [0.1, 0.5, 0.9], 1)
        rr.append(pd.DataFrame(dict(
            cell_id=cell_ids, crop=crop, period=period, scenario=scenario, model=model, n_years=n0,
            p_heat_overlap=ph[0], p_heat_lo80=lo, p_heat_hi80=hi,
            mean_heat_days_in_window=np.where(n0 > 0, np.nanmean(r["heat_days"][:, ysel], 1), np.nan),
            p_frost_before_maturity=pf[0], adaptation_margin_days=margin,
            flag_vulnerable_m5=ph[0] >= p["heat_limit"],
            workable_days_q10=wq[:, 0], workable_days_q50=wq[:, 1], workable_days_q90=wq[:, 2])))
    return pd.concat(rr, ignore_index=True), pd.concat(ss, ignore_index=True)


def read_deltas(path, cell_ids):
    d = pd.read_parquet(path) if str(path).endswith(".parquet") else pd.read_csv(path)
    need = ["cell_id", "model", "scenario", "month", "d_tmin_c", "d_tmax_c", "pr_ratio"]
    miss = [c for c in need if c not in d.columns]
    if miss:
        sys.exit(f"--deltas lacks columns {miss}; expected {need}")
    out = {}
    for (m, s), g in d.groupby(["model", "scenario"]):
        arr = {k: np.full((len(cell_ids), 12), np.nan) for k in ("tn", "tx", "pr")}
        ci = pd.Index(cell_ids).get_indexer(g["cell_id"])
        ok = ci >= 0
        mi = g["month"].to_numpy(int)[ok] - 1
        arr["tn"][ci[ok], mi] = g["d_tmin_c"].to_numpy()[ok]
        arr["tx"][ci[ok], mi] = g["d_tmax_c"].to_numpy()[ok]
        arr["pr"][ci[ok], mi] = g["pr_ratio"].to_numpy()[ok]
        out[(m, s)] = arr
    return out


def run_chronoshift(D, hist, crops, p, calib, out: Path, target_year, deltas_path):
    out.mkdir(parents=True, exist_ok=True)
    cell_ids, meta = D["cell_ids"], D["meta"]
    if hist is not None:
        cube, years = history_cube(hist, cell_ids)
        src = "history"
    else:
        cube, years, src = D["cube"], D["years"], "dataset"
    years = list(years)
    ny = len(years)
    log(f"ChronoShift on {src}: {ny} years ({years[0]}-{years[-1]}), {len(cell_ids)} cells")
    if ny < p["min_years_ml"]:
        log(f"  WARNING: only {ny} years -> quantile models limited to climatology/trend; results NOT calibrated")
    res = season_core_chunked(cube["tmin_c"], cube["tmax_c"], cube["pr_mm"], crops, p, calib)
    tmean = (cube["tmin_c"] + cube["tmax_c"]) / 2
    cs = np.nanmean(tmean[..., :90], -1)
    cs = np.where((~np.isnan(tmean[..., :90])).mean(-1) >= 0.8, cs, np.nan)

    # event table
    ev = event_arrays(res, crops)
    wide = pd.DataFrame({"cell_id": np.repeat(cell_ids, ny), "year": np.tile(years, len(cell_ids))})
    for k, a in ev.items():
        wide[k.replace(":", "_")] = a.ravel() + 1
    for k in ("last_spring_frost_censored", "first_autumn_frost_censored"):
        wide[k] = res["common"][k].ravel()
    for c in crops:
        wide[f"{c}_workable_days"] = res[c]["workable_days"].ravel()
        wide[f"{c}_sow"] = res[c]["sow"].ravel() + 1
        wide[f"{c}_heat_days"] = res[c]["heat_days"].ravel()
    wide.to_parquet(out / "events_cell_year.parquet", index=False)

    # quantile models -> windows for target year
    win_rows, ev_rows = [], []
    for name, arr in ev.items():
        panel = build_panel(arr, cell_ids, years, meta, cs)
        if panel.empty:
            continue
        pred, evd = fit_event_quantiles(panel, name, p, target_year)
        win_rows.append(pred)
        ev_rows.append(evd)
    windows = pd.concat(win_rows, ignore_index=True)
    # derived sowing date = first workable + lag (clipped to the planting window)
    sow_rows = []
    for c in crops:
        sub = windows[windows["event"] == f"{c}:first_ready"].copy()
        lag = calib.get("sow_lag", {}).get(c, p["sow_lag_days"])
        e0, e1 = md_to_idx(crops[c]["earliest_md"]), md_to_idx(crops[c]["latest_md"])
        for q in [f"q{int(x * 100)}" for x in p["quantiles"]]:
            sub[q] = np.clip(sub[q] + lag, e0, e1)
        sub["event"] = f"{c}:sow"
        sow_rows.append(sub)
    windows = pd.concat([windows] + sow_rows, ignore_index=True)
    qcols = [f"q{int(x * 100)}" for x in p["quantiles"]]
    windows = add_dates(windows, qcols)
    windows["period"], windows["scenario"], windows["model"] = "now", "obs", "obs"
    windows["target_year"], windows["n_years_fit"] = target_year, ny
    cidx = {c: i for i, c in enumerate(cell_ids)}
    cens = {"last_spring_frost": res["common"]["last_spring_frost_censored"].mean(1),
            "first_autumn_frost": res["common"]["first_autumn_frost_censored"].mean(1)}
    ci_ = windows["cell_id"].map(cidx).to_numpy()
    windows["censored_share"] = 0.0
    for ev_name, arr in cens.items():
        m_ = (windows["event"] == ev_name).to_numpy()
        windows.loc[m_, "censored_share"] = arr[ci_[m_]]
    windows["calibrated"] = ny >= p["min_years_ml"]
    evaldf = pd.concat(ev_rows, ignore_index=True) if ev_rows else pd.DataFrame()
    evaldf.to_csv(out / "eval_quantile_models.csv", index=False)

    # risk now: last `normal_years`
    ysel = np.zeros(ny, bool)
    ysel[-min(p["normal_years"], ny):] = True
    risk, scan = summarize_risk(res, cell_ids, ysel, crops, p, "now")
    risk["n_years_note"] = np.where(risk["n_years"] < p["min_years_ml"], "few years - not calibrated", "")

    # future with CMIP6 deltas on the baseline years
    fut_win, fut_risk, fut_scan = [], [], []
    if deltas_path:
        dl = read_deltas(deltas_path, cell_ids)
        log(f"applying {len(dl)} CMIP6 model x scenario delta sets to {ysel.sum()} baseline years")
        sl = np.where(ysel)[0]
        base = {k: v[:, sl] for k, v in cube.items()}
        mi = MONTH_OF_IDX
        for (m, s), a in dl.items():
            tn = base["tmin_c"] + a["tn"][:, mi][:, None, :]
            tx = base["tmax_c"] + a["tx"][:, mi][:, None, :]
            pr = base["pr_mm"] * a["pr"][:, mi][:, None, :]
            r2 = season_core_chunked(tn, tx, pr, crops, p, calib)
            allm = np.ones(len(sl), bool)
            rk, sc = summarize_risk(r2, cell_ids, allm, crops, p, "2040", s, m)
            fut_risk.append(rk)
            fut_scan.append(sc)
            for name, arr in event_arrays(r2, crops).items():
                q, n = emp_quant(arr, p["quantiles"])
                d = pd.DataFrame(q, columns=qcols)
                d.insert(0, "cell_id", cell_ids)
                d["event"], d["n_years"] = name, n
                d["method"], d["period"], d["scenario"], d["model"] = "cmip6_delta", "2040", s, m
                fut_win.append(add_dates(d, qcols))
    if fut_risk:
        fr = pd.concat(fut_risk, ignore_index=True)
        risk = pd.concat([risk, fr], ignore_index=True)
        scan = pd.concat([scan] + fut_scan, ignore_index=True)
        windows = pd.concat([windows] + fut_win, ignore_index=True)
        summ = (fr.groupby(["cell_id", "crop", "scenario"])
                  .agg(p_heat_min=("p_heat_overlap", "min"), p_heat_max=("p_heat_overlap", "max"),
                       p_heat_median=("p_heat_overlap", "median"), margin_min=("adaptation_margin_days", "min"),
                       margin_max=("adaptation_margin_days", "max"), n_models=("model", "nunique")).reset_index())
        summ.to_parquet(out / "risk_2040_across_models.parquet", index=False)
    else:
        log("  no --deltas: 2040 windows skipped (needs NEX-GDDP-CMIP6 delta table)")
    windows.to_parquet(out / "windows_cell.parquet", index=False)
    risk.to_parquet(out / "risk_cell.parquet", index=False)
    scan.to_parquet(out / "delay_scan_cell.parquet", index=False)
    log(f"ChronoShift written to {out}")
    return res, years, cube


# =====================================================================================
# 5. FALLOW-ZERO  (daily water ledger + LightGBM residual vs SMAP L4)
# =====================================================================================
def ra_mm(lat_deg):
    """Extra-terrestrial radiation (FAO-56 eq. 21) as mm/day equivalent, shape (C,365)."""
    J = np.arange(365) + 1
    dr = 1 + 0.033 * np.cos(2 * np.pi * J / 365)
    dec = 0.409 * np.sin(2 * np.pi * J / 365 - 1.39)
    phi = np.deg2rad(np.asarray(lat_deg, float))[:, None]
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec)[None], -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr[None] * (ws * np.sin(phi) * np.sin(dec)[None]
                                                  + np.cos(phi) * np.cos(dec)[None] * np.sin(ws))
    return ra * 0.408


def hargreaves(tmin, tmax, lat_deg, scale=1.0):
    tm = (tmin + tmax) / 2
    return scale * 0.0023 * (tm + 17.8) * np.sqrt(np.maximum(tmax - tmin, 0)) * ra_mm(lat_deg)[:, None, :]


def calibrate_hs_scale(ds: Dataset, p, table=None):
    """table: DataFrame date, eto, tn, tx, lat (e.g. gridmet_eto_calib.parquet from m3_collect_calibration.py); else the dataset columns."""
    if table is not None and len(table):
        g = table[["date", "eto", "tn", "tx", "lat"]].copy()
        g["date"] = pd.to_datetime(g["date"])
        g = g[g["date"].dt.month.between(4, 10)].reset_index(drop=True)      # same Apr-Oct window as the dataset
        src = f"gridMET table, {g['date'].dt.year.nunique()} yr"
    else:
        g = ds.gridmet_eto_state_mean()
        src = "dataset gridMET columns"
    if g is None or g.empty:
        return 1.0, "no gridMET ETo (dataset or --gridmet-table) -> scale 1.0"
    g["date"] = pd.to_datetime(g["date"])
    hs = 0.0023 * ((g.tn + g.tx) / 2 + 17.8) * np.sqrt(np.maximum(g.tx - g.tn, 0)) * \
        ra_mm(g["lat"].to_numpy())[np.arange(len(g)), std_idx(g["date"])[0]]
    ok = hs.notna() & g.eto.notna() & (hs > 0)
    s = float(g.eto[ok].sum() / hs[ok].sum())
    sc = float(np.clip(s, 0.5, 1.5))
    return sc, f"Hargreaves x{sc:.3f} fitted to gridMET ETo ({src}, Apr-Oct; raw ratio {s:.3f}{', CLIPPED - check units' if sc != s else ''})"


def ledger_step(S, snow, P, tmean, eto, kc, awc, p):
    cold = tmean < 0
    snow = snow + np.where(cold, P, 0.0)
    melt = np.minimum(snow, p["snow_ddf"] * np.maximum(tmean, 0.0))
    snow = snow - melt
    inflow = np.where(cold, 0.0, P) + melt
    ks = np.clip(S / ((1.0 - p["p_dep"]) * awc), 0.0, 1.0)
    S2 = np.clip(S + inflow - kc * eto * ks, 0.0, awc)
    return S2, snow


CORR_FEATS = ["frac", "P", "tmean", "eto", "doy", "awc", "snow"]


def corr_features(S_pre, snow, P, tmean, eto, d, awc):
    return np.column_stack([S_pre / awc, P, tmean, eto, np.full(S_pre.shape, float(d)), awc, snow])


def apply_corr(model, S_pre, S_new, snow, P, tmean, eto, d, awc):
    r = model.predict(corr_features(S_pre, snow, P, tmean, eto, d, awc), num_threads=1)
    return np.clip(S_new + r, 0.0, awc)


def build_triples(fields):
    return (fields.dropna(subset=["smap_cell_id"]).groupby(["unit_id", "cell_id", "smap_cell_id", "awc_bin_mm"])
            .size().reset_index(name="n_fields"))


def smap_frac_cube(smap, years):
    """SMAP root-zone moisture scaled to 0-1 between the cell's own 2nd and 98th percentile."""
    sc = sorted(smap["smap_cell_id"].unique())
    cub = to_cube(smap.rename(columns={"smap_cell_id": "cell_id"}), ["sm_rz", "lai", "snow", "soilt_k"], sc, years)
    flat = cub["sm_rz"].reshape(len(sc), -1)
    lo, hi = np.nanpercentile(flat, 2, axis=1), np.nanpercentile(flat, 98, axis=1)
    frac = np.clip((cub["sm_rz"] - lo[:, None, None]) / np.maximum(hi - lo, 1e-6)[:, None, None], 0, 1)
    return sc, frac, cub["lai"], cub["snow"]


def rollout_eval(kc_bare, corr, cubes, awc, H, p, years_idx):
    """Bare-soil rollouts started from the SMAP-derived state; absolute error at +H days vs SMAP-derived state.
    cubes holds triple-level arrays (T,Y,365): P_t, T_t, E_t (weather), paw_obs, lai, snow."""
    P, TM, E = cubes["P_t"], cubes["T_t"], cubes["E_t"]
    obs, lai, snw = cubes["paw_obs"], cubes["lai"], cubes["snow"]
    errs = []
    starts = list(range(95, 125, 5)) + list(range(265, 300, 5))
    pp = dict(p, kc_bare=kc_bare)
    for d0 in starts:
        S = obs[:, years_idx, d0].copy()
        okm = ~np.isnan(S)
        for k in range(H + 1):
            okm &= ~np.isnan(obs[:, years_idx, d0 + k]) & (lai[:, years_idx, d0 + k] < p["lai_bare_max"]) & \
                   (np.nan_to_num(snw[:, years_idx, d0 + k]) < p["snow_bare_max"])
        if not okm.any():
            continue
        snow = np.zeros_like(S)
        a = np.broadcast_to(awc[:, None], S.shape)
        for k in range(H):
            d = d0 + k
            Pd, Td = np.nan_to_num(P[:, years_idx, d]), np.nan_to_num(TM[:, years_idx, d], nan=10.0)
            Ed = np.nan_to_num(E[:, years_idx, d])
            S_pre = np.nan_to_num(S)
            S2, snow = ledger_step(S_pre, snow, Pd, Td, Ed, kc_bare, a, pp)
            if corr is not None:
                fl = lambda x: np.asarray(x).ravel()
                S2 = apply_corr(corr, fl(S_pre), fl(S2), fl(snow), fl(Pd), fl(Td), fl(Ed), d, fl(a)).reshape(S2.shape)
            S = S2
        errs.append(np.abs(S - obs[:, years_idx, d0 + H])[okm])
    return np.concatenate(errs) if errs else np.array([])


def run_ledger_calibration(ds: Dataset, D, p, crops, out: Path, gridmet_table=None):
    out.mkdir(parents=True, exist_ok=True)
    smap = ds.smap()
    hs, hs_note = calibrate_hs_scale(ds, p, gridmet_table)
    if smap is None:
        log("ledger-calibrate: dataset has no SMAP columns -> no residual model;", hs_note)
        (out / "ledger_calibration.json").write_text(json.dumps(dict(kc_bare=p["kc_bare"], hs_scale=hs, hs_note=hs_note, use_corrector=False,
                                                                     band_mm=0.0, notes=["no SMAP in dataset"]), indent=1))
        return
    years = D["years"]
    log("ledger-calibrate:", hs_note)
    sc, frac, lai, snw = smap_frac_cube(smap, years)
    trip = build_triples(D["fields"])
    trip = trip[trip["cell_id"].isin(D["cell_ids"]) & trip["smap_cell_id"].isin(sc)]
    if len(trip) > p["calib_max_triples"]:
        trip = trip.sample(p["calib_max_triples"], random_state=0)
    trip = trip.reset_index(drop=True)
    ci = pd.Index(D["cell_ids"]).get_indexer(trip["cell_id"])
    si = pd.Index(sc).get_indexer(trip["smap_cell_id"])
    awc = trip["awc_bin_mm"].to_numpy(float)
    lat = D["meta"]["lat"].to_numpy()
    eto_cell = hargreaves(D["cube"]["tmin_c"], D["cube"]["tmax_c"], lat, hs)
    TMc = (D["cube"]["tmin_c"] + D["cube"]["tmax_c"]) / 2
    cubes = dict(P_t=D["cube"]["pr_mm"][ci], T_t=TMc[ci], E_t=eto_cell[ci],
                 paw_obs=frac[si] * awc[:, None, None], lai=lai[si], snow=snw[si])
    log(f"  {len(trip)} (weather cell, SMAP cell, AWC bin) triples; {len(years)} seasons")

    # ---- one-step training table on bare, snow-free days
    rows = []
    for j in range(len(years)):
        o, l, s_ = cubes["paw_obs"][:, j, :], cubes["lai"][:, j, :], np.nan_to_num(cubes["snow"][:, j, :])
        Pj, Tj, Ej = cubes["P_t"][:, j, :], cubes["T_t"][:, j, :], cubes["E_t"][:, j, :]
        for d in range(0, 364):
            m = ~np.isnan(o[:, d]) & ~np.isnan(o[:, d + 1]) & (l[:, d] < p["lai_bare_max"]) & (l[:, d + 1] < p["lai_bare_max"]) \
                & (s_[:, d] < p["snow_bare_max"]) & ~np.isnan(Pj[:, d]) & ~np.isnan(Tj[:, d])
            if not m.any():
                continue
            rows.append(pd.DataFrame(dict(yi=j, d=d, S_pre=o[m, d], obs_next=o[m, d + 1], P=Pj[m, d], tmean=Tj[m, d],
                                          eto=np.nan_to_num(Ej[m, d]), awc=awc[m])))
    tr = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    log(f"  bare-soil training rows: {len(tr):,}")
    meta = dict(hs_scale=hs, hs_note=hs_note, n_triples=int(len(trip)), n_rows=int(len(tr)), years=[int(y) for y in years], notes=[])
    if len(tr) < 2000:
        meta.update(kc_bare=p["kc_bare"], use_corrector=False, band_mm=0.0)
        meta["notes"].append("too few bare-soil SMAP days (needs low-LAI April / October days): plain ledger, no band")
        (out / "ledger_calibration.json").write_text(json.dumps(meta, indent=1))
        return
    # ---- tune Kc_bare on 14-day rollouts
    H = p["rollout_days"]
    grid = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.70]
    allyears = list(range(len(years)))
    scores = {k: float(np.mean(rollout_eval(k, None, cubes, awc, H, p, allyears))) for k in grid}
    kc_best = min(scores, key=lambda k: scores[k] if np.isfinite(scores[k]) else 1e9)
    meta["kc_grid_mae_mm"] = scores
    meta["kc_bare"] = kc_best
    if kc_best in (grid[0], grid[-1]):
        meta["notes"].append(f"Kc_bare={kc_best} sits at the edge of the search grid - ledger physics may be off (ETo scale, SMAP range)")
    log(f"  Kc_bare grid MAE(+{H}d): " + ", ".join(f"{k}:{v:.1f}" for k, v in scores.items()) + f"  -> {kc_best}")
    pp = dict(p, kc_bare=kc_best)
    # ---- residual target with tuned Kc, fit with leave-one-year-out CV
    S2, _ = ledger_step(tr["S_pre"].to_numpy(), np.zeros(len(tr)), tr["P"].to_numpy(), tr["tmean"].to_numpy(),
                        tr["eto"].to_numpy(), kc_best, tr["awc"].to_numpy(), pp)
    tr["resid"] = tr["obs_next"].to_numpy() - S2
    X = corr_features(tr["S_pre"].to_numpy(), np.zeros(len(tr)), tr["P"].to_numpy(), tr["tmean"].to_numpy(),
                      tr["eto"].to_numpy(), 0, tr["awc"].to_numpy())
    X[:, 4] = tr["d"].to_numpy()
    if len(tr) > p["calib_max_rows"]:
        idx = np.random.default_rng(0).choice(len(tr), p["calib_max_rows"], replace=False)
    else:
        idx = np.arange(len(tr))

    def fit(rows_idx):
        m = lgb.LGBMRegressor(n_estimators=150, learning_rate=0.05, num_leaves=7, min_child_samples=200,
                              subsample=0.8, subsample_freq=1, reg_lambda=5.0, random_state=0, verbose=-1)
        m.fit(pd.DataFrame(X[rows_idx], columns=CORR_FEATS), tr["resid"].to_numpy()[rows_idx])
        return m

    cv, use = [], False
    final = None
    if lgb is not None and len(years) >= 2:
        for j in range(len(years)):
            trn = idx[tr["yi"].to_numpy()[idx] != j]
            if len(trn) < 1000:
                continue
            mdl = fit(trn)
            booster = _Wrap(mdl)
            e_plain = rollout_eval(kc_best, None, cubes, awc, H, p, [j])
            e_corr = rollout_eval(kc_best, booster, cubes, awc, H, p, [j])
            if len(e_plain) and len(e_corr):
                cv.append(dict(heldout_year=int(years[j]), mae_plain_mm=float(e_plain.mean()), mae_corrected_mm=float(e_corr.mean()),
                               rmse_plain_mm=float(np.sqrt((e_plain ** 2).mean())), rmse_corrected_mm=float(np.sqrt((e_corr ** 2).mean())),
                               n=int(len(e_plain))))
        cvdf = pd.DataFrame(cv)
        cvdf.to_csv(out / "ledger_cv.csv", index=False)
        if len(cvdf):
            use = bool(cvdf["mae_corrected_mm"].mean() < 0.98 * cvdf["mae_plain_mm"].mean())
            meta["cv_mae_plain_mm"], meta["cv_mae_corrected_mm"] = float(cvdf["mae_plain_mm"].mean()), float(cvdf["mae_corrected_mm"].mean())
            band = float(cvdf["rmse_corrected_mm" if use else "rmse_plain_mm"].mean())
            meta["band_mm"] = band
            log(f"  rollout +{H}d MAE: plain {meta['cv_mae_plain_mm']:.1f} mm vs corrected {meta['cv_mae_corrected_mm']:.1f} mm "
                f"-> {'USE residual model' if use else 'ship plain ledger (cut rule)'}; band +-{band:.1f} mm")
        final = fit(idx)
        final.booster_.save_model(str(out / "ledger_corrector.txt"))
    else:
        meta["notes"].append("lightgbm missing or <2 seasons: no residual model")
    meta.setdefault("band_mm", 0.0)
    meta["use_corrector"] = use
    meta["notes"].append("calibrated on Apr/Oct bare-soil days only; Nov-Mar behaviour (frozen soil, snow) is NOT validated")
    (out / "ledger_calibration.json").write_text(json.dumps(meta, indent=1))
    log(f"  calibration written to {out}")


class _Wrap:
    """Make an LGBMRegressor look like what apply_corr needs."""
    def __init__(self, m):
        self.m = m

    def predict(self, X, num_threads=1):
        return self.m.predict(pd.DataFrame(X, columns=CORR_FEATS))


def load_corrector(out: Path):
    cal = json.loads((out / "ledger_calibration.json").read_text()) if (out / "ledger_calibration.json").exists() else {}
    model = None
    if cal.get("use_corrector") and (out / "ledger_corrector.txt").exists() and lgb is not None:
        b = lgb.Booster(model_file=str(out / "ledger_corrector.txt"))

        class _B:
            def predict(self, X, num_threads=1):
                return b.predict(X, num_threads=num_threads)
        model = _B()
    return cal, model


def crop_kc(sow, flower, mature, harvest_idx, cp, kc_bare):
    """(C,Y) arrays -> kc (C,Y,365) piecewise-linear crop curve between sowing and harvest; bare elsewhere."""
    C, Y = sow.shape
    kc = np.full((C, Y, 365), kc_bare)
    d = np.arange(365)
    for c in range(C):
        for y in range(Y):
            s, f, m = sow[c, y], flower[c, y], mature[c, y]
            if np.isnan(s):
                continue
            h = harvest_idx
            if np.isnan(f):
                f = s + 70
            if np.isnan(m):
                m = h - 15
            anchors = dict(sow=s, flower=f, mature=m, harvest=max(h, m + 7))
            xs = np.maximum.accumulate(np.array([anchors[a] + off for a, off, _ in cp["kc_knots"]], float))
            xs = xs + np.arange(len(xs)) * 1e-6
            ys = np.array([k for _, _, k in cp["kc_knots"]], float)
            seg = (d >= xs[0]) & (d <= xs[-1])
            kc[c, y, seg] = np.interp(d[seg], xs, ys)
    return kc


def run_track(P, TM, ETO, KC, BARE, cu, awc, sow_next, hidx, p, corr, snow0=0.0):
    """Continuous bare-off-season ledger for a monoculture track.
    Returns S_h (Y,U) state at harvest and S_sow (Y,U) state at the next crop's sowing day (spring of year y)."""
    C, Y, _ = P.shape
    U = len(cu)
    S = 0.8 * awc
    snow = np.zeros(U)
    S_h = np.full((Y, U), np.nan)
    S_sow = np.full((Y, U), np.nan)
    for y in range(Y):
        sow_u = sow_next[cu, y]
        for d in range(365):
            if d == hidx:
                S_h[y] = S
            hit = sow_u == d
            if hit.any():
                S_sow[y, hit] = S[hit]
            Pd, Td, Ed = P[cu, y, d], TM[cu, y, d], ETO[cu, y, d]
            S_pre = S
            S, snow = ledger_step(S_pre, snow, Pd, Td, Ed, KC[cu, y, d], awc, p)
            if corr is not None:
                bare = BARE[cu, y, d]
                if bare.any():
                    S = np.where(bare, apply_corr(corr, S_pre, S, snow, Pd, Td, Ed, d, awc), S)
    return S_h, S_sow


def run_cover(S_h, P, TM, ETO, cu, awc, sow_next, hidx, lead, p, corr):
    """Rye cover started at harvest (+seed lag) from the bare track's harvest state; returns S at sowing (Y,U)."""
    C, Y, _ = P.shape
    U = len(cu)
    R = p["rye"]
    S_sow = np.full((Y, U), np.nan)
    for y in range(Y - 1):
        S = S_h[y].copy()
        snow = np.zeros(U)
        gcum = np.zeros(U)
        sow_u = sow_next[cu, y + 1]
        term_u = sow_u - lead
        seed_t = hidx + R["seed_lag_days"]
        for t in range(hidx, 365 + int(sow_u.max()) + 1):
            yy, d = y + t // 365, t % 365
            if yy == y + 1:
                hit = sow_u == d
                if hit.any():
                    S_sow[y + 1, hit] = S[hit]
            Pd, Td, Ed = P[cu, yy, d], TM[cu, yy, d], ETO[cu, yy, d]
            if t >= seed_t:
                gcum = gcum + np.maximum(Td - R["gdd_base"], 0.0)
            alive = np.full(U, t >= seed_t)
            if yy == y + 1:
                alive &= d < term_u
            kc = np.where(alive, p["kc_bare"] + (R["kc_max"] - p["kc_bare"]) * np.clip(gcum / R["gdd_full"], 0, 1), p["kc_bare"])
            S_pre = S
            S, snow = ledger_step(S_pre, snow, Pd, Td, Ed, kc, awc, p)
            if corr is not None:
                S = apply_corr(corr, S_pre, S, snow, Pd, Td, Ed, d, awc)
    return S_sow


def run_fallow_zero(ds, D, hist, crops, p, calib, out: Path, cal_dir: Path):
    out.mkdir(parents=True, exist_ok=True)
    if hist is None:
        log("fallow-zero: --history (full-year daily weather, many years) is required -> SKIPPED. "
            "The dataset only holds Apr-Oct of 3 seasons; harvest -> spring water balance and weather-year scenarios need more.")
        return
    cal, corr = load_corrector(cal_dir)
    p = dict(p)
    p["kc_bare"] = cal.get("kc_bare", p["kc_bare"])
    p["hs_scale"] = cal.get("hs_scale", p["hs_scale"])
    band = float(cal.get("band_mm", 0.0))
    if not cal:
        log("  NOTE: no ledger_calibration.json (run ledger-calibrate first): plain ledger, band 0")
    cell_ids, meta = D["cell_ids"], D["meta"]
    cube, years = history_cube(hist, cell_ids)
    Y = len(years)
    if Y < p["min_scenario_years"]:
        log(f"fallow-zero: only {Y} history years (< {p['min_scenario_years']}) -> SKIPPED")
        return
    log(f"Fallow-Zero: {Y} weather years {years[0]}-{years[-1]}; residual model: {'ON' if corr else 'off'}; band +-{band:.1f} mm")
    miss_cells = np.isnan(cube["tmin_c"]).all(axis=(1, 2))
    tm = (cube["tmin_c"] + cube["tmax_c"]) / 2
    P = np.nan_to_num(cube["pr_mm"])
    TM = np.nan_to_num(tm, nan=5.0)
    ETO = np.nan_to_num(hargreaves(cube["tmin_c"], cube["tmax_c"], meta["lat"].to_numpy(), p["hs_scale"]))
    res = season_core_chunked(cube["tmin_c"], cube["tmax_c"], cube["pr_mm"], crops, p, calib)
    f = D["fields"]
    units = f.groupby(["unit_id", "cell_id", "awc_bin_mm"]).size().reset_index(name="n_fields")
    units["ci"] = pd.Index(cell_ids).get_indexer(units["cell_id"])
    units = units[(units["ci"] >= 0)].copy()
    units = units[~miss_cells[units["ci"].to_numpy()]].reset_index(drop=True)
    cu, awc = units["ci"].to_numpy(), units["awc_bin_mm"].to_numpy(float)
    U = len(units)
    thr = p["paw_threshold_frac"] * awc
    rows, val_rows = [], []
    sp = p["spin_years"]
    for track in crops:                                 # crop that was just harvested
        nxt = OTHER[track]
        cp_t, cp_n = crops[track], crops[nxt]
        hidx = int(round(calib.get("harvest_idx", {}).get(track, md_to_idx(cp_t["harvest_md"]))))
        e1n = md_to_idx(cp_n["latest_md"])
        sow_n = np.where(np.isnan(res[nxt]["sow"]), e1n, res[nxt]["sow"]).astype(int)
        KC = crop_kc(res[track]["sow"], res[track]["flower"], res[track]["mature"], hidx, cp_t, p["kc_bare"])
        BARE = KC <= p["kc_bare"] + 1e-9
        S_h, S_A = run_track(P, TM, ETO, KC, BARE, cu, awc, sow_n, hidx, p, corr)
        S_B = run_cover(S_h, P, TM, ETO, cu, awc, sow_n, hidx, cp_n["cover_term_lead_days"], p, corr)
        aut_end = md_to_idx([11, 30])
        cs_ = np.concatenate([np.zeros((P.shape[0], Y, 1)), np.cumsum(P, -1)], -1)
        rain_aut = cs_[:, :, aut_end + 1] - cs_[:, :, hidx]                    # (C,Y) harvest -> Nov 30
        ys = np.arange(sp + 1, Y)                                        # spring years with a completed autumn before
        # autumn rain needed for the cover branch to be "safe" (P(shortfall | rain >= R) <= m9_limit)
        safe = {}
        for u in range(U):
            v, rn = S_B[ys, u], rain_aut[cu[u], ys - 1]
            ok = ~np.isnan(v)
            v, rn = v[ok], rn[ok]
            if len(v) < p["min_scenario_years"] - 2:
                continue
            order = np.argsort(-rn)
            sh = (v[order] < thr[u]).astype(float)
            cm = np.cumsum(sh) / np.arange(1, len(sh) + 1)               # P(shortfall | rain >= rn_sorted[i])
            okk = np.where((cm <= p["m9_limit"]) & (np.arange(1, len(sh) + 1) >= 8))[0]
            r_star = 0.0 if cm[-1] <= p["m9_limit"] else (float(rn[order][okk.max()]) if len(okk) else np.nan)
            safe[u] = (r_star, float(np.percentile(rn, 10)),
                       float(np.percentile(rn, 50)), float(np.percentile(rn, 90)))
        for branch, S in (("bare", S_A), ("cover", S_B)):
            for u in range(U):
                v = S[ys, u]
                v = v[~np.isnan(v)]
                if len(v) < p["min_scenario_years"] - 2:
                    continue
                n = len(v)
                k0 = int((v < thr[u]).sum())
                lo, hi = (float(x) for x in wilson(k0, n))
                q = np.percentile(v, [10, 50, 90])
                sf = safe.get(u, (np.nan,) * 4)
                rows.append(dict(
                    unit_id=units.at[u, "unit_id"], cell_id=units.at[u, "cell_id"], awc_mm=awc[u],
                    n_fields=int(units.at[u, "n_fields"]), after_crop=track, next_crop=nxt, branch=branch,
                    n_years=n, paw_sow_q10_mm=q[0], paw_sow_q50_mm=q[1], paw_sow_q90_mm=q[2],
                    paw_sow_frac_q50=q[1] / awc[u], p_shortfall=k0 / n, p_shortfall_lo80=lo, p_shortfall_hi80=hi,
                    p_shortfall_ledger_wet=float((v - band < thr[u]).mean()),     # ledger error band: wetter truth
                    p_shortfall_ledger_dry=float((v + band < thr[u]).mean()),     # drier truth
                    shortfall_threshold_mm=thr[u], ledger_band_mm=band,
                    safe_autumn_rain_mm=sf[0] if branch == "cover" else np.nan,
                    autumn_rain_q10_mm=sf[1], autumn_rain_q50_mm=sf[2], autumn_rain_q90_mm=sf[3],
                    harvest_doy=hidx + 1, residual_model=bool(corr)))
        # ---- validation of the spring state against SMAP L4 (dataset seasons only)
        val_rows += validate_spring(ds, D, units, cu, awc, S_A, sow_n, years, track)
    fz = pd.DataFrame(rows)
    if fz.empty:
        log("fallow-zero: no unit produced enough scenario years")
        return
    # m9 wide + delta
    wide = fz.pivot_table(index=["unit_id", "after_crop"], columns="branch", values="p_shortfall").reset_index()
    wide = wide.rename(columns={"bare": "p_shortfall_bare", "cover": "m9_cover_water_risk"})
    wide["delta_p_cover_minus_bare"] = wide["m9_cover_water_risk"] - wide["p_shortfall_bare"]
    wide["flag_cover_ok_m9"] = wide["m9_cover_water_risk"] <= p["m9_limit"]
    fz.to_parquet(out / "fallow_zero_units.parquet", index=False)
    wide.to_parquet(out / "fallow_zero_m9_units.parquet", index=False)
    # field-level join table (M1 not needed: both 'after corn' and 'after soybeans' are provided)
    fw = wide.pivot(index="unit_id", columns="after_crop", values=["m9_cover_water_risk", "p_shortfall_bare", "flag_cover_ok_m9"])
    fw.columns = [f"{a}_after_{b}" for a, b in fw.columns]
    fld = f[["CSBID", "county_fips", "cell_id", "smap_cell_id", "awc_bin_mm", "unit_id"]].merge(fw.reset_index(), on="unit_id", how="left")
    fld.to_parquet(out / "fallow_zero_field_metrics.parquet", index=False)
    if val_rows:
        pd.DataFrame(val_rows).to_csv(out / "validation_spring_state.csv", index=False)
    log(f"Fallow-Zero written to {out}  ({len(fz):,} unit rows, {len(fld):,} fields)")


def validate_spring(ds, D, units, cu, awc, S_A, sow_n, hist_years, track):
    """Compare bare-track ledger PAW at the sowing day with SMAP-derived PAW for the dataset seasons."""
    smap = ds.smap()
    if smap is None:
        return []
    dyears = D["years"]
    sc, frac, _, _ = smap_frac_cube(smap, dyears)
    trip = build_triples(D["fields"])
    trip = trip[trip["unit_id"].isin(units["unit_id"]) & trip["smap_cell_id"].isin(sc)]
    uidx = pd.Index(units["unit_id"]).get_indexer(trip["unit_id"])
    tsi = pd.Index(sc).get_indexer(trip["smap_cell_id"])
    w = trip["n_fields"].to_numpy(float)
    rows = []
    for j, y in enumerate(dyears):
        if y not in hist_years or (y - 1) not in hist_years:
            continue
        yh = hist_years.index(y)
        idx = sow_n[cu[uidx], yh]
        v = frac[tsi, j, idx]
        ok = ~np.isnan(v)
        num = np.bincount(uidx[ok], weights=(v * w)[ok], minlength=len(units))
        den = np.bincount(uidx[ok], weights=w[ok], minlength=len(units))
        obs = np.where(den > 0, num / np.maximum(den, 1e-9), np.nan) * awc
        mod = S_A[yh]
        m = ~np.isnan(obs) & ~np.isnan(mod)
        if m.sum() < 5:
            continue
        const = np.nanmedian(obs[m])
        r = float(np.corrcoef(obs[m], mod[m])[0, 1]) if np.std(mod[m]) > 0 and np.std(obs[m]) > 0 else np.nan
        rows.append(dict(spring_year=int(y), after_crop=track, n_units=int(m.sum()), mae_mm=float(np.mean(np.abs(mod[m] - obs[m]))),
                         bias_mm=float(np.mean(mod[m] - obs[m])), pearson_r=r,
                         mae_constant_baseline_mm=float(np.mean(np.abs(const - obs[m]))),
                         note="ledger (bare track) vs SMAP-derived PAW at the modelled sowing day"))
    return rows


# =====================================================================================
# 6. DATA-READINESS REPORT
# =====================================================================================
def readiness(ds: Dataset, p, hist, deltas, out: Path, nass_table=None, gridmet_table=None):
    out.mkdir(parents=True, exist_ok=True)
    L = []
    cov = ds.date_coverage()
    L.append("M3 DATA READINESS")
    L.append("=" * 70)
    L.append("Dataset coverage:")
    for _, r in cov.iterrows():
        L.append(f"  {int(r['year'])}: {str(r['first_date'])[:10]} .. {str(r['last_date'])[:10]}  "
                 f"({int(r['n_days'])} days, {int(r['n_fields']):,} fields)")
    m = ds.m
    items = [
        ("daily tmin/tmax/precip for the chosen cell source", all(c in ds.cols for c in m.values()), "ChronoShift, Fallow-Zero"),
        ("SMAP L4 root-zone moisture (+LAI, snow)", ds.has("smap_sm_rootzone", "smap_cell_id"), "ledger calibration, validation"),
        ("SSURGO available water storage 0-100 cm", ds.has("ssurgo_aws_0_100_mm"), "Fallow-Zero units"),
        ("NASS crop-progress dates (planted/silking/mature/harvest)", (any(c.startswith("nass_") for c in ds.cols) or bool(nass_table)), "phenology calibration (replaces M1)"),
        ("gridMET reference ET (to calibrate Hargreaves)", (ds.has("gridmet_eto_grass_mm") or bool(gridmet_table)), "ETo scale"),
    ]
    L.append("\nColumns:")
    for name, ok, use in items:
        L.append(f"  [{'OK ' if ok else 'MISSING'}] {name}  -> {use}")
    L.append("\nHard limits of the dataset:")
    short = (pd.to_datetime(cov["first_date"]).dt.month.min() > 1) or (pd.to_datetime(cov["last_date"]).dt.month.max() < 12)
    L.append(f"  [{'LIMIT' if short else 'OK   '}] season window is partial (no Nov-Mar): last spring frost can be censored, "
             f"first autumn frost can be censored, the harvest->spring water ledger cannot be run")
    L.append(f"  [{'LIMIT' if len(cov) < p['min_years_ml'] else 'OK   '}] {len(cov)} season(s) in dataset; quantile models need >= {p['min_years_ml']}")
    if hist is not None:
        hy = hist["date"].dt.year
        L.append(f"  [OK   ] --history: {hy.min()}-{hy.max()} ({hy.nunique()} years, {hist['cell_id'].nunique()} cells)")
    else:
        L.append("  [MISSING] --history (full-year daily weather per cell, 1981-present)")
    L.append(f"  [{'OK   ' if deltas else 'MISSING'}] --deltas (NEX-GDDP-CMIP6 monthly deltas per cell, model, scenario)")
    txt = "\n".join(L)
    (out / "data_readiness.txt").write_text(txt)
    print(txt)


# =====================================================================================
# 7. CLI
# =====================================================================================
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "chronoshift", "ledger-calibrate", "fallow-zero", "all"])
    ap.add_argument("--dataset", required=True, help="folder with <year>/<county>.parquet (or one parquet file)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--history", help="parquet/csv: cell_id,date,tmin_c,tmax_c,pr_mm (full years, e.g. POWER 1981-2025)")
    ap.add_argument("--nass-table", help="nass_stage_dates.parquet from m3_collect_calibration.py (state-year stage dates, any years)")
    ap.add_argument("--gridmet-table", help="gridmet_eto_calib.parquet from m3_collect_calibration.py (ETo scale factor)")
    ap.add_argument("--deltas", help="parquet/csv: cell_id,model,scenario,month,d_tmin_c,d_tmax_c,pr_ratio")
    ap.add_argument("--params", help="json overriding DEFAULTS / crops")
    ap.add_argument("--cell-source", choices=["power", "gridmet"])
    ap.add_argument("--target-year", type=int, help="year the windows are forecast for (default: last data year + 1)")
    a = ap.parse_args()

    p, crops = load_params(a.params)
    if a.cell_source:
        p["cell_source"] = a.cell_source
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ds = Dataset(a.dataset, p)
    hist = load_history(a.history)
    readiness(ds, p, hist, a.deltas, out, a.nass_table, a.gridmet_table)
    if a.cmd == "check":
        return
    D = prepare(ds, p)
    D["fields"].to_parquet(out / "field_index.parquet", index=False)
    Dcal = calibration_view(D, hist, load_nass_table(a.nass_table), p)
    gtab = pd.read_parquet(a.gridmet_table) if a.gridmet_table else None
    calib = calibrate_from_nass(Dcal, crops, p)
    (out / "chronoshift").mkdir(exist_ok=True)
    (out / "chronoshift" / "calibration_nass.json").write_text(json.dumps(calib, indent=1))
    log("NASS calibration:", {k: calib[k] for k in ("sow_lag", "gdd_flower", "gdd_mature", "harvest_idx")})
    for n in calib["notes"]:
        log("  note:", n)
    yrs = sorted(hist["date"].dt.year.unique()) if hist is not None else D["years"]
    ty = a.target_year or int(max(yrs)) + 1

    if a.cmd in ("chronoshift", "all"):
        validate_nass(Dcal, crops, p, calib).to_csv(out / "chronoshift" / "validation_nass.csv", index=False)
        run_chronoshift(D, hist, crops, p, calib, out / "chronoshift", ty, a.deltas)
    if a.cmd in ("ledger-calibrate", "all"):
        run_ledger_calibration(ds, D, p, crops, out / "fallow_zero", gtab)
    if a.cmd in ("fallow-zero", "all"):
        run_fallow_zero(ds, D, hist, crops, p, calib, out / "fallow_zero", out / "fallow_zero")
    log("done")


if __name__ == "__main__":
    main()
