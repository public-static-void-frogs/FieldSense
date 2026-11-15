#!/usr/bin/env python3
"""M2 - Neighbour Evidence Engine (CropTwin Detective + CausalSoil).

Question: among fields like mine, did those with a different rotation history hold up better in past drought years, and what does that
imply for my field?  Observational causal estimate from satellite outcomes of neighbouring fields that shared the same weather.

ADAPTED to the Field Shift datasets (Iowa CSB fields; the original read the analysis-script folder layout 05-19). Inputs:
  --attrs  <work>/attrs            csb_pipeline.py ingest: CSBID, STATEFIPS, CNTYFIPS, CSBACRES, centroid_lon/lat, CDL<yyyy>   -> crop_t, crop_t1..crop_t5,
                                   county, area, location. History length = the CDL years in the data (CSB 2025 edition: 2018-2025).
  --ts     <ts_YYYY> ...           crop_ts_s1.py compose output (folder with dataset/tabular.parquet, the file, or a glob), one per year:
                                   CSBID, year, n_observed_steps, ndvi_d1..16, ndwi_d1..16 (16 steps over 1 Apr - 31 Oct) -> outcomes Y1
  --drought weekly.parquet         csb_drought.py weekly: CSBID, valid_date, dm  -> usdm_drought_season = D2+ in >= --drought-weeks (4) July-August maps
  optional (a missing option only removes what it feeds):
  --ssurgo ssurgo_field.parquet    ext_soil_ssurgo.py: field soil (AWC 0-100 / 0-150 mm, OM, clay, sand, slope) -> covariates + heterogeneity of the forest
  --power-daily + --cellmap-power  POWER daily + CSBID -> cell map: heat days (T2M_MAX >= 35 C) July-August (context column in the table)
  --smap-daily + --cellmap-smap    smap_daily.parquet (csb_smap.py, ideally 2015-2025): July-August root-zone moisture, its rank among the years of the
                                   cell, days below the cell's own 20th percentile -> context; with --drought-def smap|either also the drought label
  --nass-yield nass_yield.parquet  yield_nass.py: county check (aggregate validation)
  --covariates / --winter-cover / --crop-labels / --openet / --ecostress / --cdl-extra   as in the original (see the argument help)
  Not in your datasets, so skipped: ECOSTRESS (Y2), OpenET (Y3), yield proxy, NASADEM terrain, M1 winter-cover (T4 needs --winter-cover), csr2.

SAMPLE DESIGN MATTERS. The effects are estimated between fields of the same 20 km square, crop and year, so you need MANY fields per square-year in both
  arms. crop_ts_s1.py `sample` draws a different class-balanced sample for every year; for M2 use ONE field list for all years: run `sample` once, copy its
  fields.parquet into every ts_<year> folder, then extract + compose per year (the tensors of one CSBID then exist in each year, which also gives the
  pre-treatment greenness t-2, t-3 and the negative-control check; without repeated fields those two are skipped). Sample corn and soybean fields
  (crop_id 1, 5) of the counties you care about, thousands per county rather than hundreds. `check` prints how many field-years each arm has.
MEMORY / TEMP FILES. Reading is batched: --ts files are read in --chunk-rows batches and the 32 tensor columns are cut to 5 outcome columns per batch;
  attrs / drought / POWER / SMAP joins run in DuckDB with a hard --memory limit (default 4GB) and spill to --tmp (default <out>/_tmp); propensity matching works
  in blocks of ~2M treated x control cells (no n x n x p arrays); the forest predicts and counts neighbours in blocks and writes every field-level result to
  <out>/_tmp/field_effects/*.parquet, merged block by block at the end. The prepared field-year table is saved as <out>/field_year_table.parquet:
  --reuse-table re-runs the models without reading any input again. What still sits in RAM: the field-year table of one crop (~ rows x 25 columns) and the
  DML / forest fits on it (HistGradientBoosting / EconML), so for a very large sample run one crop at a time (--crops corn, then --crops soybeans).
HISTORY LENGTH. T2 uses t-1..t-5 (--t2-window 5); CSB 2018-2025 gives that only for t >= 2023. The default here is --t2-window 3 (t >= 2021).
  Longer history: pass --cdl-extra (parquet CSBID, year, cdl; e.g. from crop_history_*.py) to add earlier years.
Drought seasons in Iowa 2018-2025 are few (2020, 2021 regionally, 2022 and 2023 in places): the drought-specific effect gamma rests on those years.

Design (proposal 4.3)
  unit      field x season of ONE crop (corn, soybeans); comparisons only within the same crop and the same weather stratum x year.
  drought   field's USDM drought season (D2+ in >= 4 July-August maps, 07); every other season is "normal".
  treatments  T1 continuous crop vs rotated | T2 >=3 crop groups in t-5..t-1 vs 1-2 | T3 small grain / hay in t-3..t-1 vs absent |
              T4 winter cover p>=0.7 vs <=0.3 (needs M1 table) | T5 host return interval >=2 y vs 1 y.   Sign convention: the treated arm is the first.
  outcomes  Y1 greenness (peak NDVI, July-August NDWI, late NDVI, NDVI area)   Y2 ECOSTRESS ESI (+ET)   Y3 OpenET (optional)
            + field yield proxy from 19 (arm gaps only: its drought effect is not identified by construction)
  adjustment  fixed effects stratum (--grid-km square, 20 km) x year, plus covariates: log area, location, pre-treatment greenness
            (t-2, t-3), soil / terrain if supplied.
  estimators  (a) matching baseline: nearest neighbour inside stratum x year, ATT + standardised mean differences
              (b) double machine learning, partially linear, cross-fitted by square, gradient-boosting nuisance models, FE-demeaned;
                  effect in drought seasons (theta_d), in normal seasons (theta_n), and the drought-specific effect gamma = theta_d - theta_n
                  with cluster-robust and cluster-bootstrap intervals
              (c) causal forest (EconML) on drought seasons: conditional effect by soil water capacity, drought intensity, size ->
                  field-level what-if with 95% interval, comparable fields within 30 km, or "insufficient evidence"
  checks    covariate balance (|SMD| < 0.1) | overlap (propensity in 0.05-0.95, both arms inside a stratum-year) | permutation placebo for gamma |
            negative-control outcome (pre-treatment greenness) | sensitivity dropping uncertain seasons | sign vs the expected resilience direction
            | county yield check (aggregate, NASS)
  Output wording: "Adjusted association from observational satellite data".  Limits are written on every output (see LIMITS).

OUTPUT FILES (--out) AND HOW TO READ THEM
  effects.csv             one row per crop x treatment x outcome. theta_normal = effect of the treated arm in normal seasons (the usual gap);
                          theta_drought = its effect in drought seasons; gamma = theta_drought - theta_normal = the extra effect that shows up only in
                          drought, for neighbours under the same weather (95% cluster-bootstrap interval gamma_lo..gamma_hi). Outcome units: NDWI / NDVI
                          / ESI index points (ndvi_area: NDVI x days). Expected sign of gamma for "more resilient": T1 negative, T2-T5 positive
                          (sign_agrees_with_expected). Compare with match_gamma (matched baseline) and gamma_linear_fe (plain FE regression): if all
                          three agree in sign the result is not an artefact of the estimator.
                          verdict: "supported (all checks pass)" = interval excludes 0, placebo p < 0.1, negative control passes, matched SMD < 0.1;
                          "supported by the DML model; matched baseline not fully balanced"; "interval excludes 0, but placebo or negative control fails";
                          "no detectable drought-specific effect"; "arm gap only" (yield proxy: drought effect not identified); "abstain" + abstain_reason.
                          EVIDENCE TIERS (graceful degradation; thin data gives a weaker, labelled answer instead of no answer). evidence_tier / confidence /
                          tier_note say which one a row got; headline_effect, headline_lo, headline_hi, headline_basis are the single number to show:
                            full             both season types >= --min-arm fields per arm and >= --min-units squares, overlap ok.   confidence high / medium
                            limited          both season types >= --soft-arm (20) and --soft-units (2): same estimators, small sample, wide intervals. low
                            one season type  only drought OR normal seasons are big enough: effect for that season type, gamma NOT identified.        low
                            pooled           >= --pooled-arm (10) fields per arm over ALL seasons: one pooled effect, no drought split.            low
                            descriptive      >= 1 field-year per arm: within-square-year arm gap (raw gap if none), n shown, NOT a causal estimate.  very low
                            abstain          an arm has no field-year at all, or --strict (old behaviour).
                          With < 60 rows or < 4 squares the ML adjustment is dropped (method = "FE regression, no ML adjustment"); with < 3 squares carrying
                          the variation no interval is given (lo / hi empty). Show tier and confidence next to every number.
                          adjusted_for = which other rotation-history indicators were held fixed (T2 and T3 are nested: when holding both fixed
                          breaks overlap, the weaker adjustment is used and adjustment_note says so - then their effects are not separable).
                          few_clusters = fewer than 10 squares: trust the bootstrap interval, not the standard error.
  outcome_diagnostics.csv does each outcome see the drought at all? (drought_coef in SD of normal-year fields; an outcome with |sd_units| < 1
                          cannot show a rotation difference in drought).
  balance.csv             standardised mean difference per covariate before / after matching. field_year_table.parquet = the analysis table.
  field_effects.parquet   CausalSoil what-if per field x treatment x outcome: effect_drought = conditional drought-season effect of the treated arm at
                          this field's own covariates, lo95 / hi95, n_comparable_treated / control within 30 km (_30km columns) and within the radius
                          actually used (_used, radius_used_km: widened 30 -> 60 -> 120 km while a neighbourhood has < 30 per arm), status "ok" (>= 30 per arm
                          within 30 km), "limited evidence" (>= 10 per arm within a widened radius: show with a caveat) or "insufficient evidence" (indicative
                          only). scenario_d2_weeks = the drought intensity assumed. Field-level estimates exist only for tiers full / limited.
  county_check_<crop>.csv aggregate check: county yield anomaly vs share of continuous-crop area x county drought share (sign should match).
  report.md               the same in prose with the limits.

Usage
  python m2_neighbour_evidence.py check --attrs ./csb_work/attrs --ts ./ts_2021 ./ts_2022 ./ts_2023 ./ts_2024 ./ts_2025 --drought ./drought/ia_weekly.parquet --state 19
  python m2_neighbour_evidence.py run   <same inputs> --out ./m2_evidence [--ssurgo ./ext/ssurgo_field.parquet] [--nass-yield ./yield_work/nass_yield.parquet]
        [--power-daily P --cellmap-power M] [--smap-daily S --cellmap-smap M] [--crops corn soybeans] [--treatments T1 T2 T3 T5] [--t2-window 3]
        [--reps 499] [--fast] [--no-forest] [--predict-fields all|csv-or-ids]
Deps: numpy pandas pyarrow scikit-learn duckdb pyproj (+ econml for the causal forest; without it forest / field estimates are skipped, lightgbm optional, duckdb for the county check)
"""
import argparse
import gc
import json
import os
import math
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import NearestNeighbors

warnings.filterwarnings("ignore")

CORN, SOY = 1, 5
SMALL_GRAIN = (21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 205, 225, 226, 230, 234, 235, 236, 237, 240, 254)
HAY = (36, 37, 58)
CROPS = {"corn": CORN, "soybeans": SOY}
STEP_DAYS = 214 / 16
EVIDENCE_LABEL = "Adjusted association from observational satellite data"
LIMITS = ["unobserved management (hybrid, nitrogen rate, tillage) can bias the estimates",
          "greenness and ESI are stress proxies, not yield",
          "CSB / CDL crop classes can be wrong"]
TREATMENTS = {
    "T1": dict(treated="continuous crop (same crop in t-1)", control="rotated (the other main crop in t-1)", expected=-1),
    "T2": dict(treated=">=3 crop groups in t-5..t-1", control="1-2 crop groups", expected=+1),
    "T3": dict(treated="small grain or hay in t-3..t-1", control="absent", expected=+1),
    "T4": dict(treated="winter cover probability >= 0.7", control="<= 0.3 (bare winter)", expected=+1),
    "T5": dict(treated="host return interval >= 2 years", control="1 year (same crop last year)", expected=+1),
}
GREEN = ("peak_ndvi", "ndwi_jul_aug", "late_ndvi", "ndvi_area")
EXTRA = ("esi_jul_aug", "et_jul_aug", "openet_et", "openet_etof", "yield_proxy_dev")
NO_GAMMA = ("yield_proxy_dev",)                    # 19: the proxy's drought effect is not identified by construction (arm gaps only)
OUT_LABEL = {"peak_ndvi": "Y1 peak NDVI", "ndwi_jul_aug": "Y1 NDWI Jul-Aug", "late_ndvi": "Y1 late-season NDVI", "ndvi_area": "Y1 NDVI season area",
             "esi_jul_aug": "Y2 ECOSTRESS ESI Jul-Aug", "et_jul_aug": "Y2 ECOSTRESS ET Jul-Aug", "openet_et": "Y3 OpenET ET",
             "openet_etof": "Y3 OpenET ETof", "yield_proxy_dev": "NDVI-based yield proxy (bu/ac vs state-year)"}


RES = {"memory": "4GB", "tmp": None}          # set from --memory / --tmp in main()


def _duck():
    """DuckDB with a hard memory limit and a spill directory: joins and aggregates over the big daily tables go out-of-core"""
    import duckdb
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{RES['memory']}'")
    if RES["tmp"]:
        Path(RES["tmp"]).mkdir(parents=True, exist_ok=True)
        con.execute(f"PRAGMA temp_directory='{Path(RES['tmp']).as_posix()}/duckdb_spill'")
    return con


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def has_econml():
    try:
        import econml  # noqa: F401
        return True
    except Exception:
        return False


# =====================================================================================
# 1. DATA: one table, one row per field x season
# =====================================================================================
def outcomes_from_tensor(t):
    """Same definitions as 17_m2_drought_effect.py: steps are 13.4-day bins over 1 April - 31 October."""
    nd = t[[f"ndvi_d{k}" for k in range(1, 17)]].to_numpy(float)
    nw = t[[f"ndwi_d{k}" for k in range(1, 17)]].to_numpy(float)
    lo, hi = np.nanmin(nd, axis=1), np.nanmax(nd, axis=1)
    half = lo + 0.5 * (hi - lo)
    k = np.argmax(nd >= half[:, None], axis=1)
    prev = np.where(k > 0, nd[np.arange(len(nd)), np.maximum(k - 1, 0)], np.nan)
    frac = np.where(k > 0, (half - prev) / (nd[np.arange(len(nd)), k] - prev), 0.0)
    return pd.DataFrame({"CSBID": t["CSBID"].to_numpy(), "year": t["year"].to_numpy(), "n_observed_steps": t["n_observed_steps"].to_numpy(),
                         "peak_ndvi": nd[:, 6:12].max(axis=1), "ndwi_jul_aug": nw[:, 7:11].mean(axis=1),
                         "late_ndvi": nd[:, 11:13].mean(axis=1), "ndvi_area": nd[:, 5:13].sum(axis=1) * STEP_DAYS,
                         "greenup_doy": 91 + (np.where(k > 0, k - 1 + frac, 0.0) + 0.5) * STEP_DAYS})


def _names(path):
    import pyarrow.parquet as pq
    return pq.read_schema(path).names


def _read(path, columns=None, filters=None):
    """read only the wanted columns that exist; push the CSBID filter down, fall back to filtering after the read."""
    if columns is not None:
        have = set(_names(path))
        columns = [c for c in columns if c in have]
    try:
        return pd.read_parquet(path, columns=columns, filters=filters)
    except Exception:
        return pd.read_parquet(path, columns=columns)


def crop_group(code):
    return np.select([code == CORN, code == SOY, np.isin(code, SMALL_GRAIN), np.isin(code, HAY)], ["corn", "soy", "small_grain", "hay"], "other")


def _cap_range(path, cols):
    return [c for c in cols if c in set(_names(path))]


def _glob_ts(paths):
    """--ts accepts crop_ts_s1 folders (<folder>/dataset/tabular.parquet), tabular.parquet files, or globs of either"""
    import glob
    out = []
    for p in paths:
        for q in (sorted(glob.glob(str(p))) or [str(p)]):
            q = Path(q)
            for c in ((q,) if q.is_file() else (q / "dataset/tabular.parquet", q / "tabular.parquet")):
                if c.is_file():
                    out.append(c); break
    if not out:
        sys.exit("no tabular.parquet found for --ts (expected <crop_ts_s1 out>/dataset/tabular.parquet)")
    return out


def _county_key(df):
    c = df["CNTYFIPS"].astype(str).str.zfill(5) if df["CNTYFIPS"].astype(str).str.len().max() > 3 else \
        df["STATEFIPS"].astype(str).str.zfill(2) + df["CNTYFIPS"].astype(str).str.zfill(3)
    return c


def read_attrs(a, ids):
    """CSB attrs (csb_pipeline.py ingest): CSBID, STATEFIPS, CNTYFIPS, CSBACRES, centroid_lon/lat, CDL<yyyy> for the sampled fields"""
    import re
    import duckdb
    files = sorted(Path(a.attrs).glob("batch_*.parquet"))
    if not files:
        sys.exit(f"no batch_*.parquet in --attrs {a.attrs}")
    names = _names(files[0])
    cdl = sorted(int(c[3:]) for c in names if re.fullmatch(r"CDL\d{4}", c))
    area = "CSBACRES" if "CSBACRES" in names else "area_acres"
    con = _duck()
    con.register("ids", pd.DataFrame({"CSBID": sorted(ids)}))
    sel = ", ".join(["CAST(a.CSBID AS VARCHAR) AS CSBID", "a.STATEFIPS", "a.CNTYFIPS", f"a.{area} AS area_acres", "a.centroid_lon", "a.centroid_lat"] + [f"a.CDL{y}" for y in cdl])
    df = con.execute(f"SELECT {sel} FROM read_parquet('{(Path(a.attrs) / 'batch_*.parquet').as_posix()}') a SEMI JOIN ids ON CAST(a.CSBID AS VARCHAR) = ids.CSBID").df()
    df["county_fips"] = _county_key(df)
    return df.drop(columns=["STATEFIPS", "CNTYFIPS"]), cdl


def add_crop_history(o, attrs, cdl_years, a):
    """crop_t = CDL of the season, crop_t1..crop_t5 = CDL of the previous 5 seasons, from the field's own CDL columns (+ --cdl-extra long table)"""
    long = attrs.melt(id_vars=["CSBID"], value_vars=[f"CDL{y}" for y in cdl_years], var_name="y", value_name="cdl")
    long["year"] = long["y"].str[3:].astype(int)
    long = long[["CSBID", "year", "cdl"]]
    if a.cdl_extra:
        ex = pd.read_parquet(a.cdl_extra, columns=["CSBID", "year", "cdl"]).astype({"CSBID": str, "year": int})
        long = pd.concat([long, ex[ex["CSBID"].isin(set(attrs["CSBID"]))]]).drop_duplicates(["CSBID", "year"], keep="last")
    long["cdl"] = pd.to_numeric(long["cdl"], errors="coerce").where(lambda s: s > 0)
    for k in range(0, 6):
        nm = "crop_t" if k == 0 else f"crop_t{k}"
        x = long.assign(year=long["year"] + k).rename(columns={"cdl": nm})
        o = o.merge(x, on=["CSBID", "year"], how="left")
    return o


def add_drought(o, a):
    """USDM weekly table of csb_drought.py (CSBID, valid_date, dm; dm null = no drought class). Season = July-August (maps valid 1 Jul - 31 Aug).
    d2_jul_aug = number of maps with D2+ at the field centroid; usdm_drought_season = d2_jul_aug >= --drought-weeks. A field without a row in a map counts as
    'no drought' (so a table written with --drop-none works), but only for the years the table covers: by default every year between its first and last
    valid_date; pass --drought-years to name them (e.g. a drop-none table whose last years had no drought at all). Other years get NaN (unknown, not 'normal')."""
    import duckdb
    con = _duck()
    con.register("ids", pd.DataFrame({"CSBID": sorted(o["CSBID"].unique())}))
    w = f"read_parquet('{Path(a.drought).as_posix()}')" if Path(a.drought).is_file() else f"read_parquet('{(Path(a.drought) / '*.parquet').as_posix()}')"
    rng_ = con.execute(f"SELECT min(year(CAST(valid_date AS DATE))), max(year(CAST(valid_date AS DATE))) FROM {w}").fetchone()
    covered = set(a.drought_years) if a.drought_years else set(range(int(rng_[0]), int(rng_[1]) + 1))
    d = con.execute(f"SELECT CAST(w.CSBID AS VARCHAR) AS CSBID, year(CAST(w.valid_date AS DATE)) AS year, "
                    f"sum(CASE WHEN w.dm >= 2 THEN 1 ELSE 0 END) AS d2_jul_aug, max(coalesce(w.dm, -1)) AS max_jul_aug "
                    f"FROM {w} w SEMI JOIN ids ON CAST(w.CSBID AS VARCHAR) = ids.CSBID WHERE month(CAST(w.valid_date AS DATE)) IN (7, 8) GROUP BY 1, 2").df()
    o = o.merge(d, on=["CSBID", "year"], how="left")
    o["n_maps"] = o["year"].isin(covered).astype(float) * 99
    known = o["n_maps"] >= 6
    o["d2_jul_aug"] = np.where(known, o["d2_jul_aug"].fillna(0), np.nan)
    o["max_jul_aug"] = np.where(known, o["max_jul_aug"].fillna(-1), np.nan)
    o["usdm_drought_season"] = np.where(known, o["d2_jul_aug"] >= a.drought_weeks, np.nan)
    return o.drop(columns=["n_maps"])


def cell_year_stat(daily, cmap, ids, expr_by_year, ycol):
    """aggregate a daily cell table to cell x year (DuckDB), then map fields -> cell. Returns CSBID, year, <ycol...>"""
    import duckdb
    con = _duck()
    con.register("ids", pd.DataFrame({"CSBID": sorted(ids)}))
    cm = con.execute(f"SELECT CAST(m.CSBID AS VARCHAR) AS CSBID, m.cell_id AS _cell FROM read_parquet('{Path(cmap).as_posix()}') m SEMI JOIN ids ON CAST(m.CSBID AS VARCHAR) = ids.CSBID").df()
    con.register("cm", cm)
    cy = con.execute(expr_by_year.format(src=f"read_parquet('{Path(daily).as_posix()}')")).df()
    return cm.merge(cy, left_on="_cell", right_on="cell_id", how="inner").drop(columns=["_cell", "cell_id"]), cm


def read_inputs(a):
    ts_files = _glob_ts(a.ts)
    need = ["CSBID", "year", "n_observed_steps"] + [f"{p}_d{k}" for p in ("ndvi", "ndwi") for k in range(1, 17)]
    import pyarrow.parquet as pq
    for f in ts_files:
        miss = [c for c in need if c not in set(_names(f))]
        if miss:
            sys.exit(f"{f} lacks {miss[:4]}... (crop_ts / crop_ts_s1 compose output with --steps 16 expected)")
    # pass 1: only the CSBID column of every file -> the field list (a few MB)
    ids = set()
    for f in ts_files:
        ids.update(pd.read_parquet(f, columns=["CSBID"])["CSBID"].astype(str).unique())
    attrs, cdl_years = read_attrs(a, ids)
    if str(a.state).lower() != "all":
        keep = {s.strip().zfill(2) for s in str(a.state).split(",")}
        attrs = attrs[attrs["county_fips"].str[:2].isin(keep)]
    good = set(attrs["CSBID"])
    # pass 2: row batches -> the 32 tensor columns are reduced to 5 outcome columns per batch, never all in memory at once
    parts = []
    for f in ts_files:
        for b_ in pq.ParquetFile(f).iter_batches(batch_size=a.chunk_rows, columns=need):
            t = b_.to_pandas()
            t["CSBID"] = t["CSBID"].astype(str)
            t = t[t["CSBID"].isin(good)]
            if len(t):
                oc = outcomes_from_tensor(t)
                f32 = [c for c in oc.columns if c not in ("CSBID", "year", "n_observed_steps")]
                parts.append(oc.astype({c: "float32" for c in f32}))
            del t
    if not parts:
        sys.exit("no field of --ts is in --attrs for this --state")
    tens = pd.concat(parts, ignore_index=True)
    del parts
    tens = tens.drop_duplicates(["CSBID", "year"], keep="last")
    o = tens.merge(attrs[["CSBID", "county_fips", "area_acres", "centroid_lon", "centroid_lat"]], on="CSBID", how="inner")
    del tens
    o = add_crop_history(o, attrs, cdl_years, a)
    if a.crop_labels:                                            # seasons without CDL (e.g. a classifier for the current year)
        cl = pd.read_parquet(a.crop_labels).astype({"CSBID": str})
        if "label_prob" not in cl:
            cl["label_prob"] = 1.0
        o = o.merge(cl[["CSBID", "year", "crop_t", "label_prob"]].rename(columns={"crop_t": "crop_lab", "label_prob": "lab_p"}), on=["CSBID", "year"], how="left")
        use = o["crop_t"].isna() & o["crop_lab"].notna() & (o["lab_p"] >= a.label_min_prob)
        o.loc[use, "crop_t"] = o.loc[use, "crop_lab"]
        o["label_uncertain"] = o["lab_p"].notna() & (o["lab_p"] < 0.95)
    else:
        o["label_uncertain"] = False
    o = add_drought(o, a)
    o["drought"] = o["usdm_drought_season"].astype(float)
    o["log_area"] = np.log(o["area_acres"].astype(float).clip(lower=0.01))
    # stratum = the neighbourhood that shares weather: a grid square of --grid-km (EPSG:5070), "unit" in the original design
    from pyproj import Transformer
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform(o["centroid_lon"].to_numpy(float), o["centroid_lat"].to_numpy(float))
    g = a.grid_km * 1000.0
    o["unit"] = np.floor(x / g).astype(int).astype(str) + "_" + np.floor(y / g).astype(int).astype(str)
    o["stratum"] = o["unit"]
    o["fe"] = o["stratum"] + "_" + o["year"].astype(int).astype(str)

    # pre-treatment greenness (t-2, t-3), whatever crop the field carried then (needs the same fields in several years of --ts)
    na = o[["CSBID", "year", "ndvi_area", "peak_ndvi"]].drop_duplicates(["CSBID", "year"])
    pre = []
    for lag in (2, 3):
        pre.append(na.assign(year=na["year"] + lag).rename(columns={"ndvi_area": f"pa{lag}", "peak_ndvi": f"pp{lag}"}))
    o = o.merge(pre[0], on=["CSBID", "year"], how="left").merge(pre[1], on=["CSBID", "year"], how="left")
    o["pre_ndvi_area"] = o[["pa2", "pa3"]].mean(axis=1, skipna=True)
    o["pre_peak_ndvi"] = o[["pp2", "pp3"]].mean(axis=1, skipna=True)
    o = o.drop(columns=["pa2", "pa3", "pp2", "pp3"])

    # weather of the season (context + SMAP-based drought definition); POWER heat days, SMAP root-zone moisture
    ids = set(o["CSBID"])
    if a.power_daily and a.cellmap_power:
        p, _ = cell_year_stat(a.power_daily, a.cellmap_power, ids,
                              "SELECT cell_id, year(CAST(date AS DATE)) AS year, sum(CASE WHEN T2M_MAX >= 35 THEN 1 ELSE 0 END) AS heat_days_jul_aug "
                              "FROM {src} WHERE month(CAST(date AS DATE)) IN (7, 8) GROUP BY 1, 2", None)
        o = o.merge(p, on=["CSBID", "year"], how="left")
    if a.smap_daily and a.cellmap_smap:
        sm_sql = ("WITH d AS (SELECT cell_id, CAST(date AS DATE) AS dt, sm_rootzone FROM {src} WHERE month(CAST(date AS DATE)) IN (7, 8) AND sm_rootzone IS NOT NULL), "
                  "q AS (SELECT cell_id, quantile_cont(sm_rootzone, 0.2) AS p20 FROM d GROUP BY 1) "
                  "SELECT d.cell_id, year(d.dt) AS year, avg(d.sm_rootzone) AS smap_rz_jul_aug, "
                  "sum(CASE WHEN d.sm_rootzone < q.p20 THEN 1 ELSE 0 END) AS smap_days_below_p20_jul_aug, count(*) AS smap_days_jul_aug "
                  "FROM d JOIN q USING (cell_id) GROUP BY 1, 2")
        s, _ = cell_year_stat(a.smap_daily, a.cellmap_smap, ids, sm_sql, None)
        s["smap_rz_pctl_jul_aug"] = s.groupby("CSBID")["smap_rz_jul_aug"].rank(pct=True) * 100.0           # rank of the season among the years of the record
        o = o.merge(s, on=["CSBID", "year"], how="left")
        # SMAP drought: >= --smap-days of the season's July-August days below the cell's own 20th percentile of the record (needs a multi-year smap_daily)
        smap_dr = np.where(o["smap_days_jul_aug"].fillna(0) >= 40, (o["smap_days_below_p20_jul_aug"] >= a.smap_days).astype(float), np.nan)
        if a.drought_def == "smap":
            o["usdm_drought_season"], o["drought"] = smap_dr, smap_dr
        elif a.drought_def == "either":
            o["drought"] = np.where(np.isnan(smap_dr), o["drought"], np.fmax(np.nan_to_num(o["drought"]), np.nan_to_num(smap_dr)))
            o.loc[o["usdm_drought_season"].isna() & np.isnan(smap_dr), "drought"] = np.nan
            o["usdm_drought_season"] = o["drought"]
    elif a.drought_def != "usdm":
        sys.exit("--drought-def smap/either needs --smap-daily and --cellmap-smap")
    if a.ecostress:
        e = pd.read_parquet(a.ecostress).astype({"CSBID": str})
        e.loc[e["esi_n"] < 2, "esi_jul_aug"] = np.nan                  # one clear overpass is too noisy
        e.loc[e["et_n"] < 2, "et_jul_aug"] = np.nan
        o = o.merge(e[["CSBID", "year", "esi_jul_aug", "et_jul_aug"]], on=["CSBID", "year"], how="left")
    if a.openet:
        oe = pd.read_parquet(a.openet).astype({"CSBID": str})
        o = o.merge(oe[[c for c in ("CSBID", "year", "openet_et", "openet_etof") if c in oe.columns]], on=["CSBID", "year"], how="left")
    if a.ssurgo:                                                       # static field soil (ext_soil_ssurgo.py) -> the names used by the models
        sg = pd.read_parquet(a.ssurgo).astype({"CSBID": str}).drop_duplicates("CSBID")
        ren = {"ssurgo_aws_0_150_mm": "awc_mm", "ssurgo_aws_0_100_mm": "aws_0_100cm_mm", "ssurgo_om_pct": "om_pct", "ssurgo_clay_pct": "clay",
               "ssurgo_sand_pct": "sand", "ssurgo_slope_pct": "slope"}
        sg = sg[["CSBID"] + [c for c in ren if c in sg.columns]].rename(columns=ren)
        o = o.merge(sg, on="CSBID", how="left")
    if a.covariates:
        cv = pd.read_parquet(a.covariates).astype({"CSBID": str})
        key = ["CSBID", "year"] if "year" in cv.columns else ["CSBID"]
        o = o.merge(cv, on=key, how="left", suffixes=("", "_cov"))
    if a.winter_cover:
        wc = pd.read_parquet(a.winter_cover).astype({"CSBID": str})[["CSBID", "year", "p_cover"]]
        o = o.merge(wc, on=["CSBID", "year"], how="left")
    if a.max_year is None:
        a.max_year = int(max(cdl_years))
    return o


def covariate_columns(o, a):
    base = ["log_area", "centroid_lon", "centroid_lat", "pre_ndvi_area", "pre_peak_ndvi", "awc_mm", "aws_0_100cm_mm", "om_pct", "clay", "sand", "slope"]
    extra = []
    if a.covariates:
        cv = pd.read_parquet(a.covariates)
        extra = [c for c in cv.columns if c not in ("CSBID", "year") and pd.api.types.is_numeric_dtype(cv[c])]
        extra = [c for c in extra if c in o.columns]
    cols = [c for c in base + extra if c in o.columns and o[c].notna().sum() > 0 and o[c].nunique() > 1]
    return list(dict.fromkeys(cols))



# =====================================================================================
# 2. TREATMENTS
# =====================================================================================
def make_treatments(o, crop, a):
    other = SOY if crop == CORN else CORN
    T = pd.DataFrame(index=o.index)
    t1 = o["crop_t1"]
    T["T1"] = np.where(t1 == crop, 1.0, np.where(t1 == other, 0.0, np.nan))
    w = a.t2_window
    cols = [f"crop_t{k}" for k in range(1, w + 1) if f"crop_t{k}" in o.columns]
    if len(cols) == w:
        g = pd.DataFrame({c: crop_group(o[c].to_numpy()) for c in cols}, index=o.index).where(o[cols].notna())
        ok = o[cols].notna().all(axis=1)
        T["T2"] = np.where(ok, (g.nunique(axis=1) >= 3).astype(float), np.nan)
    else:
        T["T2"] = np.nan
    c3 = [c for c in ("crop_t1", "crop_t2", "crop_t3") if c in o.columns]
    if len(c3) == 3:
        has = o[c3].isin(SMALL_GRAIN + HAY).any(axis=1)
        T["T3"] = np.where(o[c3].notna().all(axis=1), has.astype(float), np.nan)
    else:
        T["T3"] = np.nan
    if "p_cover" in o.columns:
        T["T4"] = np.where(o["p_cover"] >= 0.7, 1.0, np.where(o["p_cover"] <= 0.3, 0.0, np.nan))
    else:
        T["T4"] = np.nan
    T["T5"] = np.where(t1.notna(), (t1 != crop).astype(float), np.nan)
    return T


# =====================================================================================
# 3. ESTIMATION
# =====================================================================================
def learner(name, fast=False, seed=0):
    it = 60 if fast else 150
    if name == "lgbm":
        import lightgbm as lgb
        return lgb.LGBMRegressor(n_estimators=it + 50, learning_rate=0.05, num_leaves=15, min_child_samples=20, subsample=0.8, subsample_freq=1,
                                 colsample_bytree=0.8, verbose=-1, random_state=seed, n_jobs=1)
    return HistGradientBoostingRegressor(max_iter=it, learning_rate=0.06, max_leaf_nodes=15, min_samples_leaf=20, random_state=seed)


def demean(df, cols, by):
    return df[cols] - df.groupby(by)[cols].transform("mean")


def crossfit(X, y, groups, a, seed=0):
    """out-of-fold predictions, folds = whole clusters (squares): a field is never predicted from its neighbours' own residual structure."""
    n_split = int(min(a.n_splits, len(np.unique(groups))))
    pred = np.full(len(y), np.nan)
    if n_split < 2:
        m = learner(a.learner, a.fast, seed).fit(X, y)
        return m.predict(X)
    for tr, te in GroupKFold(n_splits=n_split).split(X, y, groups):
        m = learner(a.learner, a.fast, seed).fit(X[tr], y[tr])
        pred[te] = m.predict(X[te])
    return pred


def cluster_sums(rt, ry, cl, n_cl):
    a_c = np.bincount(cl, weights=rt * ry, minlength=n_cl)
    b_c = np.bincount(cl, weights=rt * rt, minlength=n_cl)
    return a_c, b_c


def theta_cr(rt, ry, cl, n_cl):
    """partially linear DML estimate and cluster-robust (CR1) standard error from cross-fitted residuals."""
    J = float((rt * rt).sum())
    if J <= 0:
        return np.nan, np.nan
    th = float((rt * ry).sum() / J)
    psi = rt * (ry - th * rt)
    S = np.bincount(cl, weights=psi, minlength=n_cl)
    G = int((np.bincount(cl, minlength=n_cl) > 0).sum())
    V = float((S ** 2).sum()) / J ** 2 * (G / max(G - 1, 1))
    return th, math.sqrt(V)


class Pair:
    """One crop x treatment: the estimation sample, covariates, overlap diagnostics."""

    def __init__(self, d, tr, xcols, a):
        self.a, self.tr, self.xcols = a, tr, xcols
        self.d = d.reset_index(drop=True)
        self.cluster_names = sorted(self.d["stratum"].unique())
        self.d["cl"] = self.d["stratum"].map({c: i for i, c in enumerate(self.cluster_names)})
        self.n_cl = len(self.cluster_names)
        self.cache = {}

    def prep_x(self, d):
        X = d[self.xcols].copy()
        X = X.astype(float)
        return X

    def nuisance_t(self, idx, d):
        """residual of the treatment on FE-demeaned covariates (cross-fitted), cached by sample."""
        key = idx.tobytes()
        if key in self.cache:
            return self.cache[key]
        X = self.prep_x(d)
        Xd = (X - X.groupby(d["fe"]).transform("mean")).to_numpy()
        td = (d["T"] - d.groupby("fe")["T"].transform("mean")).to_numpy()
        rt = td - crossfit(Xd, td, d["cl"].to_numpy(), self.a, 1)
        self.cache[key] = (Xd, td, rt)
        return self.cache[key]

    def dml(self, d, y, simple=None, min_n=30):
        """Partially linear DML. simple=True (default when < 4 squares or < 60 rows): no ML adjustment, plain FE regression - cross-fitting on a few
        squares would overfit. Returns None when fewer than min_n rows have the outcome."""
        d = d[d[y].notna()]
        if len(d) < min_n:
            return None
        cl = d["cl"].to_numpy()
        n_cl = int(len(np.unique(cl)))
        if simple is None:
            simple = n_cl < 4 or len(d) < 60
        if simple:
            td = (d["T"] - d.groupby("fe")["T"].transform("mean")).to_numpy()
            rt, ry = td, (d[y] - d.groupby("fe")[y].transform("mean")).to_numpy()
        else:
            Xd, td, rt = self.nuisance_t(d.index.to_numpy(), d)
            yd = (d[y] - d.groupby("fe")[y].transform("mean")).to_numpy()
            ry = yd - crossfit(Xd, yd, cl, self.a, 2)
        th, se = theta_cr(rt, ry, cl, self.n_cl)
        if n_cl < 2:
            se = np.nan
        a_c, b_c = cluster_sums(rt, ry, cl, self.n_cl)
        return dict(theta=th, se=se, n=len(d), a_c=a_c, b_c=b_c, n_clusters=n_cl,
                    method="FE regression, no ML adjustment (small sample)" if simple else "DML")


def boot_cis(res_d, res_n, reps, rng):
    """cluster bootstrap of theta_d, theta_n and gamma = theta_d - theta_n, resampling squares jointly across drought and normal seasons."""
    G = len(res_d["a_c"])
    W = rng.multinomial(G, np.ones(G) / G, size=reps).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        td = (W @ res_d["a_c"]) / (W @ res_d["b_c"])
        tn = (W @ res_n["a_c"]) / (W @ res_n["b_c"])
    q = lambda v: tuple(np.nanpercentile(v, [2.5, 97.5]))
    return q(td), q(tn), q(td - tn)


def fe_interaction(d, y, tcol, dcol, fe, cluster, controls=("log_area",)):
    """linear FE regression of y on t, t x drought, controls; FE absorb the drought main effect (17's specification). Returns gamma."""
    x = [tcol, f"{tcol}_x_d"] + list(controls)
    d = d.assign(**{f"{tcol}_x_d": d[tcol] * d[dcol]}).dropna(subset=[y] + x)
    Y = demean(d, [y], fe).to_numpy().ravel()
    X = demean(d, x, fe).to_numpy()
    keep = X.std(axis=0) > 0
    if not keep[1]:
        return np.nan, np.nan
    X = X[:, keep]
    names = [c for c, k in zip(x, keep) if k]
    xtx = np.linalg.pinv(X.T @ X)
    b = xtx @ X.T @ Y
    e = Y - X @ b
    g = pd.factorize(d[cluster])[0]
    meat = np.zeros((X.shape[1], X.shape[1]))
    for c in np.unique(g):
        s = X[g == c].T @ e[g == c]
        meat += np.outer(s, s)
    G = len(np.unique(g))
    V = xtx @ meat @ xtx * G / max(G - 1, 1)
    i = names.index(f"{tcol}_x_d")
    return float(b[i]), float(np.sqrt(V[i, i]))


def placebo_p(d, y, tcol, fe, cluster, gamma, reps, rng):
    ug = d.drop_duplicates(fe)[[fe, "drought"]]
    perm = []
    for _ in range(reps):
        m = dict(zip(ug[fe], rng.permutation(ug["drought"].to_numpy())))
        dd = d.assign(drought_p=d[fe].map(m))
        perm.append(fe_interaction(dd, y, tcol, "drought_p", fe, cluster)[0])
    perm = np.array(perm)
    perm = perm[np.isfinite(perm)]
    return float((np.sum(np.abs(perm) >= abs(gamma)) + 1) / (len(perm) + 1)) if np.isfinite(gamma) and len(perm) else np.nan


# ---- matching baseline -----------------------------------------------------------------
MATCH_CELLS = 2_000_000                                     # max treated x control cells per matching block (~16 MB)


def match_att(d, y, xcols, caliper_sd=0.2):
    """Propensity-score matching inside each stratum x year: every treated field gets the control with the closest cross-fitted logit(propensity)
    (with replacement, caliper 0.2 SD of the logit). Returns ATT, pairs and the standardised mean differences of ALL covariates before / after."""
    d = d[d[y].notna()]
    X = d[xcols].astype(float)
    Xf = X.fillna(X.median())
    ps = d["ps"].clip(0.01, 0.99)
    z = np.log(ps / (1 - ps)).to_numpy()
    cal = caliper_sd * np.nanstd(z) if np.isfinite(np.nanstd(z)) and np.nanstd(z) > 0 else np.inf
    idx_t, idx_c = [], []
    pos = {k: i for i, k in enumerate(d.index)}
    sd = Xf.std().replace(0, 1)
    Z = ((Xf - Xf.mean()) / sd).to_numpy()                              # standardised covariates
    zs = np.nanstd(z) if np.nanstd(z) > 0 else 1.0
    for _, g in d.groupby("fe"):
        gt = g["T"].to_numpy()
        t_i, c_i = np.where(gt == 1)[0], np.where(gt == 0)[0]
        if len(t_i) == 0 or len(c_i) == 0:
            continue
        gi = g.index.to_numpy()
        pt, pc = [pos[k] for k in gi[t_i]], [pos[k] for k in gi[c_i]]
        zt, zc, Zt, Zc = z[pt], z[pc], Z[pt], Z[pc]
        c2 = (Zc ** 2).sum(1)
        step = max(1, int(MATCH_CELLS // max(len(pc), 1)))                    # treated rows per block: block x controls stays below MATCH_CELLS
        j = np.empty(len(pt), dtype=int)
        okk = np.empty(len(pt), dtype=bool)
        for s0 in range(0, len(pt), step):
            sl = slice(s0, s0 + step)
            dps = np.abs(zt[sl][:, None] - zc[None, :])                       # propensity distance inside the caliper, then covariate distance
            dcov = np.maximum((Zt[sl] ** 2).sum(1)[:, None] + c2[None, :] - 2.0 * Zt[sl] @ Zc.T, 0.0) / Z.shape[1]
            cost = np.where(dps <= cal, dcov + 4.0 * (dps / zs) ** 2, np.inf)
            jj = cost.argmin(axis=1)
            j[sl] = jj
            okk[sl] = np.isfinite(cost[np.arange(len(jj)), jj])
        for ti, pj, k in zip(t_i, j, okk):
            if k:
                idx_t.append(gi[ti]); idx_c.append(gi[c_i[pj]])
    if not idx_t:
        return dict(att=np.nan, n_pairs=0, smd_before=np.nan, smd_after=np.nan, smd_by=None)
    att = float(np.mean(d.loc[idx_t, y].to_numpy() - d.loc[idx_c, y].to_numpy()))
    both = d.groupby("fe")["T"].transform(lambda s: s.nunique() == 2)
    dd = d[both]
    pool = np.sqrt((Xf[both][dd["T"] == 1].var() + Xf[both][dd["T"] == 0].var()) / 2).replace(0, np.nan)
    Xdm = Xf[both] - Xf[both].groupby(dd["fe"]).transform("mean")
    before = ((Xdm[dd["T"] == 1].mean() - Xdm[dd["T"] == 0].mean()) / pool).abs()
    after = ((Xf.loc[idx_t].reset_index(drop=True) - Xf.loc[idx_c].reset_index(drop=True)).mean() / pool).abs()
    return dict(att=att, n_pairs=len(idx_t), smd_before=float(before.max()), smd_after=float(after.max()),
                smd_by={c: (float(before[c]), float(after[c])) for c in xcols})


# ---- overlap ---------------------------------------------------------------------------
def overlap_diag(pair, d):
    """(1) inside a stratum x year both arms must exist; (2) propensity from covariates must lie in 0.05-0.95."""
    a = pair.a
    both = d.groupby("fe")["T"].transform(lambda s: s.nunique() == 2)
    out = dict(share_fe_both_arms=float(both.mean()), units_with_both=int(d.loc[both, "stratum"].nunique()))
    dd = d[both].copy()
    if len(dd) < 50 or dd["T"].nunique() < 2:
        out.update(share_in_05_95=np.nan, keep=pd.Series(False, index=d.index))
        return out
    # propensity from covariates, square and year (no treatment-derived features: a leave-one-out share would identify T exactly)
    X = pair.prep_x(dd).assign(stratum_code=pd.factorize(dd["stratum"])[0], year=dd["year"].to_numpy()).to_numpy()
    gk = GroupKFold(n_splits=int(min(a.n_splits, dd["stratum"].nunique()))) if dd["stratum"].nunique() > 1 else None
    p = np.full(len(dd), np.nan)
    if gk is None:
        return dict(out, share_in_05_95=np.nan, keep=pd.Series(False, index=d.index))
    for tr, te in gk.split(X, dd["T"], dd["stratum"]):
        if dd["T"].iloc[tr].nunique() < 2:
            p[te] = dd["T"].iloc[tr].mean()
            continue
        m = HistGradientBoostingClassifier(max_iter=60 if a.fast else 120, learning_rate=0.06, max_leaf_nodes=8, min_samples_leaf=30, random_state=0)
        m.fit(X[tr], dd["T"].iloc[tr].astype(int))
        p[te] = m.predict_proba(X[te])[:, 1]
    ok = (p >= 0.05) & (p <= 0.95)
    keep = pd.Series(False, index=d.index)
    keep.loc[dd.index[ok]] = True
    out.update(share_in_05_95=float(ok.mean()), keep=keep, ps=pd.Series(p, index=dd.index))
    return out


TIER_RANK = {"full": 0, "limited": 1, "one season type": 2, "pooled": 3, "descriptive": 4}
CONFIDENCE = {"full": "medium", "limited": "low", "one season type": "low", "pooled": "low", "descriptive": "very low"}


def _arms(s):
    return (int((s["T"] == 1).sum()), int((s["T"] == 0).sum()))


def units_both(s):
    """squares that have both arms inside one square-year"""
    if s.empty:
        return 0
    both = s.groupby("fe")["T"].transform(lambda x: x.nunique() == 2)
    return int(s.loc[both, "stratum"].nunique())


def raw_gap(d, y):
    """last resort: difference of the arm means (no fixed effects, no model)"""
    d = d[d[y].notna()]
    t, c = d.loc[d["T"] == 1, y], d.loc[d["T"] == 0, y]
    if len(t) == 0 or len(c) == 0:
        return None
    return dict(theta=float(t.mean() - c.mean()), se=np.nan, n=len(d), a_c=None, b_c=None, n_clusters=int(d["stratum"].nunique()), method="raw arm gap")


def ci_one(res, reps, rng):
    """cluster bootstrap (squares) of a single theta; needs >= 3 squares with treatment variation"""
    if res is None or res.get("a_c") is None or int((res["b_c"] > 0).sum()) < 3:
        return np.nan, np.nan
    G = len(res["a_c"])
    W = rng.multinomial(G, np.ones(G) / G, size=reps).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (W @ res["a_c"]) / (W @ res["b_c"])
    t = t[np.isfinite(t)]
    return (float(np.percentile(t, 2.5)), float(np.percentile(t, 97.5))) if len(t) > 20 else (np.nan, np.nan)


def _few_sq(res):
    return res is None or res.get("a_c") is None or int((res["b_c"] > 0).sum()) < 3


def _reasons(arms, units, shares, a):
    out = []
    for k in ("drought", "normal"):
        if min(arms[k]) < a.min_arm:
            out.append(f"{k}: arm size {arms[k]} < {a.min_arm}")
        if units[k] < a.min_units:
            out.append(f"{k}: only {units[k]} squares with both arms inside a square-year")
        sh = shares.get(k, np.nan)
        if np.isfinite(sh) and sh < a.min_overlap:
            out.append(f"{k}: overlap {sh:.0%} of fields have propensity in 0.05-0.95")
    return out


def _headline(r, expected):
    for k, lab in (("drought", "effect in drought seasons"), ("normal", "effect in normal seasons"), ("pooled", "effect over all seasons")):
        v = r.get(f"theta_{k}", np.nan)
        if v is not None and np.isfinite(v):
            r.update(headline_basis=("raw arm gap, not adjusted" if r.get("method") == "raw arm gap" else lab), headline_effect=v,
                     headline_lo=r.get(f"lo_{k}", np.nan), headline_hi=r.get(f"hi_{k}", np.nan), headline_sign_agrees=bool(np.sign(v) == expected))
            return r
    r.update(headline_basis="", headline_effect=np.nan, headline_lo=np.nan, headline_hi=np.nan, headline_sign_agrees=None)
    return r


def estimate_pair(d0, crop, tr, xcols, outcomes, a, rng, forest_bank):
    """All outcomes for one crop x treatment, with GRACEFUL DEGRADATION. The best tier the data support is used (evidence_tier in the output):
       full             both season types pass the full thresholds (--min-arm, --min-units, overlap): DML, gamma, all checks
       limited          both season types pass the soft thresholds (--soft-arm, --soft-units): same estimators on a small sample, intervals wide
       one season type  only drought OR normal seasons have enough fields in both arms: that effect only, gamma not identified
       pooled           neither season type alone, but all seasons together have >= --pooled-arm fields in each arm: one effect over all seasons
       descriptive      anything else with at least one field-year in each arm: within-square-year arm gap (or raw gap) with n, no model
       (abstain only when an arm has no field-year at all, or with --strict)"""
    meta = TREATMENTS[tr]
    d0 = d0.copy()
    d0["T"] = d0[tr].astype(float)
    d0["ps"] = np.nan
    dr, nm = d0[d0["drought"] == 1], d0[d0["drought"] == 0]
    arms = {"drought": _arms(dr), "normal": _arms(nm), "pooled": _arms(d0)}
    units = {"drought": units_both(dr), "normal": units_both(nm), "pooled": units_both(d0)}
    base = dict(crop=crop, treatment=tr, treated=meta["treated"], control=meta["control"], expected_sign=meta["expected"], evidence_label=EVIDENCE_LABEL,
                n_treated_drought=arms["drought"][0], n_control_drought=arms["drought"][1], n_treated_normal=arms["normal"][0],
                n_control_normal=arms["normal"][1], overlap_share_drought=np.nan, overlap_share_normal=np.nan,
                squares_both_arms_drought=units["drought"], squares_both_arms_normal=units["normal"], squares_both_arms_pooled=units["pooled"])
    ok = lambda k, n, u: min(arms[k]) >= n and units[k] >= u
    full_c = ok("drought", a.min_arm, a.min_units) and ok("normal", a.min_arm, a.min_units)
    soft_c = ok("drought", a.soft_arm, a.soft_units) and ok("normal", a.soft_arm, a.soft_units)
    one_ks = [k for k in ("drought", "normal") if ok(k, a.soft_arm, a.soft_units)]
    tier, note, d, shares = None, "", None, {}
    if soft_c:
        keep = pd.Series(False, index=d0.index)
        for k, sub in (("drought", dr), ("normal", nm)):
            o_ = overlap_diag(Pair(sub, tr, xcols, a), sub)
            keep.loc[o_["keep"][o_["keep"]].index] = True
            if "ps" in o_:
                d0.loc[o_["ps"].index, "ps"] = o_["ps"]
            shares[k] = o_.get("share_in_05_95", np.nan)
            base[f"overlap_share_{k}"] = shares[k]
        ov_ok = all(np.isfinite(x) and x >= a.min_overlap for x in shares.values())
        if full_c and ov_ok:
            tier, d = "full", d0[keep]
        else:
            kk = d0[keep]
            trim_ok = all(len(x) and min(_arms(x)) >= a.soft_arm and units_both(x) >= a.soft_units for x in (kk[kk["drought"] == 1], kk[kk["drought"] == 0]))
            tier, d = "limited", (kk if trim_ok else d0)
            why = _reasons(arms, units, shares, a)
            note = ("small sample: " + "; ".join(why) if why else "small sample") + ("" if trim_ok else "; overlap trimming skipped (it would leave too few fields)")
    elif one_ks:
        tier = "one season type"
        miss = [k for k in ("drought", "normal") if k not in one_ks]
        note = (f"drought effect not identified: only {' and '.join(one_ks)} seasons have enough fields in both arms; "
                + "; ".join(f"{k}: arms {arms[k]}, {units[k]} squares with both arms" for k in miss))
    elif ok("pooled", a.pooled_arm, a.soft_units):
        tier = "pooled"
        note = (f"too few fields in each season type separately (drought {arms['drought']}, normal {arms['normal']}); effect averaged over all seasons, "
                "drought-specific effect not identified")
    elif min(arms["pooled"]) >= 1:
        tier = "descriptive"
        note = (f"descriptive arm gap only, not a causal estimate: treated n={arms['pooled'][0]}, control n={arms['pooled'][1]}, "
                f"{units['pooled']} squares with both arms")
    reasons = _reasons(arms, units, shares, a)
    if tier is None or (a.strict and tier != "full"):
        if tier is None:
            reasons = [f"no field-year in one arm (treated {arms['pooled'][0]}, control {arms['pooled'][1]})"]
        return [dict(base, outcome=y, outcome_label=OUT_LABEL.get(y, y), abstain=True, abstain_reason="; ".join(reasons), evidence_tier="none") for y in outcomes], []
    base.update(evidence_tier=tier, confidence=CONFIDENCE[tier], tier_note=note)
    blank = dict(theta_drought=np.nan, se_drought=np.nan, lo_drought=np.nan, hi_drought=np.nan, theta_normal=np.nan, se_normal=np.nan, lo_normal=np.nan, hi_normal=np.nan,
                 theta_pooled=np.nan, se_pooled=np.nan, lo_pooled=np.nan, hi_pooled=np.nan, gamma=np.nan, gamma_lo=np.nan, gamma_hi=np.nan,
                 gamma_placebo_p=np.nan, gamma_identified=False, balance_pass=None, neg_control_pass=None, neg_control_theta=np.nan, neg_control_se=np.nan)
    rows, balance = [], []
    if tier in ("full", "limited"):
        pair = Pair(d, tr, xcols, a)
        d = pair.d
        drd, nmd = d[d["drought"] == 1], d[d["drought"] == 0]
        mn = 30 if tier == "full" else 15
        for y in outcomes:
            r = dict(base, outcome=y, outcome_label=OUT_LABEL.get(y, y), abstain=False, abstain_reason="", **blank)
            rd, rn = pair.dml(drd, y, min_n=mn), pair.dml(nmd, y, min_n=mn)
            if rd is None or rn is None:
                rows.append(dict(r, abstain=True, abstain_reason="too few outcome values", evidence_tier="none")); continue
            bd, bn, bg = boot_cis(rd, rn, a.reps, rng)
            if _few_sq(rd) or _few_sq(rn):                       # fewer than 3 squares carry the variation: a bootstrap interval would be meaningless
                bd = bn = bg = (np.nan, np.nan)
            r.update(n_drought=rd["n"], n_normal=rn["n"], squares=int(d["stratum"].nunique()), method=rd["method"],
                     theta_drought=rd["theta"], se_drought=rd["se"], lo_drought=bd[0], hi_drought=bd[1],
                     theta_normal=rn["theta"], se_normal=rn["se"], lo_normal=bn[0], hi_normal=bn[1])
            r["few_clusters"] = bool(min(rd["n_clusters"], rn["n_clusters"]) < 10)
            if y not in NO_GAMMA:
                th = rd["theta"] - rn["theta"]
                r.update(gamma=th, gamma_lo=bg[0], gamma_hi=bg[1], gamma_identified=True)
                gl, gl_se = fe_interaction(d, y, "T", "drought", "fe", "stratum")
                r["gamma_linear_fe"] = gl
                r["gamma_placebo_p"] = placebo_p(d.dropna(subset=[y]), y, "T", "fe", "stratum", gl, a.placebo_reps, rng)
                unc = (d["n_observed_steps"] < 12) | d["label_uncertain"].astype(bool)             # sensitivity: drop uncertain seasons
                gl2, _ = fe_interaction(d[~unc], y, "T", "drought", "fe", "stratum")
                r["gamma_linear_fe_drop_uncertain"] = gl2
                r["sensitivity_same_sign"] = bool(np.isfinite(gl) and np.isfinite(gl2) and np.sign(gl) == np.sign(gl2))
                r["sign_agrees_with_expected"] = bool(np.sign(th) == meta["expected"]) if np.isfinite(th) else None
            try:                                                 # matching baseline (same strata, same outcome); needs the propensity of every row used
                md, mnn = drd[drd["ps"].notna()], nmd[nmd["ps"].notna()]
                mm_d, mm_n = match_att(md, y, xcols), match_att(mnn, y, xcols)
            except Exception:
                mm_d = mm_n = dict(att=np.nan, n_pairs=0, smd_before=np.nan, smd_after=np.nan, smd_by=None)
            r.update(match_att_drought=mm_d["att"], match_att_normal=mm_n["att"], match_pairs_drought=mm_d["n_pairs"], match_pairs_normal=mm_n["n_pairs"],
                     match_gamma=(mm_d["att"] - mm_n["att"]) if np.isfinite(mm_d["att"]) and np.isfinite(mm_n["att"]) else np.nan,
                     max_smd_before=max(np.nan_to_num(mm_d["smd_before"]), np.nan_to_num(mm_n["smd_before"])),
                     max_smd_after=max(np.nan_to_num(mm_d["smd_after"]), np.nan_to_num(mm_n["smd_after"])))
            r["balance_pass"] = bool(r["max_smd_after"] < 0.1) if (mm_d["n_pairs"] and mm_n["n_pairs"]) else None
            if mm_d["smd_by"] and y == outcomes[0]:
                for k, v in mm_d["smd_by"].items():
                    balance.append(dict(crop=crop, treatment=tr, season_type="drought", covariate=k, smd_before=v[0], smd_after=v[1]))
                if mm_n["smd_by"]:
                    for k, v in mm_n["smd_by"].items():
                        balance.append(dict(crop=crop, treatment=tr, season_type="normal", covariate=k, smd_before=v[0], smd_after=v[1]))
            rows.append(_headline(r, meta["expected"]))
        # negative-control outcome: greenness before the treatment (t-2, t-3), pooled seasons
        nc = pair.dml(d, "pre_ndvi_area", min_n=mn) if d["pre_ndvi_area"].notna().sum() > (200 if tier == "full" else 60) else None
        for r in rows:
            if nc is not None and not r.get("abstain"):
                r.update(neg_control_theta=nc["theta"], neg_control_se=nc["se"], neg_control_pass=bool(abs(nc["theta"]) < 2 * nc["se"]))
        return rows, balance
    # ---- lower tiers: no gamma, no matching, no placebo
    pair = Pair(d0, tr, xcols, a)
    dp = pair.d
    sets = {"drought": dp[dp["drought"] == 1], "normal": dp[dp["drought"] == 0]}
    for y in outcomes:
        r = dict(base, outcome=y, outcome_label=OUT_LABEL.get(y, y), abstain=False, abstain_reason="", squares=int(dp["stratum"].nunique()), **blank)
        got = False
        if tier == "one season type":
            for k in one_ks:
                res = pair.dml(sets[k], y, min_n=15)
                if res is not None:
                    lo, hi = ci_one(res, a.reps, rng)
                    r.update({f"theta_{k}": res["theta"], f"se_{k}": res["se"], f"lo_{k}": lo, f"hi_{k}": hi, f"n_{k}": res["n"], "method": res["method"]})
                    r["few_clusters"] = bool(res["n_clusters"] < 10)
                    got = True
        else:
            res = pair.dml(dp, y, simple=True if tier == "descriptive" else None, min_n=15 if tier == "pooled" else 2)
            if tier == "descriptive" and (res is None or not np.isfinite(res["theta"])):
                res = raw_gap(dp, y)
            if res is not None and np.isfinite(res["theta"]):
                lo, hi = ci_one(res, a.reps, rng)
                r.update(theta_pooled=res["theta"], se_pooled=res["se"], lo_pooled=lo, hi_pooled=hi, n_pooled=res["n"], method=res["method"])
                r["few_clusters"] = bool(res["n_clusters"] < 10)
                got = True
        if not got:
            rows.append(dict(r, abstain=True, abstain_reason="too few outcome values", evidence_tier="none")); continue
        rows.append(_headline(r, meta["expected"]))
    return rows, []


# =====================================================================================
# 4. HETEROGENEITY + FIELD-LEVEL WHAT-IF (causal forest, EconML)
# =====================================================================================
HET = ["awc_mm", "aws_0_100cm_mm", "om_pct", "clay", "sand", "slope", "d2_jul_aug", "log_area"]   # soil / terrain / drought intensity / size


def forest_fit(d, tr, y, het, wcols, a):
    from econml.dml import CausalForestDML
    d = d[d[y].notna()].copy()
    Td = (d["T"] - d.groupby("fe")["T"].transform("mean")).to_numpy()
    Yd = (d[y] - d.groupby("fe")[y].transform("mean")).to_numpy()
    X = d[het].astype(float)
    X = X.fillna(X.median()).to_numpy()
    W = d[wcols].astype(float)
    W = (W - W.groupby(d["fe"]).transform("mean")).fillna(0).to_numpy() if wcols else None
    est = CausalForestDML(model_y=learner(a.learner, True), model_t=learner(a.learner, True), discrete_treatment=False, n_estimators=int(math.ceil(a.forest_trees / 4) * 4),
                          min_samples_leaf=max(10, len(d) // 200), cv=min(3, d["stratum"].nunique()), random_state=0)
    est.fit(Yd, Td, X=X, W=W, groups=pd.factorize(d["stratum"])[0] if d["stratum"].nunique() >= 3 else None)
    return est, X, d


def comparable(lat, lon, ref, radii_km, min_n, chunk=20000):
    """fields (unique CSBID) of the drought sample around every target, by arm. Counts only. The radius is WIDENED (radii_km, ascending) for targets that
    have fewer than min_n comparable fields in either arm: returns counts at the first radius, counts and radius used (smallest radius with min_n in both
    arms, else the largest)."""
    from sklearn.neighbors import BallTree
    n = len(lat)
    trees = {}
    for arm in (1, 0):
        sub = ref[ref["T"] == arm]
        trees[arm] = BallTree(np.radians(sub[["centroid_lat", "centroid_lon"]].to_numpy()), metric="haversine") if len(sub) else None
    q = np.radians(np.column_stack([lat, lon]))
    n_t, n_c = np.zeros(n, dtype=int), np.zeros(n, dtype=int)
    n_t0, n_c0 = n_t.copy(), n_c.copy()
    used = np.full(n, float(radii_km[-1]))
    todo = np.arange(n)
    for ri, rk in enumerate(radii_km):
        if len(todo) == 0:
            break
        r = rk / 6371.0088
        cnt = []
        for arm in (1, 0):
            if trees[arm] is None:
                cnt.append(np.zeros(len(todo), dtype=int)); continue
            cnt.append(np.concatenate([trees[arm].query_radius(q[todo[i:i + chunk]], r=r, count_only=True) for i in range(0, len(todo), chunk)]))
        n_t[todo], n_c[todo] = cnt[0], cnt[1]
        if ri == 0:
            n_t0, n_c0 = n_t.copy(), n_c.copy()
        used[todo] = rk
        todo = todo[~((cnt[0] >= min_n) & (cnt[1] >= min_n))]
    return n_t0, n_c0, n_t, n_c, used


def field_estimates(d_drought, crop, tr, y, xcols, a, targets, sens_gamma):
    """CausalSoil: the conditional drought-season effect at the field's own covariates, 95% interval, comparable neighbours, or abstention."""
    het = [c for c in HET if c in d_drought.columns and d_drought[c].notna().sum() > 0 and d_drought[c].nunique() > 1]
    if len(het) == 0 or d_drought["T"].nunique() < 2 or d_drought["stratum"].nunique() < 3:
        return None
    wcols = [c for c in xcols if c not in het]
    est, X, dd = forest_fit(d_drought, tr, y, het, wcols, a)
    ref_d2 = float(d_drought["d2_jul_aug"].median()) if "d2_jul_aug" in d_drought else np.nan
    tg = targets.copy()
    if "d2_jul_aug" in het:
        tg["d2_jul_aug"] = a.scenario_d2 if a.scenario_d2 is not None else ref_d2
    Xt = tg[het].astype(float)
    Xt = Xt.fillna(dd[het].astype(float).median()).to_numpy()
    taus, los, his = [], [], []
    for i0 in range(0, len(Xt), a.chunk_rows // 10):                      # predictions block by block (trees x rows memory)
        blk = Xt[i0:i0 + a.chunk_rows // 10]
        taus.append(np.ravel(est.effect(blk)))
        l_, h_ = est.effect_interval(blk, alpha=0.05)
        los.append(np.ravel(l_)); his.append(np.ravel(h_))
    tau, lo, hi = np.concatenate(taus), np.concatenate(los), np.concatenate(his)
    radii = [float(a.radius_km)]
    while radii[-1] * 2 <= a.max_radius_km:
        radii.append(radii[-1] * 2)
    n_t0, n_c0, n_t, n_c, rad = comparable(tg["centroid_lat"].to_numpy(), tg["centroid_lon"].to_numpy(), dd[["centroid_lat", "centroid_lon", "T"]].drop_duplicates(),
                                           radii, a.min_comparable)
    out = tg[["CSBID", "centroid_lat", "centroid_lon"]].copy()
    out = out.assign(crop=crop, treatment=tr, outcome=y, treated=TREATMENTS[tr]["treated"], control=TREATMENTS[tr]["control"],
                     effect_drought=tau, lo95=np.ravel(lo), hi95=np.ravel(hi), n_comparable_treated_30km=n_t0, n_comparable_control_30km=n_c0,
                     n_comparable_treated_used=n_t, n_comparable_control_used=n_c, radius_used_km=rad,
                     scenario_d2_weeks=(a.scenario_d2 if a.scenario_d2 is not None else ref_d2), heterogeneity_vars=",".join(het),
                     evidence_label=EVIDENCE_LABEL)
    good = (n_t >= a.min_comparable) & (n_c >= a.min_comparable)
    soft = (n_t >= a.min_comparable_soft) & (n_c >= a.min_comparable_soft)
    out["status"] = np.where(good & (rad <= a.radius_km + 1e-9), "ok", np.where(soft, "limited evidence", "insufficient evidence"))
    out["note"] = [("" if st == "ok" else
                    f"fewer than {a.min_comparable} comparable fields of one arm within {a.radius_km:.0f} km; counted within {rk:.0f} km: {nt} treated, {nc} control"
                    if st == "limited evidence" else
                    f"fewer than {a.min_comparable_soft} comparable fields of one arm even within {rk:.0f} km ({nt} treated, {nc} control): indicative only")
                   for st, rk, nt, nc in zip(out["status"], rad, n_t, n_c)]
    avg_ate = float(np.mean(tau)) if len(tau) else np.nan
    out["forest_mean_effect"] = avg_ate
    return out


# =====================================================================================
# 5. COUNTY CHECK (aggregate validation, NASS yields)
# =====================================================================================
def county_check(o, crop, a):
    """County yield anomaly (NASS, yield_nass.py output) vs the county's share of continuous-crop acres in the sample, interacted with the county's
    drought share. County and year fixed effects; clusters = county. An aggregate check on the sign only; the shares come from the sampled fields,
    so a stratified sample (by crop class) makes it weaker than a census of the county's fields."""
    if not a.nass_yield or not Path(a.nass_yield).exists():
        return None
    code = CROPS[crop]
    d0 = o[o["crop_t"] == code]
    g = d0.groupby(["year", "county_fips"])
    cy = pd.DataFrame({"mono_share": g.apply(lambda s: s.loc[s["crop_t1"] == code, "area_acres"].sum() / max(s.loc[s["crop_t1"].isin([CORN, SOY]), "area_acres"].sum(), 1e-9)
                                              if s["crop_t1"].isin([CORN, SOY]).any() else np.nan),
                       "drought_share": g.apply(lambda s: s.loc[s["drought"] == 1, "area_acres"].sum() / max(s["area_acres"].sum(), 1e-9) if s["drought"].notna().any() else np.nan),
                       "n_fields": g.size()}).reset_index()
    min_f = getattr(a, f"county_min_fields_{crop}", None)
    min_f = a.county_min_fields if min_f is None else min_f             # per-crop value, else the common --county-min-fields
    cy = cy[cy["n_fields"] >= min_f]
    panel = pd.read_parquet(a.nass_yield)
    panel["county_fips"] = panel["county_fips"].astype(str).str.zfill(5)
    panel = panel[panel["crop"].str.upper() == crop.upper()]
    prev = "yield_mean_prev3_bu_acre" if "yield_mean_prev3_bu_acre" in panel.columns else "yield_mean_prev3"
    cy = cy.merge(panel[["county_fips", "year", "yield_bu_acre", prev]], on=["county_fips", "year"]).dropna()
    cy["anomaly"] = cy["yield_bu_acre"] / cy[prev]
    if len(cy) < 30 or cy["county_fips"].nunique() < 8:
        log(f"{crop} county check skipped: {len(cy)} county-years, {cy['county_fips'].nunique()} counties (need 30 / 8; lower --county-min-fields-{crop} (now {min_f}) or sample more fields)")
        return None
    cy["year_f"] = cy["year"].astype(str)
    cy["inter"] = cy["mono_share"] * cy["drought_share"]
    d = cy.copy()
    for c in ("anomaly", "mono_share", "inter", "drought_share"):
        d[c + "_dm"] = d[c] - d.groupby("county_fips")[c].transform("mean")
        d[c + "_dm"] = d[c + "_dm"] - d.groupby("year_f")[c + "_dm"].transform("mean")
    X = d[["mono_share_dm", "inter_dm"]].to_numpy()
    Y = d["anomaly_dm"].to_numpy()
    xtx = np.linalg.pinv(X.T @ X)
    b = xtx @ X.T @ Y
    e = Y - X @ b
    gg = pd.factorize(d["county_fips"])[0]
    meat = sum(np.outer(X[gg == c].T @ e[gg == c], X[gg == c].T @ e[gg == c]) for c in np.unique(gg))
    G = len(np.unique(gg))
    V = xtx @ meat @ xtx * G / (G - 1)
    se = np.sqrt(np.diag(V))
    return pd.DataFrame([dict(crop=crop, term="continuous share (normal seasons)", coef=b[0], se=se[0], n_county_years=len(d), counties=G),
                         dict(crop=crop, term="continuous share x county drought share", coef=b[1], se=se[1], n_county_years=len(d), counties=G)])


# =====================================================================================
# 6. DRIVERS
# =====================================================================================
def outcome_diagnostics(o, crop, outcomes, a):
    """does an outcome see the drought at all? (17): drought main effect with stratum x ... FE of stratum, year dummies, both arms together."""
    rows = []
    d = o[o["crop_t"] == CROPS[crop]].copy()
    d["stratum_f"] = d["stratum"]
    for y in outcomes:
        x = d.dropna(subset=[y, "drought"])
        if len(x) < 100 or x["drought"].nunique() < 2:
            continue
        yrs = sorted(x["year"].unique())
        X = pd.concat([x[["drought", "log_area"]], pd.get_dummies(x["year"], prefix="y", drop_first=True).astype(float)], axis=1)
        X = X.assign(stratum=x["stratum"])
        Xd = demean(X.assign(_s=x["stratum"]), [c for c in X.columns if c != "stratum"], "stratum")
        Yd = (x[y] - x.groupby("stratum")[y].transform("mean")).to_numpy()
        keep = Xd.std() > 0
        Xm = Xd.loc[:, keep].to_numpy()
        b = np.linalg.pinv(Xm.T @ Xm) @ Xm.T @ Yd
        e = Yd - Xm @ b
        g = pd.factorize(x["stratum"])[0]
        xtx = np.linalg.pinv(Xm.T @ Xm)
        meat = sum(np.outer(Xm[g == c].T @ e[g == c], Xm[g == c].T @ e[g == c]) for c in np.unique(g))
        G = len(np.unique(g))
        V = xtx @ meat @ xtx * G / max(G - 1, 1)
        names = list(Xd.columns[keep])
        if "drought" not in names:                      # one season only: drought is constant inside every square, the stratum effect absorbs it
            log(f"  outcome diagnostics {crop} {y}: drought has no variation inside squares (only one year?) - cannot check that the outcome sees drought")
            continue
        i = names.index("drought")
        sd = x.loc[x["drought"] == 0, y].std()
        rows.append(dict(crop=crop, outcome=y, drought_coef=float(b[i]), se=float(np.sqrt(V[i, i])), t=float(b[i] / np.sqrt(V[i, i])),
                         sd_units=float(b[i] / sd) if sd > 0 else np.nan, n=len(x), squares=G, sees_drought=bool(abs(b[i] / np.sqrt(V[i, i])) > 2)))
    return rows


def pick_outcomes(o, crop, a):
    use = [c for c in GREEN if c in o.columns]
    d = o[(o["crop_t"] == CROPS[crop]) & (o["year"] <= a.max_year)]
    for c in EXTRA:
        if c in o.columns and d[c].notna().sum() >= a.min_extra_outcome:
            use.append(c)
    return use


def cmd_check(a):
    o = read_inputs(a)
    xcols = covariate_columns(o, a)
    print("M2 DATA READINESS\n" + "=" * 70)
    print(f"field-years with HLS outcomes: {len(o):,}   fields: {o['CSBID'].nunique():,}   squares: {o['stratum'].nunique()}   years: {sorted(int(y) for y in o['year'].unique())}")
    print(f"drought labelled: {int(o['drought'].notna().sum()):,}   drought field-years: {int((o['drought'] == 1).sum()):,}")
    print("covariates:", xcols)
    print("econml (causal forest / field estimates):", "available" if has_econml() else "MISSING (pip install econml)")
    for crop, code in CROPS.items():
        d = o[o["crop_t"] == code]
        T = make_treatments(d, code, a)
        print(f"\n{crop}: {len(d):,} field-years with crop label; outcomes: {pick_outcomes(o, crop, a)}")
        rows = []
        for tr in TREATMENTS:
            t = T[tr]
            rows.append(dict(treatment=tr, defined=int(t.notna().sum()),
                             drought_treated=int(((t == 1) & (d["drought"] == 1)).sum()), drought_control=int(((t == 0) & (d["drought"] == 1)).sum()),
                             normal_treated=int(((t == 1) & (d["drought"] == 0)).sum()), normal_control=int(((t == 0) & (d["drought"] == 0)).sum())))
        print(pd.DataFrame(rows).to_string(index=False))
    if "p_cover" not in o.columns:
        print("\nT4 (winter cover) is skipped: no --winter-cover table (M1 output).")


def add_verdicts(res, n_years):
    """verdict, confidence and limits per row (res = effects table)"""
    res["limits"] = " | ".join(LIMITS)
    res["t_gamma"] = np.where(res.get("gamma").notna() if "gamma" in res else False, np.nan, np.nan)
    if "gamma" in res:
        # a conservative verdict per row: the cluster-bootstrap interval of gamma excludes 0, the placebo agrees, the checks pass
        ex0 = (res["gamma_lo"] > 0) | (res["gamma_hi"] < 0)
        res["verdict"] = np.where(res["abstain"], "abstain",
                         np.where(~res["gamma_identified"].fillna(False).astype(bool), "arm gap only (drought effect not identified)",
                         np.where(ex0 & (res["gamma_placebo_p"].fillna(1) < 0.1) & res["neg_control_pass"].fillna(True) & res["balance_pass"].fillna(False),
                                  "supported (all checks pass)",
                         np.where(ex0 & (res["gamma_placebo_p"].fillna(1) < 0.1) & res["neg_control_pass"].fillna(True),
                                  "supported by the DML model; matched baseline not fully balanced",
                         np.where(ex0, "interval excludes 0, but placebo or negative control fails", "no detectable drought-specific effect")))))
        if "neg_control_pass" in res:                  # the check was not run (no pre-treatment greenness): say so instead of counting it as passed
            nc = res["neg_control_pass"].isna() & res["verdict"].str.startswith("supported")
            res.loc[nc, "verdict"] = res.loc[nc, "verdict"] + " (negative control NOT run: no pre-treatment greenness)"
        if "evidence_tier" in res:
            tier = res["evidence_tier"]
            res["confidence"] = res["confidence"].where(tier != "full", np.where(res["verdict"].str.startswith("supported (all"), "high", "medium"))
            res.loc[tier == "limited", "verdict"] = "small sample: " + res["verdict"]
            res.loc[tier == "one season type", "verdict"] = "drought-specific effect not identified: effect in " + res["headline_basis"].fillna("").str.replace("effect in ", "", regex=False) + " only"
            res.loc[tier == "pooled", "verdict"] = "drought-specific effect not identified: one pooled effect over all seasons"
            res.loc[tier == "descriptive", "verdict"] = "descriptive arm gap only, not a causal estimate"
        if n_years < 2:
            one = ~res["abstain"].fillna(False).astype(bool)
            res.loc[one, "verdict"] = "one season only: gamma compares drought squares with normal squares in different places, not the same weather (not identified)"
            log("only one season in the data: theta_normal / theta_drought are within-square arm gaps; gamma is NOT identified (see verdict)")
    return res.drop(columns=["t_gamma"])


def cmd_run(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    tabf = out / "field_year_table.parquet"
    if a.reuse_table and tabf.exists():
        o = pd.read_parquet(tabf)
        if a.max_year is None:
            a.max_year = int(o["year"].max())
        xcols = covariate_columns(o, a)
        log(f"reusing {tabf}: {len(o):,} field-years (inputs not re-read)")
    else:
        o = read_inputs(a)
        xcols = covariate_columns(o, a)
        log(f"{len(o):,} field-years, {o['CSBID'].nunique():,} fields, {o['stratum'].nunique()} squares; covariates {xcols}")
        o = o[(o["n_observed_steps"] >= a.min_steps) & o["drought"].notna() & (o["year"] <= a.max_year)]
        o = o[o["peak_ndvi"] >= 0.5]                             # a crop that never greened is a CDL or centroid miss (17)
        o.to_parquet(tabf, index=False)                          # the prepared table: --reuse-table skips all input reading next time
    fe_dir = Path(RES["tmp"]) / "field_effects"
    if fe_dir.exists():
        for f in fe_dir.glob("*.parquet"):
            f.unlink()
    fe_dir.mkdir(parents=True, exist_ok=True)
    n_fe = 0
    all_rows, all_bal, diag = [], [], []
    use_forest = (not a.no_forest) and has_econml()
    if not a.no_forest and not use_forest:
        log("econml not installed: causal forest and field-level estimates skipped (pip install econml)")
    for crop in a.crops:
        code = CROPS[crop]
        dcrop = o[o["crop_t"] == code].copy()
        if dcrop.empty:
            log(f"{crop}: no field-years"); continue
        outs = pick_outcomes(o, crop, a)
        dg = outcome_diagnostics(o[o["year"] <= a.max_year], crop, outs, a)
        diag += dg
        sees = {r["outcome"]: r["sees_drought"] for r in dg}
        log(f"{crop}: {len(dcrop):,} field-years; outcomes {outs}; outcomes that see the drought: {[k for k, v in sees.items() if v]}")
        T = make_treatments(dcrop, code, a)
        forest_outs = a.forest_outcomes or [r["outcome"] for r in sorted(dg, key=lambda r: -abs(np.nan_to_num(r["sd_units"]))) if r["sees_drought"] and r["outcome"] not in NO_GAMMA][:a.n_forest_outcomes] or [outs[0]]
        for tr in a.treatments:
            d = dcrop.join(T[[tr]]).dropna(subset=[tr])
            if d.empty:
                log(f"  {crop} {tr}: treatment not defined for any field-year"); continue
            # adjustment ladder: hold the other rotation-history indicators fixed; T2 and T3 are nested (small grain or hay IS a third crop
            # group), so when that destroys overlap fall back to T1 only, then to none, and say so in the output
            skip = {tr, "T5" if tr == "T1" else "T1" if tr == "T5" else tr}
            others = [k for k in TREATMENTS if k not in skip and T[k].notna().sum() > 0]
            ladder = [others] if a.adjust_history else [[]]
            if a.adjust_history and others:
                if [k for k in others if k == "T1"] and len(others) > 1:
                    ladder.append(["T1"])
                ladder.append([])
            t0 = time.time()
            best = None
            for adj in ladder:
                xtr = list(xcols)
                for k in adj:
                    dcrop[f"hist_{k}"] = T[k]
                    xtr.append(f"hist_{k}")
                d = dcrop.join(T[[tr]]).dropna(subset=[tr])
                rows, bal = estimate_pair(d, crop, tr, xtr, outs, a, rng, None)
                rank = min([TIER_RANK.get(r.get("evidence_tier"), 5) if not r.get("abstain") else 5 for r in rows] or [5])
                if best is None or rank < best[0]:
                    best = (rank, rows, bal, adj, list(xtr), d)
                if rank <= 1:                                        # full or limited: no need to weaken the adjustment
                    break
            _, rows, bal, adj, xtr, d = best
            gc.collect()
            tag = "+".join(adj) if adj else "none"
            for r in rows:
                r["adjusted_for"] = tag
                if a.adjust_history and adj != others and others:
                    r["adjustment_note"] = "other treatments could not all be held fixed (nested definitions break overlap)"
            for r in rows:
                r["outcome_sees_drought"] = sees.get(r["outcome"])
            all_rows += rows
            all_bal += bal
            ok = [r for r in rows if not r.get("abstain")]
            tier_ = ok[0]["evidence_tier"] if ok else None
            log(f"  {crop} {tr}: " + (f"{len(ok)} outcome estimates, evidence tier '{tier_}'" if ok else "ABSTAIN - " + rows[0]["abstain_reason"]) + f" ({time.time() - t0:.0f}s)")
            if use_forest and ok and tier_ in ("full", "limited"):
                dd = d.copy(); dd["T"] = dd[tr].astype(float)
                dd = dd[dd["drought"] == 1]
                if a.predict_fields == "all":
                    targets = dcrop.sort_values("year").drop_duplicates("CSBID", keep="last")
                elif Path(a.predict_fields).exists() and {"centroid_lat", "centroid_lon"} <= set(pd.read_csv(a.predict_fields, nrows=1).columns):
                    targets = pd.read_csv(a.predict_fields, dtype={"CSBID": str})          # fields outside the sample: coordinates + soil / terrain / area
                    if "CSBID" not in targets:
                        targets["CSBID"] = [f"query_{i}" for i in range(len(targets))]
                    if "log_area" not in targets and "area_acres" in targets:
                        targets["log_area"] = np.log(targets["area_acres"].astype(float))
                else:
                    ids = a.predict_fields.split(",") if not Path(a.predict_fields).exists() else pd.read_csv(a.predict_fields, dtype=str).iloc[:, 0].tolist()
                    targets = dcrop[dcrop["CSBID"].astype(str).isin(ids)].sort_values("year").drop_duplicates("CSBID", keep="last")
                for y in forest_outs:
                    if y not in outs or y in NO_GAMMA:
                        continue
                    r = next((r for r in ok if r["outcome"] == y), None)
                    if r is None:
                        continue
                    try:
                        fe_ = field_estimates(dd, crop, tr, y, xtr, a, targets, None)
                    except Exception as e:
                        log(f"    forest {crop} {tr} {y} failed: {e}"); continue
                    if fe_ is not None:
                        fe_["expected_sign"] = TREATMENTS[tr]["expected"]
                        fe_.to_parquet(fe_dir / f"{n_fe:05d}.parquet", index=False)            # spilled to disk, not kept in memory
                        n_fe += 1
                        del fe_
        cc = county_check(o, crop, a)
        if cc is not None:
            cc.to_csv(out / f"county_check_{crop}.csv", index=False)
            log(f"{crop} county check:\n" + cc.round(4).to_string(index=False))
    res = add_verdicts(pd.DataFrame(all_rows), o["year"].nunique())
    res.to_csv(out / "effects.csv", index=False)
    pd.DataFrame(all_bal).to_csv(out / "balance.csv", index=False)
    pd.DataFrame(diag).to_csv(out / "outcome_diagnostics.csv", index=False)
    fe_files = sorted(fe_dir.glob("*.parquet"))
    if fe_files:
        import pyarrow as pa
        import pyarrow.csv as pacsv
        import pyarrow.parquet as pq
        schema = pa.unify_schemas([pq.read_schema(f) for f in fe_files], promote_options="permissive")
        n_rows = n_ok = n_lim = 0
        with pq.ParquetWriter(out / "field_effects.parquet", schema) as pw, open(out / "field_effects.csv", "wb") as cf:
            first = True
            for f in fe_files:                                     # one block at a time
                t = pq.read_table(f).cast(schema)
                pw.write_table(t)
                pacsv.write_csv(t, cf, write_options=pacsv.WriteOptions(include_header=first)); first = False
                n_rows += t.num_rows
                n_ok += int(sum(1 for v in t.column("status").to_pylist() if v == "ok"))
                n_lim += int(sum(1 for v in t.column("status").to_pylist() if v == "limited evidence"))
        log(f"field-level estimates: {n_rows:,} rows ({n_ok / max(n_rows, 1):.0%} ok, {n_lim / max(n_rows, 1):.0%} limited evidence, rest insufficient)")
        for f in fe_files:
            f.unlink()
    write_report(out, res, diag, a)
    log(f"written to {out}")


def write_report(out, res, diag, a):
    L = ["# M2 Neighbour Evidence - results", "", f"Evidence label: **{EVIDENCE_LABEL}**.", "", "Limits (every output):"]
    L += [f"- {x}" for x in LIMITS]
    L += ["", "gamma = extra effect of the treated arm in drought seasons beyond its effect in normal seasons (neighbours under the same weather).",
          "Expected sign for 'resilience' by treatment: T1 (continuous crop) negative; T2-T5 positive.", ""]
    if diag:
        L += ["## Does the outcome see the drought?", "", pd.DataFrame(diag).round(4).to_markdown(index=False), ""]
    if len(res):
        show = res[~res["abstain"]]
        cols = [c for c in ("crop", "treatment", "outcome", "evidence_tier", "confidence", "headline_basis", "headline_effect", "headline_lo", "headline_hi",
                            "gamma", "gamma_lo", "gamma_hi", "theta_normal", "gamma_placebo_p", "balance_pass",
                            "neg_control_pass", "sign_agrees_with_expected", "verdict") if c in show.columns]
        L += ["## Estimates", "", show[cols].round(4).to_markdown(index=False) if len(show) else "none", ""]
        ab = res[res["abstain"]].drop_duplicates(["crop", "treatment"])
        if len(ab):
            L += ["## Abstentions", ""] + [f"- {r.crop} {r.treatment}: {r.abstain_reason}" for r in ab.itertuples()] + [""]
    (out / "report.md").write_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "run"])
    ap.add_argument("--attrs", required=True, help="csb_pipeline.py ingest folder (batch_*.parquet with CDL<yyyy>)")
    ap.add_argument("--ts", nargs="+", required=True, help="crop_ts_s1.py compose outputs (folders, tabular.parquet files or globs), one per year")
    ap.add_argument("--drought", required=True, help="csb_drought.py weekly parquet (CSBID, valid_date, dm)")
    ap.add_argument("--state", default="19", help="state FIPS, comma list or all (default 19 = Iowa)")
    ap.add_argument("--ssurgo"); ap.add_argument("--power-daily", dest="power_daily"); ap.add_argument("--cellmap-power", dest="cellmap_power")
    ap.add_argument("--smap-daily", dest="smap_daily"); ap.add_argument("--cellmap-smap", dest="cellmap_smap"); ap.add_argument("--nass-yield", dest="nass_yield")
    ap.add_argument("--ecostress"); ap.add_argument("--cdl-extra", dest="cdl_extra", help="parquet CSBID, year, cdl: extra years of crop history")
    ap.add_argument("--grid-km", dest="grid_km", type=float, default=20.0, help="side of the square that defines a field's neighbourhood (stratum)")
    ap.add_argument("--drought-weeks", dest="drought_weeks", type=int, default=4, help="USDM maps with D2+ in July-August that make a drought season")
    ap.add_argument("--drought-years", dest="drought_years", type=int, nargs="+", help="years fully covered by --drought (default: first..last year of its valid_date)")
    ap.add_argument("--drought-def", dest="drought_def", choices=["usdm", "smap", "either"], default="usdm")
    ap.add_argument("--smap-days", dest="smap_days", type=int, default=30, help="days below the cell's p20 of July-August root-zone moisture (smap definition)")
    ap.add_argument("--memory", default="4GB", help="DuckDB memory limit for the joins over attrs / drought / POWER / SMAP (spills to --tmp beyond it)")
    ap.add_argument("--tmp", help="spill / scratch folder (default <out>/_tmp)")
    ap.add_argument("--chunk-rows", dest="chunk_rows", type=int, default=200000, help="rows per batch when reading the tensors and predicting the forest")
    ap.add_argument("--reuse-table", dest="reuse_table", action="store_true", help="run: reuse <out>/field_year_table.parquet instead of reading the inputs again")
    ap.add_argument("--county-min-fields", dest="county_min_fields", type=int, default=20, help="min sampled fields per county-year for the county check (both crops unless overridden below)")
    ap.add_argument("--county-min-fields-corn", dest="county_min_fields_corn", type=int, default=10, help="overrides --county-min-fields for corn")
    ap.add_argument("--county-min-fields-soybeans", dest="county_min_fields_soybeans", type=int, default=5, help="overrides --county-min-fields for soybeans")
    ap.add_argument("--out")
    ap.add_argument("--crops", nargs="+", default=["corn", "soybeans"], choices=list(CROPS))
    ap.add_argument("--treatments", nargs="+", default=["T1", "T2", "T3", "T4", "T5"], choices=list(TREATMENTS))
    ap.add_argument("--covariates"); ap.add_argument("--winter-cover"); ap.add_argument("--crop-labels"); ap.add_argument("--openet")
    ap.add_argument("--label-min-prob", dest="label_min_prob", type=float, default=0.9)
    ap.add_argument("--t2-window", dest="t2_window", type=int, default=3, help="years of history for T2 (5 as in the proposal; 3 because CSB gives CDL 2018-2025 only)")
    ap.add_argument("--max-year", dest="max_year", type=int, default=None, help="last season used in the effects (default: the last CDL year in --attrs)")
    ap.add_argument("--min-steps", dest="min_steps", type=int, default=8)
    ap.add_argument("--learner", choices=["hgb", "lgbm"], default="hgb")
    ap.add_argument("--n-splits", dest="n_splits", type=int, default=5)
    ap.add_argument("--fast", action="store_true", help="smaller nuisance models")
    ap.add_argument("--reps", type=int, default=499, help="cluster-bootstrap draws")
    ap.add_argument("--placebo-reps", dest="placebo_reps", type=int, default=200)
    ap.add_argument("--min-arm", dest="min_arm", type=int, default=100)
    ap.add_argument("--min-units", dest="min_units", type=int, default=5)
    ap.add_argument("--soft-arm", dest="soft_arm", type=int, default=20, help="limited tier: min fields in the smaller arm of EACH season type")
    ap.add_argument("--soft-units", dest="soft_units", type=int, default=2, help="limited / one-season-type / pooled tiers: min squares with both arms")
    ap.add_argument("--pooled-arm", dest="pooled_arm", type=int, default=10, help="pooled tier: min fields in the smaller arm over all seasons")
    ap.add_argument("--strict", action="store_true", help="old behaviour: abstain unless the full thresholds are met (no limited / pooled / descriptive tiers)")
    ap.add_argument("--max-radius-km", dest="max_radius_km", type=float, default=120.0, help="field what-if: widen the neighbour radius (x2 steps) up to this")
    ap.add_argument("--min-comparable-soft", dest="min_comparable_soft", type=int, default=10, help="field what-if: 'limited evidence' needs this many per arm")
    ap.add_argument("--min-overlap", dest="min_overlap", type=float, default=0.5)
    ap.add_argument("--min-extra-outcome", dest="min_extra_outcome", type=int, default=1000)
    ap.add_argument("--no-adjust-history", dest="adjust_history", action="store_false",
                    help="by default each treatment is estimated holding the other rotation-history indicators fixed (T1/T5 excepted)")
    ap.add_argument("--n-forest-outcomes", dest="n_forest_outcomes", type=int, default=2)
    ap.add_argument("--no-forest", dest="no_forest", action="store_true")
    ap.add_argument("--forest-outcomes", dest="forest_outcomes", nargs="+")
    ap.add_argument("--forest-trees", dest="forest_trees", type=int, default=300)
    ap.add_argument("--predict-fields", dest="predict_fields", default="all",
                    help="all (sample fields) | comma list of CSBID | csv of CSBID | csv with centroid_lat, centroid_lon, area_acres (+ the soil / terrain columns of --covariates) for any field")
    ap.add_argument("--scenario-d2", dest="scenario_d2", type=float, help="drought intensity (D2+ weeks in Jul-Aug) for the field what-if; default: median of drought seasons")
    ap.add_argument("--radius-km", dest="radius_km", type=float, default=30.0)
    ap.add_argument("--min-comparable", dest="min_comparable", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    RES.update(memory=a.memory, tmp=a.tmp or (str(Path(a.out) / "_tmp") if a.out else __import__("tempfile").gettempdir()))
    if a.cmd == "check":
        return cmd_check(a)
    if not a.out:
        sys.exit("--out required")
    cmd_run(a)


if __name__ == "__main__":
    main()