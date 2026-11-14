"""Does soil water add to the county-yield baseline (m11)? Same panel, trend and validation as script 04.

SMAP L4 exists for 2025 only in our data, so the multi-year test uses the MERRA-2 soil wetness in POWER
(06; its root-zone percentile follows SMAP's with r = 0.88 within a cell in 2025) and the FAO-56 ledger (11).
Feature groups, per county and target year t:
- at planting (what a planner can know): root-zone wetness percentile, 1-15 April; precipitation
  October t-1 to March t; ledger plant-available water at the modelled planting date;
- in season (scenario variables, an oracle for a pre-season tool): ledger water gap m7 and stress days,
  corn's gap around silking, root-zone percentile July-August, heat days at silking (10).
Every set is added to the trend + yield lags of script 04, scored by forward chaining and leave-one-year-out
with 04's own functions. A scenario table gives the yield anomaly (yield / county trend) by water-gap quintile,
the conditional range a planner can attach to a dry or wet season.

Usage: python 13_m11_soil.py --dataset path/to/field_dataset --panel county_panel.csv --power power_seasons.csv \
           --context county_context.csv --power-daily power_daily.parquet --water water/ --m3 m3/ \
           --tables path/to/field_daily_2025 --out results_dir
"""
import argparse
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
base = importlib.import_module("04_m11_baseline")

AT_PLANTING = ["gwetroot_pctl_apr", "precip_oct_mar", "paw_plant"]
IN_SEASON = ["m7_gap_mm", "stress_days", "gwetroot_pctl_jul_aug"]
CORN_ONLY = ["m7_critical_mm", "heat32_days_silk"]


def county_daily(power_daily, fields):
    pw = pd.read_parquet(power_daily, columns=["power_cell_id", "date", "gwetroot_pctl", "PRECTOTCORR"])
    w = fields.groupby(["county_fips", "power_cell_id"]).area_acres.sum().rename("w").reset_index()
    m = w.merge(pw, on="power_cell_id")
    for c in ("gwetroot_pctl", "PRECTOTCORR"):
        m[c] = m[c] * m.w
    g = m.groupby(["county_fips", "date"])[["gwetroot_pctl", "PRECTOTCORR", "w"]].sum()
    return g[["gwetroot_pctl", "PRECTOTCORR"]].div(g.w, axis=0).reset_index()


def features(args):
    fields = pd.read_parquet(Path(args.tables) / "fields.parquet", columns=["county_fips", "power_cell_id", "area_acres"])
    cd = county_daily(args.power_daily, fields)
    d = cd.date
    apr = cd[(d.dt.month == 4) & (d.dt.day <= 15)].groupby(["county_fips", d.dt.year]).gwetroot_pctl.mean().rename("gwetroot_pctl_apr")
    jja = cd[d.dt.month.isin([7, 8])].groupby(["county_fips", d.dt.year]).gwetroot_pctl.mean().rename("gwetroot_pctl_jul_aug")
    winter_year = d.dt.year + (d.dt.month >= 10)
    wet = cd[(d.dt.month >= 10) | (d.dt.month <= 3)].groupby(["county_fips", winter_year]).PRECTOTCORR.sum().rename("precip_oct_mar")
    f = pd.concat([apr, jja, wet], axis=1)
    f.index.names = ["county_fips", "year"]
    f = f.reset_index()
    f.loc[f.year == f.year.min(), "precip_oct_mar"] = np.nan                   # first winter is incomplete

    s = pd.read_parquet(Path(args.water) / "county_season.parquet")
    s["paw_plant"] = 1 - s.dr_plant_mm / s.taw_mm
    s["crop"] = s.crop.str.upper()
    cy = pd.read_parquet(Path(args.m3) / "cell_year.parquet", columns=["power_cell_id", "year", "heat32_days_silk"])
    w = fields.groupby(["county_fips", "power_cell_id"]).area_acres.sum().rename("w").reset_index()
    h = w.merge(cy, on="power_cell_id").assign(x=lambda t: t.w * t.heat32_days_silk)
    heat = (h.groupby(["county_fips", "year"]).x.sum() / h.groupby(["county_fips", "year"]).w.sum()).rename("heat32_days_silk").reset_index()
    out = s[["county_fips", "year", "crop", "paw_plant", "m7_gap_mm", "stress_days", "m7_critical_mm"]].merge(f, on=["county_fips", "year"], how="left")
    return out.merge(heat, on=["county_fips", "year"], how="left")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for a in ("dataset", "panel", "power", "context", "power-daily", "water", "m3", "tables", "out"):
        ap.add_argument(f"--{a}", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df = base.build(args).merge(features(args), on=["county_fips", "year", "crop"], how="left")
    print(f"{len(df):,} county-years; soil features present from {df.dropna(subset=AT_PLANTING).year.min()}")

    rows = []
    for crop in ("CORN", "SOYBEANS"):
        c = df[df.crop == crop]
        extra = CORN_ONLY if crop == "CORN" else []
        sets = {"trend only": [], "+ yield lags": base.LAGS,
                "+ soil at planting": base.LAGS + AT_PLANTING,
                "+ soil at planting + April drought (2001+)": base.LAGS + AT_PLANTING + base.DROUGHT,
                "oracle: same-summer weather (04)": base.LAGS + base.SAME,
                "oracle: in-season water": base.LAGS + IN_SEASON + extra,
                "oracle: in-season water + same-summer weather": base.LAGS + IN_SEASON + extra + base.SAME}
        for mode, years in (("forward", range(1995, 2026)), ("loyo", range(1991, 2026)), ("forward 2001+", range(2001, 2026))):
            # every set is scored on the same county-years: those with all inputs of this mode present
            common = AT_PLANTING + IN_SEASON + extra + base.SAME + (base.DROUGHT if "2001+" in mode else [])
            sub = c.dropna(subset=common)
            if "2001+" in mode:
                sub = sub[sub.year >= 2000]
            for name, feats in sets.items():
                if ("2001+" in name) != ("2001+" in mode) and name not in ("trend only", "+ yield lags", "+ soil at planting"):
                    continue
                for model in (("ridge", "hgb") if feats else ("trend",)):
                    p = base.run(sub, feats, years, "loyo" if mode == "loyo" else "forward", model if model != "trend" else "ridge")
                    if p.empty:
                        continue
                    rows.append({"crop": crop, "cv": mode, "features": name, "model": model, **base.score(p)})
                    print(rows[-1])
    res = pd.DataFrame(rows)
    res.to_csv(out / "m11_soil_experiments.csv", index=False)
    pd.set_option("display.width", 220)
    print(res.pivot_table(index=["crop", "features"], columns=["cv", "model"], values="rmse").round(2).to_string())

    # scenario table: yield anomaly against the county's own trend (all years, descriptive) by water-gap quintile
    scen = []
    for crop in ("CORN", "SOYBEANS"):
        c = df[(df.crop == crop) & df.m7_gap_mm.notna()].copy()
        c["trend"] = c.groupby("county_fips").apply(lambda g: pd.Series(np.polyval(np.polyfit(g.year, g.yield_bu_acre, 1), g.year), index=g.index),
                                                    include_groups=False).reset_index(level=0, drop=True)
        c["anomaly"] = c.yield_bu_acre / c.trend
        c["gap_quintile"] = pd.qcut(c.m7_gap_mm, 5, labels=False, duplicates="drop") + 1
        t = c.groupby("gap_quintile").agg(gap_min=("m7_gap_mm", "min"), gap_max=("m7_gap_mm", "max"), n=("anomaly", "size"),
                                          p10=("anomaly", lambda s: s.quantile(0.1)), p50=("anomaly", "median"),
                                          p90=("anomaly", lambda s: s.quantile(0.9)))
        scen.append(t.assign(crop=crop).reset_index())
    scen = pd.concat(scen)
    scen.to_csv(out / "m11_water_gap_scenarios.csv", index=False)
    print(scen.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
