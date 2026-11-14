"""Rain-fed water ledger per county, 1984-2026: m6 crop water demand, m7 water gap, m9 cover-crop water risk.

FAO-56 single-coefficient daily root-zone balance (Allen et al. 1998, eq. 84-86):
    Dr[i] = Dr[i-1] - (P - RO)[i] + Ks Kc ET0[i] + DP[i],   0 <= Dr <= TAW
- ET0 from 06 (POWER solar, so the run starts in 1984); P = POWER PRECTOTCORR; RO = SCS curve number 75;
- TAW = the county's SSURGO available water storage (08) down to the crop's rooting depth, kept fixed all
  year (corn 1.5 m, soybeans 1.2 m: Table 22 upper values, which the paper recommends for rain-fed modelling);
- Ks = (TAW - Dr) / ((1 - p) TAW) when Dr > p TAW; p = 0.55 corn, 0.50 soybeans, adjusted by 0.04 (5 - ETc);
- calendar: planting = M3's modelled 50% planted date (10); corn stages by GDD with M3's NASS-fitted silking
  and maturity sums (initial stage to 200 GDD, mid-season from silking to 60% of silking -> maturity); a corn
  season that has not matured by the first killing frost (<= -2.2 C) after silking or by 31 October ends there;
  soybean stages from Table 11 (Central USA, May: 20 / 35 / 60 / 25 days); harvest = NASS district mean
  50% harvested date, 2001-2025, and never before maturity + 7 days;
- Kc from Table 12: maize 1.20 mid, 0.35 end (grain dried in the field), soybeans 1.15 / 0.50. Kc ini = 0.5:
  the table's base value is for infrequent wetting and footnote 1 raises it for frequent wetting, as in Iowa
  springs. Bare soil with residue between seasons and after maturity: Kc 0.3.
m6 = sum of Kc ET0 from planting to maturity; m7 = m6 minus the actual Ks Kc ET0 (what rain and stored water did
not cover); m7_critical = the same deficit from 14 days before to 21 days after corn silking.
m9 (Fallow-Zero): from harvest to the next crop's planting (corn -> soybeans, soybeans -> corn) in a 1 m root
zone, a bare branch (Kc 0.3) and a cereal rye branch (Kc 0.4, Table 12 winter wheat on frozen soils, until
green-up at a 5-day soil temperature >= 5 C after 15 February, then a linear ramp to 1.0 at termination 14 days
before planting). Outcome: plant-available water at planting, and "dry start" = less than half of TAW.
Checks: ledger soil water against SMAP L4 (2025), POWER GWETROOT and ISU station water content; m7 against
county yield anomalies.

Usage: python 11_water_ledger.py --tables path/to/field_daily_2025 --power power_daily.parquet --reference reference/ \
           --m3 m3/ --insitu insitu/ --panel county_panel.csv --out water/
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

START = "1984-01-01"
CN = 75
CROP = {"corn": {"p": 0.55, "kc": (0.5, 1.20, 0.35), "taw_cm": 150, "harvest": "corn harvested for grain"},
        "soybeans": {"p": 0.50, "kc": (0.5, 1.15, 0.50), "taw_cm": 120, "harvest": "soybeans harvested",
                     "stages": (20, 35, 60, 25)}}
KC_OFF, KC_COVER_WINTER, KC_COVER_TERM = 0.3, 0.4, 1.0
INI_GDD, MID_END_FRACTION = 200, 0.6
TERMINATION_DAYS = 14
NEXT = {"corn": "soybeans", "soybeans": "corn"}


def runoff(p):
    s = 25400 / CN - 254
    ia = 0.2 * s
    return np.where(p > ia, (p - ia) ** 2 / (p - ia + s), 0.0)


def ledger(et0, p, kc, taw, pfrac, dr0):
    """Daily balance over counties (rows) and days (columns). Returns depletion, Ks, ETc, ETa, runoff, drainage."""
    n, T = et0.shape
    dr = np.empty((n, T)); ks = np.empty((n, T)); eta = np.empty((n, T)); dp = np.empty((n, T))
    ro = runoff(p)
    etc = kc * et0
    d = dr0.copy()
    for t in range(T):
        pa = np.clip(pfrac + 0.04 * (5 - etc[:, t]), 0.1, 0.8)
        raw = pa * taw
        k = np.where(d > raw, np.clip((taw - d) / ((1 - pa) * taw), 0, 1), 1.0)
        a = k * etc[:, t]
        d = d - (p[:, t] - ro[:, t]) + a
        dp[:, t] = np.maximum(-d, 0)
        d = np.clip(d, 0, taw)
        dr[:, t], ks[:, t], eta[:, t] = d, k, a
    return dr, ks, etc, eta, ro, dp


def interp50(weeks, values):
    above = np.flatnonzero(values >= 50)
    if not len(above) or above[0] == 0:
        return np.nan
    i = above[0]
    return weeks[i - 1] + (weeks[i] - weeks[i - 1]) * (50 - values[i - 1]) / (values[i] - values[i - 1])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for a in ("tables", "power", "reference", "m3", "insitu", "panel", "out"):
        ap.add_argument(f"--{a}", required=True)
    args = ap.parse_args()
    out, ref, m3 = Path(args.out), Path(args.reference), Path(args.m3)
    out.mkdir(parents=True, exist_ok=True)

    fields = pd.read_parquet(Path(args.tables) / "fields.parquet", columns=["county_fips", "power_cell_id", "smap_cell_id", "area_acres"])
    soils = pd.read_parquet(ref / "county_soils.parquet").set_index("county_fips")
    districts = pd.read_parquet(ref / "iowa_county_district.parquet").set_index("county_fips")
    counties = sorted(fields.county_fips.unique())
    pw = pd.read_parquet(args.power, columns=["power_cell_id", "date", "et0_mm", "PRECTOTCORR", "T2M_MAX", "T2M_MIN", "TSOIL1", "GWETROOT"])
    pw = pw[pw.date >= START]
    cells = sorted(pw.power_cell_id.unique())
    dates = pd.DatetimeIndex(sorted(pw.date.unique()))
    a = fields.groupby(["county_fips", "power_cell_id"]).area_acres.sum().unstack(fill_value=0).reindex(index=counties, columns=cells, fill_value=0)
    W = (a.T / a.sum(axis=1)).T.to_numpy()
    grid = {c: pw.pivot(index="power_cell_id", columns="date", values=c).loc[cells, dates]
            for c in ("et0_mm", "PRECTOTCORR", "T2M_MAX", "T2M_MIN", "TSOIL1", "GWETROOT")}
    # POWER solar misses a few single days (1984-1996, 2026-09-07): interpolate ET0 across them
    print(f"ET0 interpolated on {int(grid['et0_mm'].isna().to_numpy().sum())} cell-days")
    grid["et0_mm"] = grid["et0_mm"].interpolate(axis=1, limit_direction="both")
    cty = {c: W @ v.to_numpy() for c, v in grid.items()}
    assert not np.isnan(cty["et0_mm"]).any()
    gdd = (np.clip(cty["T2M_MAX"], 10, 30) + np.clip(cty["T2M_MIN"], 10, 30)) / 2 - 10
    ts5 = pd.DataFrame(cty["TSOIL1"].T).rolling(5, min_periods=4).mean().to_numpy().T
    years = range(dates[0].year, dates[-1].year + 1)
    print(f"{len(counties)} counties, {len(dates):,} days {dates[0].date()}..{dates[-1].date()}")

    # calendar inputs: M3 planting per county-year, GDD sums, NASS district harvest dates
    cy = pd.read_parquet(m3 / "cell_year.parquet")
    need = json.loads((m3 / "summary.json").read_text())["gdd_need"]
    plant = {}
    for crop in CROP:
        pv = cy.pivot(index="power_cell_id", columns="year", values=f"{crop}_planted50_doy").reindex(cells)
        plant[crop] = pd.DataFrame(np.rint(W @ pv.to_numpy()), index=counties, columns=pv.columns)
    nass = pd.read_parquet(ref / "nass_iowa_progress.parquet")
    harvest = {}
    for crop, spec in CROP.items():
        h = nass[(nass.metric == spec["harvest"]) & nass.week_ending.dt.year.between(2001, 2025)]
        d50 = h.groupby(["district", h.week_ending.dt.year]).apply(
            lambda g: interp50(g.sort_values("week_ending").week_ending.dt.day_of_year.to_numpy(float),
                               g.sort_values("week_ending").value.to_numpy(float)), include_groups=False)
        harvest[crop] = d50.groupby(level=0).mean()
        print(f"{crop} NASS 50% harvested, district mean day of year:", harvest[crop].round(0).to_dict())

    # Kc per county and day for each crop, with season dates
    seasons = []
    kc = {}
    for crop, spec in CROP.items():
        k = np.full((len(counties), len(dates)), KC_OFF)
        ini, mid, end = spec["kc"]
        for ci, c in enumerate(counties):
            for y in years:
                doy = plant[crop].loc[c].get(y, np.nan)
                if np.isnan(doy):
                    continue
                i0 = dates.get_loc(pd.Timestamp(y, 1, 1)) + int(doy) - 1
                if crop == "corn":
                    # the season ends at maturity, or earlier at the first killing frost after silking or 31 October
                    if pd.Timestamp(y, 10, 31) > dates[-1]:                  # 2026: season not over in the data
                        continue
                    last = dates.get_loc(pd.Timestamp(y, 10, 31))
                    cum = np.cumsum(gdd[ci, i0:last + 1])
                    g_silk, g_mat = need["corn silking"], need["corn mature"]
                    g_mid_end = g_silk + MID_END_FRACTION * (g_mat - g_silk)
                    if cum[-1] < g_silk:
                        continue
                    silk = i0 + int(np.argmax(cum >= g_silk))
                    frost = np.flatnonzero(cty["T2M_MIN"][ci, silk:last + 1] <= -2.2)
                    stop = min(int(np.argmax(cum >= g_mat)) if cum[-1] >= g_mat else last - i0,
                               silk - i0 + frost[0] if len(frost) else last - i0)
                    curve = np.interp(cum, [0, INI_GDD, g_silk, g_mid_end, g_mat], [ini, ini, mid, mid, end])
                    n_season = stop + 1
                else:
                    L = spec["stages"]
                    n_season = sum(L)
                    curve = np.interp(np.arange(n_season), np.cumsum([0, L[0], L[1], L[2], L[3]]) - [0, 0, 0, 0, 1],
                                      [ini, ini, mid, mid, end])
                    silk = np.nan
                    if i0 + n_season >= len(dates):
                        continue
                k[ci, i0:i0 + n_season] = curve[:n_season]
                hv = max(harvest[crop][districts.loc[c, "district"]], doy + n_season + 7)
                seasons.append({"county_fips": c, "year": y, "crop": crop, "i_plant": i0, "i_mature": i0 + n_season - 1,
                                "i_silk": silk, "i_harvest": dates.get_loc(pd.Timestamp(y, 1, 1)) + int(hv) - 1})
        kc[crop] = k
    seasons = pd.DataFrame(seasons)

    # continuous ledger per crop (the same crop every year; winters reset most of the difference)
    taw = {crop: soils.loc[counties, "aws_0_100cm_mm"].to_numpy() + (spec["taw_cm"] - 100) / 50 *
           (soils.loc[counties, "aws_0_150cm_mm"].to_numpy() - soils.loc[counties, "aws_0_100cm_mm"].to_numpy())
           for crop, spec in CROP.items()}
    P = np.nan_to_num(cty["PRECTOTCORR"])
    runs, daily = {}, []
    for crop, spec in CROP.items():
        runs[crop] = ledger(cty["et0_mm"], P, kc[crop], taw[crop], spec["p"], np.zeros(len(counties)))
        dr, ks, etc, eta, ro, dp = runs[crop]
        daily.append(pd.DataFrame({"county_fips": np.repeat(counties, len(dates)), "date": np.tile(dates, len(counties)),
                                   "crop": crop, "kc": kc[crop].ravel(), "ks": ks.ravel(), "dr_mm": dr.ravel(),
                                   "rel_soil_water": (1 - dr / taw[crop][:, None]).ravel(), "et0_mm": cty["et0_mm"].ravel(),
                                   "etc_mm": etc.ravel(), "eta_mm": eta.ravel(), "rain_mm": P.ravel(), "runoff_mm": ro.ravel(),
                                   "drainage_mm": dp.ravel()}))
    daily = pd.concat(daily, ignore_index=True)
    daily.to_parquet(out / "ledger_daily.parquet", compression="zstd", index=False)

    rows = []
    for s in seasons.itertuples():
        dr, ks, etc, eta, ro, dp = runs[s.crop]
        ci = counties.index(s.county_fips)
        sl = slice(s.i_plant, s.i_mature + 1)
        r = {"county_fips": s.county_fips, "year": s.year, "crop": s.crop, "plant_date": dates[s.i_plant],
             "mature_date": dates[s.i_mature], "harvest_date": dates[min(s.i_harvest, len(dates) - 1)],
             "taw_mm": taw[s.crop][ci], "dr_plant_mm": dr[ci, s.i_plant - 1],
             "m6_etc_mm": etc[ci, sl].sum(), "eta_mm": eta[ci, sl].sum(), "rain_mm": P[ci, sl].sum(),
             "runoff_mm": ro[ci, sl].sum(), "drainage_mm": dp[ci, sl].sum(), "stress_days": int((ks[ci, sl] < 1).sum())}
        r["m7_gap_mm"] = r["m6_etc_mm"] - r["eta_mm"]
        if s.crop == "corn" and not np.isnan(s.i_silk):
            cs = slice(int(s.i_silk) - 14, int(s.i_silk) + 22)
            r["silk_date"] = dates[int(s.i_silk)]
            r["m7_critical_mm"] = etc[ci, cs].sum() - eta[ci, cs].sum()
        rows.append(r)
    season = pd.DataFrame(rows)
    season.to_parquet(out / "county_season.parquet", index=False)
    done = season[season.year <= 2025]
    q = done[done.year >= 1991].groupby("crop")[["m6_etc_mm", "eta_mm", "m7_gap_mm", "m7_critical_mm", "rain_mm", "stress_days"]].quantile([0.1, 0.5, 0.9])
    print("county-seasons 1991-2025, P10/P50/P90:"); print(q.round(1).to_string())
    by_year = done.groupby(["year", "crop"]).m7_gap_mm.mean().unstack()
    print("worst Iowa-mean water gap years:", {c: by_year[c].nlargest(6).round(0).to_dict() for c in CROP})

    # m9: harvest -> next planting, bare vs cereal rye, in a 1 m root zone
    taw1 = soils.loc[counties, "aws_0_100cm_mm"].to_numpy()
    m9 = []
    for crop, nxt in NEXT.items():
        prev = seasons[seasons.crop == crop].set_index(["county_fips", "year"])
        nseason = seasons[seasons.crop == nxt].set_index(["county_fips", "year"])
        for (c, y), s in prev.iterrows():
            if (c, y + 1) not in nseason.index:
                continue
            ci = counties.index(c)
            i_h, i_p = int(s.i_harvest), int(nseason.loc[(c, y + 1)].i_plant)
            span = slice(i_h + 1, i_p)
            n = i_p - i_h - 1
            dr0 = runs[crop][0][ci, i_h] / taw[crop][ci] * taw1[ci]
            k_cover = np.full(n, KC_COVER_WINTER)
            green = [j for j in range(n) if dates[i_h + 1 + j] >= pd.Timestamp(y + 1, 2, 15) and ts5[ci, i_h + 1 + j] >= 5]
            term = n - TERMINATION_DAYS
            if green and green[0] < term:
                k_cover[green[0]:term] = np.linspace(KC_COVER_WINTER, KC_COVER_TERM, term - green[0])
            k_cover[term:] = KC_OFF
            for branch, k in (("bare", np.full(n, KC_OFF)), ("cover", k_cover)):
                dr = ledger(cty["et0_mm"][ci:ci + 1, span], P[ci:ci + 1, span], k[None, :], taw1[ci:ci + 1], 0.5, np.array([dr0]))[0]
                m9.append({"county_fips": c, "harvest_year": y, "prev_crop": crop, "next_crop": nxt, "branch": branch,
                           "days": n, "dr_harvest_mm": dr0, "dr_plant_mm": dr[0, -1], "taw_mm": taw1[ci],
                           "fall_rain_mm": P[ci, i_h + 1:dates.get_loc(pd.Timestamp(y, 12, 1))].sum(),
                           "rain_mm": P[ci, span].sum()})
    m9 = pd.DataFrame(m9)
    m9["paw_plant_frac"] = 1 - m9.dr_plant_mm / m9.taw_mm
    m9["dry_start"] = (m9.paw_plant_frac < 0.5).astype(int)
    m9.to_parquet(out / "m9_county_year.parquet", index=False)
    piv = m9.pivot_table(index=["county_fips", "harvest_year", "prev_crop"], columns="branch", values=["paw_plant_frac", "dry_start"])
    risk = m9.groupby(["prev_crop", "branch"]).agg(p_dry_start=("dry_start", "mean"), paw_plant_median=("paw_plant_frac", "median"))
    print("m9 over county-years:"); print(risk.round(3).to_string())
    extra = (piv["paw_plant_frac"]["bare"] - piv["paw_plant_frac"]["cover"]).groupby(level=1).mean()
    print("mean extra spring depletion from the cover (share of TAW), worst years:", extra.nlargest(6).round(3).to_dict())
    added = piv["dry_start"]["cover"] - piv["dry_start"]["bare"]
    print("county-years where only the cover branch starts dry:", int((added > 0).sum()), "of", len(added))

    # checks 1: SMAP L4 2025 root-zone wetness, county area-weighted
    sm = pd.read_parquet(Path(args.tables) / "smap_cellday.parquet", columns=["smap_cell_id", "date", "smap_sm_rootzone_wetness", "smap_sm_profile_wetness"])
    sw = fields.groupby(["county_fips", "smap_cell_id"]).area_acres.sum().rename("a").reset_index().merge(sm, on="smap_cell_id")
    sw = sw.assign(w1=sw.a * sw.smap_sm_rootzone_wetness, w2=sw.a * sw.smap_sm_profile_wetness).groupby(["county_fips", "date"])[["w1", "w2", "a"]].sum()
    sw = (sw[["w1", "w2"]].div(sw.a, axis=0)).rename(columns={"w1": "smap_rootzone", "w2": "smap_profile"}).reset_index()
    sw["date"] = pd.to_datetime(sw.date)
    gw = pd.DataFrame({"county_fips": np.repeat(counties, len(dates)), "date": np.tile(dates, len(counties)), "gwetroot": cty["GWETROOT"].ravel()})
    checks = {}
    for crop in CROP:
        d = daily[daily.crop == crop][["county_fips", "date", "rel_soil_water"]]
        m = d.merge(sw, on=["county_fips", "date"])
        within = m.groupby("county_fips")[["rel_soil_water", "smap_rootzone"]].corr().xs("rel_soil_water", level=1).smap_rootzone
        spatial = {str(dd.date()): m[m.date == dd].rel_soil_water.corr(m[m.date == dd].smap_rootzone)
                   for dd in pd.to_datetime(["2025-04-15", "2025-07-31", "2025-10-31"])}
        g = d.merge(gw, on=["county_fips", "date"])
        g_within = g.groupby("county_fips")[["rel_soil_water", "gwetroot"]].corr().xs("rel_soil_water", level=1).gwetroot
        checks[crop] = {"smap_2025_median_county_r": within.median(), "smap_2025_spatial_r": spatial,
                        "gwetroot_1984_2025_median_county_r": g_within.median()}
    # checks 2: ISU stations, 30-60 cm water content, station county
    st = pd.read_parquet(Path(args.insitu) / "isusm_stations.parquet")
    names = {n.lower().replace(" ", ""): f for f, n in districts.county_name.items()} | {"obrien": "19141"}
    st["county_fips"] = st.county.str.lower().str.replace(" ", "").map(names)
    assert st.county_fips.notna().all()
    obs = pd.read_parquet(Path(args.insitu) / "isusm_daily.parquet").merge(st[["sid", "county_fips"]], on="sid")
    obs["vwc"] = obs[["vwc30", "vwc60"]].mean(axis=1, skipna=False)
    for crop in CROP:
        m = obs.merge(daily[daily.crop == crop][["county_fips", "date", "rel_soil_water"]], on=["county_fips", "date"]).dropna(subset=["vwc"])
        r = m.groupby("sid").filter(lambda g: len(g) > 200).groupby("sid")[["vwc", "rel_soil_water"]].corr().xs("vwc", level=1).rel_soil_water
        checks[crop]["isusm_median_station_r"] = r.median()
        checks[crop]["isusm_stations"] = int(r.notna().sum())
    print("ledger checks:", json.dumps(checks, indent=1, default=float))

    # checks 3: water gap against county yield anomalies (yield / own linear trend)
    panel = pd.read_csv(args.panel, dtype={"county_fips": str})
    panel["crop"] = panel.crop.str.lower()
    res = {}
    for crop in CROP:
        y = panel[panel.crop == crop][["county_fips", "year", "yield_bu_acre"]].dropna()
        y["trend"] = y.groupby("county_fips").apply(lambda g: pd.Series(np.polyval(np.polyfit(g.year, g.yield_bu_acre, 1), g.year), index=g.index),
                                                    include_groups=False).reset_index(level=0, drop=True)
        y["anomaly"] = y.yield_bu_acre / y.trend
        j = y.merge(done[done.crop == crop], on=["county_fips", "year"])
        cols = ["m7_gap_mm", "stress_days"] + (["m7_critical_mm"] if crop == "corn" else [])
        yr = j.groupby("year")[["anomaly"] + cols].mean()
        res[crop] = {"county_years": len(j), "years": f"{j.year.min()}-{j.year.max()}",
                     **{f"r_{c}_pooled": j.anomaly.corr(j[c]) for c in cols},
                     **{f"r_{c}_iowa_by_year": yr.anomaly.corr(yr[c]) for c in cols},
                     **{f"r_{c}_within_year": j.groupby("year").apply(lambda g: g.anomaly.corr(g[c]), include_groups=False).median() for c in cols}}
    print("water gap vs yield anomaly:", json.dumps(res, indent=1, default=float))
    (out / "summary.json").write_text(json.dumps({"checks": checks, "yield": res, "m9": risk.reset_index().to_dict(orient="records"),
                                                  "quantiles": q.reset_index().to_dict(orient="records")}, indent=1, default=str))


if __name__ == "__main__":
    main()
