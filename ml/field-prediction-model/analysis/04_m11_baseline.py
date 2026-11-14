"""Baseline county-yield experiments (Sivozmina m11) on the backfilled county panel.

Every model predicts a county's corn or soybean yield for year t from information available before
planting: the county trend, last years' yields, the previous summer's weather (POWER, May-Sep of t-1),
the April drought map of t and the crop shares of t-1. One extra run uses the same summer's weather
(May-Sep of t) as an "oracle" upper bound: it shows how much of the yield is decided after planting.

Validation is by year: leave-one-year-out (LOYO) and, more realistic, forward chaining (train on years
before t only). A final diagnostic trains on field rows to show how a random row split leaks the label.

Usage: python 04_m11_baseline.py --dataset path/to/field_dataset --panel county_panel.csv \
         --power power_seasons.csv --context county_context.csv --out results_dir
"""
import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

WEATHER = ["t2m_mean", "tmin_mean", "tmax_mean", "cold_days", "hot_days", "precip_sum", "dry_days", "solar_sum"]
PREV = [f"prev_{w}" for w in WEATHER]
SAME = [f"same_{w}" for w in WEATHER]
LAGS = ["lag1_ratio", "prev3_ratio"]
DROUGHT = ["usdm_class_april", "usdm_d1plus_share_april"]
SHARES = ["cdl_corn_frac"]  # corn / (corn + soy) in t-1; the only CDL share comparable across 2000-2024 (see script 03)
CSB_SHARES = ["corn_share_prev1", "soy_share_prev1", "corn_to_soy_share_prev2", "soy_to_corn_share_prev2", "corn_corn_share_prev2"]
RNG = 0


def county_weather(dataset, power):
    """Area-weighted county weather per season year from cell seasons."""
    con = duckdb.connect()
    w = con.execute(f"""SELECT county_fips, power_cell_id, sum(area_acres) AS w FROM (
        SELECT DISTINCT CSBID, county_fips, power_cell_id, area_acres
        FROM read_parquet('{dataset}/year=*/part.parquet', union_by_name = true)) GROUP BY 1, 2""").df()
    m = w.merge(power, on="power_cell_id")
    agg = m.groupby(["county_fips", "season_year"]).apply(
        lambda g: pd.Series({c: np.average(g[c], weights=g.w) for c in WEATHER}), include_groups=False)
    return agg.reset_index()


def build(args):
    panel = pd.read_csv(args.panel, dtype={"county_fips": str})
    power = pd.read_csv(args.power)
    ctx = pd.read_csv(args.context, dtype={"county_fips": str})
    cw = county_weather(args.dataset, power)
    prev = cw.rename(columns={c: f"prev_{c}" for c in WEATHER}).assign(year=lambda d: d.season_year + 1)
    same = cw.rename(columns={c: f"same_{c}" for c in WEATHER}).assign(year=lambda d: d.season_year)
    df = (panel.merge(prev.drop(columns="season_year"), on=["county_fips", "year"], how="left")
               .merge(same.drop(columns="season_year"), on=["county_fips", "year"], how="left")
               .merge(ctx, on=["county_fips", "year"], how="left"))
    # sanity: the backfilled previous-summer weather equals the dataset's own county values where both exist
    both = df.dropna(subset=["power_hot_days_prev_season"])
    assert np.allclose(both.prev_hot_days, both.power_hot_days_prev_season, atol=1e-6)
    return df


def add_trend(train, test):
    """Per-county linear trend fitted on the training years only; lag features as ratios to it."""
    out = []
    for (crop, fips), g in test.groupby(["crop", "county_fips"]):
        tr = train[(train.crop == crop) & (train.county_fips == fips)]
        if len(tr) >= 3:
            b, a = np.polyfit(tr.year, tr.yield_bu_acre, 1)
        else:
            b, a = 0.0, tr.yield_bu_acre.mean() if len(tr) else np.nan
        g = g.assign(trend=a + b * g.year)
        out.append(g)
    t = pd.concat(out)
    return t.assign(lag1_ratio=t.yield_lag1 / t.trend, prev3_ratio=t.yield_mean_prev3 / t.trend)


def run(df, features, years, mode, model="ridge"):
    """Predict yield = county trend + model(residual). mode: 'loyo' or 'forward'."""
    preds = []
    for t in years:
        train = df[(df.year != t) if mode == "loyo" else (df.year < t)]
        test = df[df.year == t]
        assert t not in set(train.year)
        if test.empty or train.year.nunique() < 5:
            continue
        test = add_trend(train, test)
        if features:
            tr = add_trend(train, train).dropna(subset=features + ["trend"])
            tr = tr[tr.year != t]
            X, y = tr[features], tr.yield_bu_acre - tr.trend
            est = (make_pipeline(StandardScaler(), Ridge(alpha=1.0)) if model == "ridge"
                   else HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                                      min_samples_leaf=20, random_state=RNG))
            est.fit(X, y)
            ok = test.dropna(subset=features)
            test = ok.assign(pred=ok.trend + est.predict(ok[features]))
        else:
            test = test.assign(pred=test.trend)
        preds.append(test)
    return pd.concat(preds) if preds else pd.DataFrame()


def score(p):
    p = p.dropna(subset=["pred", "yield_mean_prev3"])
    e = p.pred - p.yield_bu_acre
    base = p.yield_mean_prev3 - p.yield_bu_acre
    rmse, rmse_b = np.sqrt((e ** 2).mean()), np.sqrt((base ** 2).mean())
    return {"n": len(p), "years": p.year.nunique(), "rmse": rmse, "mae": e.abs().mean(),
            "rmse_prev3_mean": rmse_b, "skill_vs_prev3": 1 - rmse / rmse_b}


def experiments(df):
    rows, per_year = [], []
    sets = {
        "E1 1991-2025": (range(1991, 2026), {
            "trend only": [], "+ yield lags": LAGS, "+ prev-summer weather": LAGS + PREV,
            "oracle: same-summer weather": LAGS + SAME}),
        "E2 2001-2025": (range(2001, 2026), {
            "trend only": [], "+ yield lags": LAGS, "+ prev-summer weather": LAGS + PREV,
            "+ April drought": LAGS + PREV + DROUGHT, "+ CDL shares t-1": LAGS + PREV + DROUGHT + SHARES,
            "oracle: same-summer weather": LAGS + SAME}),
        "E3 2020-2025 (table as delivered)": (range(2020, 2026), {
            "trend only": [], "+ yield lags": LAGS, "+ prev-summer weather": LAGS + PREV,
            "+ April drought (dataset)": LAGS + PREV + ["drought_class_april", "drought_d1plus_share_april"],
            "+ CSB neighbour shares": LAGS + PREV + ["drought_class_april", "drought_d1plus_share_april"] + CSB_SHARES}),
    }
    for exp, (years, fsets) in sets.items():
        sub = df[df.year >= (1990 if exp.startswith("E1") else 2000 if exp.startswith("E2") else 2019)]
        for crop in ("CORN", "SOYBEANS"):
            c = sub[sub.crop == crop]
            for mode in ("loyo", "forward"):
                if exp.startswith("E3") and mode == "forward":
                    continue  # too few years to train forward
                for name, feats in fsets.items():
                    for model in (("ridge", "hgb") if feats else ("trend",)):
                        p = run(c, feats, years, mode, model if model != "trend" else "ridge")
                        if p.empty:
                            continue
                        rows.append({"experiment": exp, "crop": crop, "cv": mode, "features": name, "model": model, **score(p)})
                        if mode == "loyo" and model in ("ridge", "trend"):
                            py = p.groupby("year").apply(lambda g: np.sqrt(((g.pred - g.yield_bu_acre) ** 2).mean()),
                                                         include_groups=False)
                            per_year.append(pd.DataFrame({"experiment": exp, "crop": crop, "features": name,
                                                          "year": py.index, "rmse": py.values}))
    return pd.DataFrame(rows), pd.concat(per_year)


def importance(df):
    """Permutation importance of the full E2 gradient-boosting model, corn, all 2001-2025 years pooled."""
    c = df[(df.crop == "CORN") & (df.year >= 2001)]
    c = add_trend(c, c).dropna(subset=LAGS + PREV + DROUGHT + SHARES)
    feats = LAGS + PREV + DROUGHT + SHARES
    est = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20,
                                        random_state=RNG).fit(c[feats], c.yield_bu_acre - c.trend)
    r = permutation_importance(est, c[feats], c.yield_bu_acre - c.trend, n_repeats=10, random_state=RNG)
    return pd.DataFrame({"feature": feats, "importance": r.importances_mean}).sort_values("importance", ascending=False)


def leakage_demo(dataset):
    """Field rows 2019-2025: random split vs year-grouped split, same model and features."""
    con = duckdb.connect()
    f = con.execute(f"""SELECT * FROM (
        SELECT year, yield_bu_acre, centroid_lon, centroid_lat, area_acres, field_corn_prev1, field_soy_prev1,
               field_prev1_is_candidate_crop, power_hot_days_prev_season, power_precip_prev_season_sum, power_t2m_prev_season_mean
        FROM read_parquet('{dataset}/year=*/part.parquet', union_by_name = true)
        WHERE crop = 'CORN' AND year >= 2019) USING SAMPLE reservoir(300000 ROWS) REPEATABLE (42)""").df()
    X, y = f.drop(columns=["yield_bu_acre"]), f.yield_bu_acre
    out = {}
    rng = np.random.default_rng(RNG)
    test_rand = rng.random(len(f)) < 0.2
    for name, test in {"random 80/20 rows": test_rand, "hold out 2024": (f.year == 2024).to_numpy()}.items():
        est = HistGradientBoostingRegressor(max_iter=300, random_state=RNG).fit(X[~test].drop(columns="year"), y[~test])
        e = est.predict(X[test].drop(columns="year")) - y[test]
        out[name] = {"rmse_bu_acre": float(np.sqrt((e ** 2).mean())), "n_test_rows": int(test.sum())}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--panel", required=True)
    ap.add_argument("--power", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    df = build(args)
    df.to_csv(out / "county_panel_backfilled.csv", index=False)
    res, per_year = experiments(df)
    res.to_csv(out / "results.csv", index=False)
    per_year.to_csv(out / "per_year_rmse.csv", index=False)
    imp = importance(df)
    imp.to_csv(out / "importance_corn_e2.csv", index=False)
    leak = leakage_demo(args.dataset)
    pd.DataFrame(leak).T.to_csv(out / "leakage_demo.csv")

    pd.set_option("display.width", 200)
    print(res.round(3).to_string(index=False))
    print("\nPer-year RMSE (LOYO), selected years:")
    sel = per_year[per_year.year.isin([1993, 2012, 2020, 2023])]
    print(sel.pivot_table(index=["experiment", "crop", "features"], columns="year", values="rmse").round(1).to_string())
    print("\nPermutation importance (corn, E2, gradient boosting):")
    print(imp.round(4).to_string(index=False))
    print("\nLeakage demo (corn field rows 2019-2025):", leak)


if __name__ == "__main__":
    main()
