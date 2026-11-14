"""First M2 estimate (m10 v0): did continuous corn hold up worse than rotated corn in the 2021 and 2023 droughts?

Fields: the HLS sample of 16 (32 squares of ~20 km; 24 had USDM drought seasons in 2021 and/or 2023, 8 never).
Outcomes per field-year from the 16-step HLS tensor: peak NDVI (max of steps 7-12, late June - early September),
mean NDWI of steps 8-11 (July-August, canopy water), late NDVI (steps 12-13, late August - late September:
drought speeds up senescence), the NDVI area of steps 6-13, and the green-up date (half of the season's NDVI
amplitude, interpolated); when 18 has run, ECOSTRESS mean ESI and daily ET of July-August (fields with at least
two clear overpasses). First, each outcome's plain drought signal (square and year effects): an outcome that
does not see the drought cannot show a rotation difference in it.
Arms (07, CSB/CDL): corn after corn (CC) vs corn after soybeans (SC); soybeans after soybeans vs after corn.
Drought: the field's USDM season flag (D2+ in at least 4 Jul-Aug maps, 07); as checks, the number of D2+ weeks
and the SMAP root-zone percentile of July-August (12).

Model: Y = square x year effects + b CC + g CC x drought + d log(area) (+ CC x year in the second version).
g is the extra NDVI that continuous corn loses in a drought season, beyond its normal-year gap, comparing
neighbours under the same weather. Standard errors are clustered by square and checked with a square-level
bootstrap; a placebo reassigns drought across square-years at random.
Also: the M1 reference classifier (15's set-up, trained on the M1 archive v1) applied to HLS 2021-2024 with
CDL as truth, and used to label 2025 for a robustness run; and an M3 check: green-up against modelled
planting and against NASS district 50% planted dates.

Usage: python 17_m2_drought_effect.py --data path/to/Field-Shift-NASA-data --out m2/effect/
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

YEARS = (2021, 2023, 2024, 2025)
OUTCOMES = ("peak_ndvi", "ndwi_jul_aug", "late_ndvi", "ndvi_area")
STEP_DAYS = 214 / 16
RNG = np.random.default_rng(0)
CROP = {1: "Corn", 5: "Soybeans", 36: "Alfalfa", 176: "Grassland/Pasture"}


def outcomes(t):
    nd = t[[f"ndvi_d{k}" for k in range(1, 17)]].to_numpy()
    nw = t[[f"ndwi_d{k}" for k in range(1, 17)]].to_numpy()
    lo, hi = nd.min(axis=1), nd.max(axis=1)
    half = lo + 0.5 * (hi - lo)
    k = np.argmax(nd >= half[:, None], axis=1)
    prev = np.where(k > 0, nd[np.arange(len(nd)), k - 1], np.nan)
    frac = np.where(k > 0, (half - prev) / (nd[np.arange(len(nd)), k] - prev), 0.0)
    greenup = np.where(k > 0, k - 1 + frac, 0.0)                 # 0-based step position, step i centred at i + 0.5
    return pd.DataFrame({"CSBID": t.CSBID, "year": t.year, "n_observed_steps": t.n_observed_steps,
                         "peak_ndvi": nd[:, 6:12].max(axis=1), "ndwi_jul_aug": nw[:, 7:11].mean(axis=1),
                         "late_ndvi": nd[:, 11:13].mean(axis=1), "ndvi_area": nd[:, 5:13].sum(axis=1) * STEP_DAYS,
                         "greenup_doy": 91 + (greenup + 0.5) * STEP_DAYS})


def demean(df, cols, by):
    return df[cols] - df.groupby(by)[cols].transform("mean")


def fe_ols(df, y, x, fe, cluster):
    """OLS of y on x after removing fixed effects `fe` (one categorical); CR1 standard errors by cluster."""
    d = df.dropna(subset=[y] + x)
    Y, X = demean(d, [y], fe).to_numpy().ravel(), demean(d, x, fe).to_numpy()
    keep = X.std(axis=0) > 0
    X = X[:, keep]
    xtx_inv = np.linalg.pinv(X.T @ X)
    b = xtx_inv @ X.T @ Y
    e = Y - X @ b
    g = d[cluster].to_numpy()
    meat = np.zeros((X.shape[1], X.shape[1]))
    for c in np.unique(g):
        s = X[g == c].T @ e[g == c]
        meat += np.outer(s, s)
    n, k, G = len(Y), X.shape[1] + d[fe].nunique(), len(np.unique(g))
    V = xtx_inv @ meat @ xtx_inv * G / (G - 1) * (n - 1) / (n - k)
    names = [c for c, kk in zip(x, keep) if kk]
    return pd.DataFrame({"coef": b, "se": np.sqrt(np.diag(V))}, index=names), n, G


def bootstrap(df, y, x, fe, cluster, term, reps=499):
    units = df[cluster].unique()
    out = []
    for _ in range(reps):
        pick = RNG.choice(units, len(units), replace=True)
        parts = [df[df[cluster] == u].assign(**{cluster: f"{u}#{i}", fe: df.loc[df[cluster] == u, fe] + f"#{i}"}) for i, u in enumerate(pick)]
        b, _, _ = fe_ols(pd.concat(parts, ignore_index=True), y, x, fe, cluster)
        out.append(b.coef.get(term, np.nan))
    return np.nanpercentile(out, [2.5, 97.5])


def m1_classifier(data):
    a = pd.read_parquet(Path(data) / "src/greenness_2025_v1/dataset/tabular.parquet")
    feats = [f"{i}_d{k}" for i in ("ndvi", "ndwi") for k in range(1, 17)]
    clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.06, random_state=0)
    clf.fit(a[a.split != "test"][feats], a[a.split != "test"].crop_name)
    return clf, feats, a


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reps", type=int, default=499, help="bootstrap draws; the placebo uses 200")
    args = ap.parse_args()
    D, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 220)

    sample = pd.read_parquet(D / "greenness/sample_fields.parquet")
    tens = pd.concat([pd.read_parquet(D / f"greenness/hls_tensor_{y}.parquet") for y in YEARS if (D / f"greenness/hls_tensor_{y}.parquet").exists()], ignore_index=True)
    hist = pd.read_parquet(D / "m2/field_season_drought.parquet").rename(columns={"season": "year"})
    fields = pd.read_parquet(D / "field_daily_2025/fields.parquet", columns=["CSBID", "power_cell_id", "smap_cell_id"])

    # M1 reference classifier on HLS: trained on the 2025 archive, scored on other years with CDL as truth
    clf, feats, arch = m1_classifier(D)
    tens["pred_crop"] = clf.predict(tens[feats])
    tens["pred_prob"] = clf.predict_proba(tens[feats]).max(axis=1)
    j = tens.merge(hist[["CSBID", "year", "crop_t"]], on=["CSBID", "year"], how="left")
    j["true_crop"] = j.crop_t.map(CROP)
    rows = []
    for y, g in j[j.true_crop.notna()].groupby("year"):
        cs = g[g.true_crop.isin(["Corn", "Soybeans"])]
        rows.append({"year": y, "fields": len(g), "accuracy_4_classes": np.mean(g.pred_crop == g.true_crop),
                     "corn_soy_fields": len(cs), "accuracy_corn_soy": np.mean(cs.pred_crop == cs.true_crop)})
    m1 = pd.DataFrame(rows)
    ov = tens[tens.year == 2025].merge(arch[["CSBID", "crop_name"]], on="CSBID")
    print("M1 reference classifier (trained on the 2025 archive v1) applied to HLS:"); print(m1.round(3).to_string(index=False))
    print(f"  2025 HLS vs archive labels on {len(ov)} shared fields: accuracy {np.mean(ov.pred_crop == ov.crop_name):.3f}")
    m1.to_csv(out / "m1_classifier_on_hls.csv", index=False)

    # field-year table
    o = outcomes(tens).merge(tens[["CSBID", "year", "pred_crop", "pred_prob"]], on=["CSBID", "year"])
    o = o.merge(sample[["CSBID", "unit", "kind", "area_acres", "county_fips"]], on="CSBID")
    o = o.merge(hist[["CSBID", "year", "crop_t", "crop_t1", "usdm_drought_season", "d2_jul_aug", "max_jul_aug"]], on=["CSBID", "year"], how="left")
    o = o.merge(fields, on="CSBID", how="left")
    # 2025 has no CDL: the classifier's confident corn/soybean calls stand in (robustness only)
    is25 = o.year == 2025
    o.loc[is25, "crop_t"] = np.where((o.pred_crop[is25] == "Corn") & (o.pred_prob[is25] >= 0.9), 1,
                                     np.where((o.pred_crop[is25] == "Soybeans") & (o.pred_prob[is25] >= 0.9), 5, np.nan))
    o.loc[is25, "crop_t1"] = o[is25].CSBID.map(hist[hist.year == 2025].set_index("CSBID").crop_t1)
    o.loc[is25, "usdm_drought_season"] = False
    smap = pd.read_parquet(D / "smap/smap_cropcasma_cellday_2015_2026.parquet", columns=["smap_cell_id", "date", "sm_rootzone_pctl_record"])
    smap = smap[pd.to_datetime(smap.date).dt.month.isin([7, 8])]
    smap = smap.assign(year=pd.to_datetime(smap.date).dt.year).groupby(["smap_cell_id", "year"]).sm_rootzone_pctl_record.mean().rename("smap_rz_pctl_jul_aug")
    o = o.merge(smap.reset_index(), on=["smap_cell_id", "year"], how="left")
    eco = D / "greenness/ecostress_field_year.parquet"                  # 18, when it has run
    outcomes_used = list(OUTCOMES)
    if eco.exists():
        e = pd.read_parquet(eco)
        e.loc[e.esi_n < 2, "esi_jul_aug"] = np.nan                       # one clear overpass is too noisy
        e.loc[e.et_n < 2, "et_jul_aug"] = np.nan
        o = o.merge(e[["CSBID", "year", "esi_jul_aug", "et_jul_aug", "esi_n"]], on=["CSBID", "year"], how="left")
        # the AppEEARS download can be partial (18); an outcome joins only with enough corn field-years in 2021-2024
        corn = o[(o.crop_t == 1) & (o.year <= 2024)]
        for c in ("esi_jul_aug", "et_jul_aug"):
            n = corn.groupby(["year", "kind"])[c].count().unstack(fill_value=0)
            print(f"ECOSTRESS {c}: corn field-years with >= 2 clear July-August values, by year and square kind:")
            print(n.to_string())
            if n.values.sum() >= 1000:
                outcomes_used.append(c)
            else:
                print(f"  {c} left out: too few values")
    o["drought"] = o.usdm_drought_season.astype(float)
    o["log_area"] = np.log(o.area_acres)
    o["unit_year"] = o.unit + "_" + o.year.astype(str)
    ok = (o.n_observed_steps >= 8)
    o.to_parquet(out / "field_year_outcomes.parquet", index=False)

    results = []
    for crop, same, other, name in ((1, 1, 5, "corn: after corn vs after soybeans"), (5, 5, 1, "soybeans: after soybeans vs after corn")):
        d = o[ok & (o.crop_t == crop) & o.crop_t1.isin([same, other])].copy()
        d = d[d.peak_ndvi >= 0.5]                                       # a crop that never greened is a CDL or centroid miss
        d["mono"] = (d.crop_t1 == same).astype(float)
        d["mono_x_drought"] = d.mono * d.drought
        d["mono_x_d2weeks"] = d.mono * d.d2_jul_aug
        d["mono_x_smap_dry"] = d.mono * (50 - d.smap_rz_pctl_jul_aug) / 50
        for yr in (2023, 2024, 2025):
            d[f"mono_x_{yr}"] = d.mono * (d.year == yr)
        n = d.groupby(["year", "drought", "mono"]).size().unstack(["drought", "mono"], fill_value=0)
        print(f"\n{name}: field-years by year x (drought, monoculture)"); print(n.to_string())
        # does each outcome see the drought at all? square and year effects, both arms together
        dd = d[d.year <= 2024].copy()
        for yr in (2023, 2024):
            dd[f"y{yr}"] = (dd.year == yr).astype(float)
        for y in outcomes_used:
            b, nobs, G = fe_ols(dd, y, ["drought", "y2023", "y2024", "log_area"], "unit", "unit")
            sd = dd[dd.drought == 0][y].std()
            print(f"  drought signal in {y}: {b.coef['drought']:+.4f} (se {b.se['drought']:.4f}), "
                  f"{b.coef['drought'] / sd:+.2f} SD of normal-year fields; {nobs:,} field-years, {G} squares")
            results.append({"crop": name, "sample": "2021-2024", "outcome": y, "spec": "drought main effect (square + year effects)",
                            "n": nobs, "squares": G, "term": "drought", "coef": b.coef["drought"], "se": b.se["drought"]})
        for sample_name, dd in (("2021-2024", d[d.year <= 2024]), ("2021-2025 (2025 crop from M1)", d)):
            for y in outcomes_used:
                for spec, x in (("drought flag", ["mono", "mono_x_drought", "log_area"]),
                                ("drought flag + mono x year", ["mono", "mono_x_drought", "log_area"] + [c for c in d if c.startswith("mono_x_20")]),
                                ("D2+ weeks", ["mono", "mono_x_d2weeks", "log_area"]),
                                ("SMAP dryness", ["mono", "mono_x_smap_dry", "log_area"])):
                    if sample_name != "2021-2024" and spec != "drought flag":
                        continue
                    b, nobs, G = fe_ols(dd, y, x, "unit_year", "unit")
                    term = x[1]
                    if term not in b.index:
                        continue
                    r = {"crop": name, "sample": sample_name, "outcome": y, "spec": spec, "n": nobs, "squares": G,
                         "mono_coef": b.coef.get("mono", np.nan), "mono_se": b.se.get("mono", np.nan),
                         "term": term, "coef": b.coef[term], "se": b.se[term]}
                    if spec == "drought flag" and y != "ndvi_area" and sample_name == "2021-2024":
                        r["boot_lo"], r["boot_hi"] = bootstrap(dd, y, x, "unit_year", "unit", term, args.reps)
                        # placebo: drought reassigned at random across square-years, structure kept
                        uy = dd.drop_duplicates("unit_year")[["unit_year", "drought"]]
                        plac = []
                        for _ in range(min(200, 4 * args.reps)):
                            m = dict(zip(uy.unit_year, RNG.permutation(uy.drought.to_numpy())))
                            pp = dd.assign(mono_x_drought=dd.mono * dd.unit_year.map(m))
                            plac.append(fe_ols(pp, y, x, "unit_year", "unit")[0].coef.get(term, np.nan))
                        r["placebo_p"] = np.mean(np.abs(plac) >= abs(r["coef"]))
                    results.append(r)
    res = pd.DataFrame(results)
    res["t"] = res.coef / res.se
    print("\nestimates (coef of the term; mono_coef = normal-year gap of the monoculture arm):")
    print(res.drop(columns=["crop"]).round(4).to_string(index=False))
    res.to_csv(out / "estimates.csv", index=False)

    # arm means for a plain reading
    d = o[ok & (o.crop_t == 1) & o.crop_t1.isin([1, 5]) & (o.peak_ndvi >= 0.5) & (o.year <= 2024)]
    means = d.groupby(["drought", d.crop_t1.map({1: "corn after corn", 5: "corn after soybeans"})])[[c for c in ("peak_ndvi", "ndwi_jul_aug", "late_ndvi", "esi_jul_aug", "et_jul_aug") if c in o]].mean().unstack()
    print("\ncorn field means 2021-2024 (drought = USDM drought season):"); print(means.round(4).to_string())
    means.to_csv(out / "corn_arm_means.csv")

    # does peak NDVI carry yield? county-year mean of corn fields vs NASS county yield
    panel = pd.read_csv(D / "m11/county_panel.csv", dtype={"county_fips": str})
    cy = d.groupby(["county_fips", "year"]).peak_ndvi.mean().reset_index().merge(
        panel[panel.crop == "CORN"][["county_fips", "year", "yield_bu_acre", "yield_mean_prev3"]], on=["county_fips", "year"])
    cy["anomaly"] = cy.yield_bu_acre / cy.yield_mean_prev3
    slope = np.polyfit(cy.peak_ndvi, cy.yield_bu_acre, 1)[0]
    print(f"\ncorn county-years {len(cy)}: r(peak NDVI, yield) = {cy.peak_ndvi.corr(cy.yield_bu_acre):.3f}, "
          f"r with yield / previous-3-year mean = {cy.peak_ndvi.corr(cy.anomaly):.3f}; slope {slope:.1f} bu/ac per 1.0 NDVI")
    cy.to_csv(out / "county_peak_ndvi_vs_yield.csv", index=False)
    if "esi_jul_aug" in d:
        ce = d.groupby(["county_fips", "year"]).esi_jul_aug.mean().reset_index().merge(cy[["county_fips", "year", "yield_bu_acre", "anomaly"]], on=["county_fips", "year"]).dropna()
        print(f"corn county-years {len(ce)}: r(ESI Jul-Aug, yield) = {ce.esi_jul_aug.corr(ce.yield_bu_acre):.3f}, "
              f"r with yield / previous-3-year mean = {ce.esi_jul_aug.corr(ce.anomaly):.3f}")

    # M3 check: field green-up against the modelled 50% planting of the field's POWER cell
    m3 = pd.read_parquet(D / "m3/cell_year.parquet", columns=["power_cell_id", "year", "corn_planted50_doy", "soybeans_planted50_doy"])
    g = o[ok & o.crop_t.isin([1, 5]) & (o.peak_ndvi >= 0.5)].merge(m3, on=["power_cell_id", "year"])
    g["planted"] = np.where(g.crop_t == 1, g.corn_planted50_doy, g.soybeans_planted50_doy)
    uy = g.groupby(["unit", "year", "crop_t"])[["greenup_doy", "planted"]].median().reset_index()
    for crop, s in uy.groupby("crop_t"):
        print(f"M3 check, {CROP[crop]}: {len(s)} square-years, r(green-up, modelled planting) = {s.greenup_doy.corr(s.planted):.3f}, "
              f"median lag {np.median(s.greenup_doy - s.planted):.0f} days")
    uy.to_csv(out / "m3_greenup_check.csv", index=False)
    # the same green-up against what NASS reported: district 50% planted dates (10's validation tables)
    dist = pd.read_parquet(D / "reference/iowa_county_district.parquet", columns=["county_fips", "district"])
    gd = g.merge(dist, on="county_fips").groupby(["district", "year", "crop_t"])[["greenup_doy", "planted"]].median().reset_index()
    for crop, name in ((1, "corn"), (5, "soybeans")):
        v = pd.read_csv(D / f"m3/validation_{name}_planted50.csv")[["district", "year", "nass50", "model50"]]
        s = gd[gd.crop_t == crop].merge(v, on=["district", "year"])
        print(f"  {name}, {len(s)} district-years: r(green-up, NASS 50% planted) = {s.greenup_doy.corr(s.nass50):.3f}, "
              f"median lag {np.median(s.greenup_doy - s.nass50):.0f} days; r(M3 model, NASS) on the same = {s.model50.corr(s.nass50):.3f}")
        s.to_csv(out / f"greenup_vs_nass_{name}.csv", index=False)


if __name__ == "__main__":
    main()
