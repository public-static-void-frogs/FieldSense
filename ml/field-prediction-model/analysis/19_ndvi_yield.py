"""NDVI -> yield: a county yield model on HLS greenness, used as a field yield proxy for M2.

Peak NDVI saturates (17), so M2 needs an outcome in bushels. NASS publishes yield per county only, so the
model is fitted at county level and then applied to single fields:
- sample: in every one of the 99 counties, the 7.68 km HLS block (one 256 x 256 COG block) with the most corn
  and soybean fields >= 5 acres; HLS 2020-2025 read with 16's functions into the same 16-step tensor;
- crops: CDL from 07's table for 2020-2024; for 2025 (no CDL) the M1 reference classifier's confident calls;
- features per county-year and crop: medians over the county's fields of that crop of peak NDVI (steps 7-12),
  late NDVI (12-13), NDWI of July-August (8-11) and the NDVI area (6-13); also the full curve (steps 4-14);
- target: the county's NASS yield relative to its own linear trend (fitted on all other years, 1990-2025);
- two models, both scored leaving one year out: across years (does greenness beat the trend?) and within a
  year (features and target as deviations from that year's mean over counties: does greenness rank counties?).
  With six years, the across-year model has almost nothing to learn from; M2 compares neighbours within a year,
  so the within-year model is the one its proxy uses;
- field proxy: the within-year model applied to one field's deviation from the year's county mean, times the
  county trend: bu/ac relative to the state's year. The M2 contrast of 17 is re-run with it (square x year
  effects absorb the year level), and its drought effect is not identified by construction, so only the arm
  gaps are reported.

Usage: python 19_ndvi_yield.py --data path/to/Field-Shift-NASA-data --out m2/effect/ [--skip-download]
"""
import argparse
import importlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV

sys.path.insert(0, str(Path(__file__).parent))
hls = importlib.import_module("16_hls_greenness")
m2 = importlib.import_module("17_m2_drought_effect")

YEARS = range(2020, 2026)
FEATS = [f"{i}_d{k}" for i in ("ndvi", "ndwi") for k in range(4, 15)]          # late April .. early October
SUMMARY = ["peak", "late", "ndwi_jul_aug", "area"]
CROPS = {1: "CORN", 5: "SOYBEANS"}


def county_blocks(D):
    tl = hls.tiles(D / "greenness/stac")
    fields = pd.read_parquet(D / "field_daily_2025/fields.parquet", columns=["CSBID", "county_fips", "centroid_lon", "centroid_lat", "area_acres", "field_cdl_prev1"])
    f = hls.assign(fields, tl)
    f = f[(f.area_acres >= hls.MIN_ACRES) & f.field_cdl_prev1.isin([1, 5])].copy()
    f["unit"] = f.tile + "_b" + (f.r30 // hls.BLOCK).astype(str) + "_" + (f.c30 // hls.BLOCK).astype(str)
    best = f.groupby(["county_fips", "unit"]).size().rename("n").reset_index().sort_values("n").groupby("county_fips").tail(1)
    s = f[f.unit.isin(best.unit)].copy()
    s = s[s.county_fips == s.unit.map(best.set_index("unit").county_fips)]
    s["ulx"], s["uly"] = s.tile.map({k: v["ulx"] for k, v in tl.items()}), s.tile.map({k: v["uly"] for k, v in tl.items()})
    return s


def download(D, out, sample, workers=12):
    cache = out / "stac"
    cache.mkdir(parents=True, exist_ok=True)
    for year in YEARS:
        if (out / f"hls_tensor_{year}.parquet").exists():
            continue
        obs_dir = out / f"obs_{year}"
        obs_dir.mkdir(exist_ok=True)
        items = hls.scenes(sample, year, cache)
        by_tile = {t: g.reset_index(drop=True) for t, g in sample.groupby("tile")}
        todo = [(it, by_tile[it["tile"]], obs_dir / f"{it['id']}.parquet") for it in items if not (obs_dir / f"{it['id']}.parquet").exists()]
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for i, fu in enumerate(as_completed([ex.submit(hls.read_item, *j) for j in todo]), 1):
                fu.result()
                if i % 100 == 0 or i == len(todo):
                    print(f"  {year}: {i}/{len(todo)} scenes, {(time.time() - t0) / 60:.1f} min", flush=True)
        obs = pd.concat([pd.read_parquet(p) for p in obs_dir.glob("*.parquet")], ignore_index=True)
        hls.composite(obs, year).to_parquet(out / f"hls_tensor_{year}.parquet", index=False)
        print(f"{year}: {len(items)} scenes, {len(obs):,} field-scenes, {obs.valid.mean():.1%} valid", flush=True)


def crops(D, tens):
    """CDL 2020-2024 from 07; 2025 from the M1 reference classifier (confidence >= 0.9)."""
    hist = pd.read_parquet(D / "m2/field_season_drought.parquet", columns=["CSBID", "season", "crop_t"]).rename(columns={"season": "year"})
    t = tens.merge(hist, on=["CSBID", "year"], how="left")
    clf, feats, _ = m2.m1_classifier(D)
    p = clf.predict_proba(t[feats])
    lab = clf.classes_[p.argmax(axis=1)]
    guess = np.where((lab == "Corn") & (p.max(axis=1) >= 0.9), 1, np.where((lab == "Soybeans") & (p.max(axis=1) >= 0.9), 5, np.nan))
    t["crop_t"] = np.where(t.year == 2025, guess, t.crop_t)
    return t


def summaries(t):
    nd, nw = t[[f"ndvi_d{k}" for k in range(1, 17)]].to_numpy(), t[[f"ndwi_d{k}" for k in range(1, 17)]].to_numpy()
    return t.assign(peak=nd[:, 6:12].max(axis=1), late=nd[:, 11:13].mean(axis=1), ndwi_jul_aug=nw[:, 7:11].mean(axis=1),
                    area=nd[:, 5:13].sum(axis=1))


def trend_ratio(panel):
    """Yield relative to the county's linear trend fitted on all other years (no year sees itself)."""
    out = []
    for (crop, fips), g in panel.groupby(["crop", "county_fips"]):
        for y in g.year:
            tr = g[g.year != y]
            b, a = np.polyfit(tr.year, tr.yield_bu_acre, 1)
            out.append({"crop": crop, "county_fips": fips, "year": y, "trend": a + b * y})
    p = panel.merge(pd.DataFrame(out), on=["crop", "county_fips", "year"])
    p["ratio"] = p.yield_bu_acre / p.trend
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()
    D, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 220)
    gy = D / "greenness_yield"
    gy.mkdir(exist_ok=True)
    if not (gy / "sample_fields.parquet").exists():
        s = county_blocks(D)
        s.to_parquet(gy / "sample_fields.parquet", index=False)
    sample = pd.read_parquet(gy / "sample_fields.parquet")
    print(f"yield sample: {len(sample):,} fields in {sample.unit.nunique()} blocks, {sample.county_fips.nunique()} counties, {sample.tile.nunique()} tiles")
    if not args.skip_download:
        download(D, gy, sample)

    tens = crops(D, pd.concat([pd.read_parquet(gy / f"hls_tensor_{y}.parquet") for y in YEARS], ignore_index=True))
    tens = tens.merge(sample[["CSBID", "county_fips"]], on="CSBID")
    panel = trend_ratio(pd.read_csv(D / "m11/county_panel.csv", dtype={"county_fips": str})[["county_fips", "year", "crop", "yield_bu_acre"]].dropna())
    rows, models, means = [], {}, {}
    for code, crop in CROPS.items():
        f = summaries(tens[(tens.crop_t == code) & (tens.n_observed_steps >= 8)])
        cy = f.groupby(["county_fips", "year"])[SUMMARY + FEATS].median().join(f.groupby(["county_fips", "year"]).size().rename("n_fields"))
        cy = cy[cy.n_fields >= 20].reset_index().merge(panel[panel.crop == crop], on=["county_fips", "year"])
        means[code] = cy.groupby("year")[SUMMARY].mean()
        for c in SUMMARY + FEATS + ["ratio"]:
            cy[c + "_w"] = cy[c] - cy.groupby("year")[c].transform("mean")
        for kind, feats, target in (("across years, full curve", FEATS, "ratio"), ("within year, 4 summaries", [c + "_w" for c in SUMMARY], "ratio_w"),
                                    ("within year, full curve", [c + "_w" for c in FEATS], "ratio_w")):
            pred = pd.Series(index=cy.index, dtype=float)
            for y in sorted(cy.year.unique()):
                tr, te = cy[cy.year != y], cy[cy.year == y]
                pred[te.index] = RidgeCV(alphas=np.logspace(-2, 4, 25)).fit(tr[feats], tr[target]).predict(te[feats])
            base = (1 - cy.ratio) if target == "ratio" else -cy.ratio_w           # trend / "every county at the year mean"
            r_y = [np.corrcoef(pred[cy.year == y], cy[target][cy.year == y])[0, 1] for y in sorted(cy.year.unique())]
            rows.append({"crop": crop, "model": kind, "county_years": len(cy), "years": cy.year.nunique(),
                         "rmse_model_bu": np.sqrt((((pred - cy[target]) * cy.trend) ** 2).mean()),
                         "rmse_baseline_bu": np.sqrt(((base * cy.trend) ** 2).mean()),
                         "r_within_year_median": np.median(r_y), "r_by_year": [round(v, 2) for v in r_y]})
        cy.to_csv(out / f"ndvi_yield_county_{crop.lower()}.csv", index=False)
        models[code] = RidgeCV(alphas=np.logspace(-2, 4, 25)).fit(cy[[c + "_w" for c in SUMMARY]], cy.ratio_w)
        slope = models[code].coef_ * cy.trend.mean()
        print(f"{crop}: within-year model, bu/ac per unit of " + ", ".join(f"{c} {v:+.1f}" for c, v in zip(SUMMARY, slope)))
    res = pd.DataFrame(rows)
    print("\nNDVI -> yield, leave one year out (baseline: trend across years; the year's mean within a year):")
    print(res.round(3).to_string(index=False))
    res.to_csv(out / "ndvi_yield_skill.csv", index=False)

    # field proxy on the M2 sample (deviation from the year's county mean), and the M2 arm gaps in bushels
    o = pd.read_parquet(out / "field_year_outcomes.parquet")
    t2 = summaries(pd.concat([pd.read_parquet(D / f"greenness/hls_tensor_{y}.parquet") for y in (2021, 2023, 2024)], ignore_index=True))
    o = o.drop(columns=[c for c in SUMMARY if c in o]).merge(t2[["CSBID", "year"] + SUMMARY], on=["CSBID", "year"])
    trend = panel[["county_fips", "year", "crop", "trend"]]
    res2 = []
    for code, crop in CROPS.items():
        d = o[(o.n_observed_steps >= 8) & (o.crop_t == code) & o.crop_t1.isin([1, 5]) & (o.peak_ndvi >= 0.5) & (o.year <= 2024)].copy()
        d = d.merge(trend[trend.crop == crop], on=["county_fips", "year"])
        dev = d[SUMMARY].to_numpy() - means[code].loc[d.year, SUMMARY].to_numpy()
        d["yield_proxy_dev"] = models[code].predict(pd.DataFrame(dev, columns=[c + "_w" for c in SUMMARY])) * d.trend
        d["mono"] = (d.crop_t1 == code).astype(float)
        d["mono_x_drought"] = d.mono * d.drought
        b, n, g = m2.fe_ols(d, "yield_proxy_dev", ["mono", "mono_x_drought", "log_area"], "unit_year", "unit")
        lo, hi = m2.bootstrap(d, "yield_proxy_dev", ["mono", "mono_x_drought", "log_area"], "unit_year", "unit", "mono_x_drought", 499)
        res2.append({"crop": crop, "field_years": n, "squares": g, "mono_normal_gap_bu": b.coef["mono"], "mono_se": b.se["mono"],
                     "mono_x_drought_bu": b.coef["mono_x_drought"], "mono_x_drought_se": b.se["mono_x_drought"], "boot_lo": lo, "boot_hi": hi})
        d[["CSBID", "year", "unit", "yield_proxy_dev"]].to_parquet(out / f"yield_proxy_{crop.lower()}.parquet", index=False)
    res2 = pd.DataFrame(res2)
    print("\nM2 arm gaps with the within-year yield proxy (bu/ac), 2021-2024:"); print(res2.round(2).to_string(index=False))
    res2.to_csv(out / "m2_yield_proxy_estimates.csv", index=False)


if __name__ == "__main__":
    main()
