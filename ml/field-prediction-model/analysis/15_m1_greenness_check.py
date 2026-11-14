"""The M1 greenness archives (dataset.zip, dataset (2).zip): what they hold, the rotation check, a crop-type benchmark.

Both archives are the M1 crop-type training set: 8,000 CSB fields of 47 states, 2025, four classes (corn,
soybeans, alfalfa, grassland/pasture), a 16-step season tensor of NDVI, EVI and NDWI per field (X.npy, also
flat in tabular.parquet), labels and splits. The second archive keeps the fields and labels but changes the
index values and redraws the splits. This script
- profiles both versions (coverage, observed steps, crop curves, step-to-step noise, differences);
- checks the rotation guess used elsewhere (2025 crop = the other of corn/soybeans in 2024) on the Iowa
  fields, whose CDL 2025 is in the archive and whose CDL 2018-2024 is in 07's table;
- runs a reference crop classifier (gradient boosting on the 48 index features, the archive's own splits):
  per-class accuracy, the accuracy when only the first k steps are known (k = 4..16), and Iowa held out
  entirely (trained on the other states). A yardstick for the CV model, not the CV model.

Usage: python 15_m1_greenness_check.py --data path/to/Field-Shift-NASA-data --out m1/
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

INDICES = ("ndvi", "evi", "ndwi")
VERSIONS = {"v1": "src/greenness_2025_v1/dataset", "v2": "src/greenness_2025_v2/dataset"}
RNG = 0


def cols(steps):
    return [f"{i}_d{k}" for i in INDICES for k in steps]


def fit_score(train, test, features):
    clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.06, random_state=RNG)
    clf.fit(train[features], train.crop_name)
    p = clf.predict(test[features])
    return accuracy_score(test.crop_name, p), f1_score(test.crop_name, p, average="macro"), p


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    D, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 220)
    t = {v: pd.read_parquet(D / p / "tabular.parquet") for v, p in VERSIONS.items()}
    for v, p in VERSIONS.items():
        X = np.load(D / p / "X.npy")
        assert np.allclose(X, np.stack([t[v][[f"{i}_d{k}" for k in range(1, 17)]].to_numpy() for i in INDICES], axis=1)), v
        assert not set(t[v][t[v].split == "train"].CSBID) & set(t[v][t[v].split != "train"].CSBID), v

    # 1. profile
    rows = []
    for v, d in t.items():
        nd = d[[f"ndvi_d{k}" for k in range(1, 17)]].to_numpy()
        rows.append({"version": v, "fields": len(d), "states": d.CSBID.str[:2].nunique(), "iowa": int((d.CSBID.str[:2] == "19").sum()),
                     "split": d.split.value_counts().to_dict(), "observed_steps_median": d.n_observed_steps.median(),
                     "ndvi_noise_mean_abs_2nd_diff": float(np.abs(np.diff(nd, 2, axis=1)).mean())})
    print(pd.DataFrame(rows).to_string(index=False))
    m = t["v1"].merge(t["v2"], on="CSBID", suffixes=("_1", "_2"))
    print(f"shared fields {len(m):,}; same label {np.mean(m.cdl_code_1 == m.cdl_code_2):.3f}; same split {np.mean(m.split_1 == m.split_2):.3f}")
    curves = pd.concat({v: d.groupby("crop_name")[[f"ndvi_d{k}" for k in range(1, 17)]].median() for v, d in t.items()})
    curves.columns = range(1, 17)
    print("median NDVI by step (1 = early April, 16 = late October if the steps are equal):")
    print(curves.round(2).to_string())
    curves.to_csv(out / "median_ndvi_by_step.csv")
    for v, d in t.items():
        nd = d[[f"ndvi_d{k}" for k in range(1, 17)]].to_numpy()
        peak = pd.Series(nd.argmax(axis=1) + 1, index=d.index).groupby(d.crop_name).median()
        half = pd.Series([int(np.argmax(r >= r.min() + 0.5 * (r.max() - r.min()))) + 1 for r in nd], index=d.index).groupby(d.crop_name).median()
        print(f"{v}: median peak step {peak.to_dict()}; median half-green-up step {half.to_dict()}")

    # 2. rotation guess on Iowa fields
    hist = pd.read_parquet(D / "m2/field_season_drought.parquet", columns=["CSBID", "season", "crop_t1"])
    prev = hist[hist.season == 2025].rename(columns={"crop_t1": "cdl_2024"})[["CSBID", "cdl_2024"]]
    ia = t["v1"][t["v1"].CSBID.str[:2] == "19"].merge(prev, on="CSBID", how="left")
    tab = pd.crosstab(ia.cdl_2024.fillna(-1).astype(int), ia.cdl_code, margins=True)
    print("Iowa archive fields: CDL 2024 (rows) x CDL 2025 (columns)"); print(tab.to_string())
    for a, b in ((1, 5), (5, 1)):
        s = ia[ia.cdl_2024 == a]
        print(f"  CDL 2024 = {a}: next year {b} in {np.mean(s.cdl_code == b):.1%} of {len(s)} fields (class-balanced sample)")

    # 3. reference classifier
    feats, res, early = cols(range(1, 17)), [], []
    for v, d in t.items():
        tr, te = d[d.split == "train"], d[d.split == "test"]
        acc, f1, p = fit_score(tr, te, feats)
        cm = pd.DataFrame(confusion_matrix(te.crop_name, p, labels=sorted(d.crop_name.unique())),
                          index=sorted(d.crop_name.unique()), columns=sorted(d.crop_name.unique()))
        per_class = (cm.values.diagonal() / cm.sum(axis=1)).round(3)
        res.append({"version": v, "test": len(te), "accuracy": acc, "macro_f1": f1, **dict(zip(cm.index, per_class))})
        cm.to_csv(out / f"confusion_{v}.csv")
        cs = d[d.crop_name.isin(["Corn", "Soybeans"])]
        for k in range(4, 17):
            a, _, _ = fit_score(d[d.split == "train"], te, cols(range(1, k + 1)))
            a2, _, _ = fit_score(cs[cs.split == "train"], cs[cs.split == "test"], cols(range(1, k + 1)))
            early.append({"version": v, "steps_known": k, "accuracy_4_classes": a, "accuracy_corn_vs_soy": a2})
        out_ia = d[d.CSBID.str[:2] != "19"]
        a, f1, _ = fit_score(out_ia, d[d.CSBID.str[:2] == "19"], feats)
        res[-1].update({"iowa_held_out_accuracy": a, "iowa_held_out_macro_f1": f1})
    res, early = pd.DataFrame(res), pd.DataFrame(early)
    print(res.round(3).to_string(index=False))
    print(early.pivot(index="steps_known", columns="version").round(3).to_string())
    res.to_csv(out / "benchmark.csv", index=False)
    early.to_csv(out / "early_season.csv", index=False)


if __name__ == "__main__":
    main()
