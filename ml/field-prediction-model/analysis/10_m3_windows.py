"""M3 windows per POWER cell, 1981-2026: workable days, sowing, silking, frost and heat, checked against NASS.

Event series per cell and year from POWER daily (06), each part scored on 2016-2025 using only earlier years:
- workable-day probability: logistic in surface soil wetness (GWETTOP), rain on the day and the two days
  before, and frozen or snow-covered soil; fitted on 2001-2015 so that district weekly sums match NASS
  "days suitable for fieldwork"; scored against a district x week-of-year climatology;
- planting progress: from day of year D0, on days whose 5-day mean soil temperature (TSOIL1) is at least
  T, a crop is planted at rate r x workable probability; (D0, T, r) fitted per crop on NASS % planted of
  the 15 years before each test year (planting practice moves: soybeans now go in ~10 days earlier);
  scored by the error of the 50% planted date against those years' mean date;
- silking and maturity: growing degree days (10/30 C) from the 50% planted date; a year's GDD sum is the
  median of NASS 50% planted -> 50% silking / mature over the 5 years before it (hybrids get longer);
  the products use the 2021-2025 median;
- frost: last spring and first autumn day with T2M_MIN <= 0 C and <= -2.2 C, and summer heat days, checked
  against long-record NWS COOP stations (IEM IACLIMATE network);
- heat at silking: days with T2M_MAX >= 35 C (and >= 32 C) within 7 days of the modelled silking date, for
  the modelled planting date and for planting 10 days earlier or 10 / 20 days later.
Districts are NASS crop reporting districts; a district's value is the field-area-weighted mean of its cells.

Usage: python 10_m3_windows.py --tables path/to/field_daily_2025 --power power_daily.parquet \
           --reference reference/ --cache coop_cache --out m3/
"""
import argparse
import io
import json
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
import duckdb
import numpy as np
import pandas as pd
from scipy import optimize, stats

TRAIN, TEST = (2001, 2015), (2016, 2025)
SUMMARY_YEARS = (1991, 2025)
DISTRICTS = ["nw", "nc", "ne", "wc", "c", "ec", "sw", "sc", "se"]
SEASON = (74, 196)                        # 15 March .. 15 July, day of year (non-leap numbering)
CROPS = {"corn": "corn planted", "soybeans": "soybeans planted"}
HEAT_OFFSETS = (-10, 0, 10, 20)
CTX = ssl.create_default_context(cafile=certifi.where())
COOP_LIST = "https://mesonet.agron.iastate.edu/geojson/network/IACLIMATE.geojson"
COOP = ("https://mesonet.agron.iastate.edu/cgi-bin/request/coop.py?network=IACLIMATE&stations={sid}"
        "&year1=1981&month1=1&day1=1&year2=2025&month2=12&day2=31&vars%5B%5D=low&vars%5B%5D=high&what=download&delim=comma&gis=no")


def get(url, path):
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "field-shift-research"})
        path.write_bytes(urllib.request.urlopen(req, timeout=300, context=CTX).read())
    return path.read_bytes()


def sigmoid(z):
    return 1 / (1 + np.exp(-z))


def interp_crossing(x, values, level):
    """Where a cumulative weekly series first reaches `level`, linear between weeks; NaN if not bracketed."""
    above = np.flatnonzero(values >= level)
    if not len(above) or above[0] == 0:
        return np.nan
    i = above[0]
    return x[i - 1] + (x[i] - x[i - 1]) * (level - values[i - 1]) / (values[i] - values[i - 1])


def days_since_epoch(ts):
    return ts.to_numpy().astype("datetime64[D]").astype(float)


class Grid:
    """POWER columns as cell x day matrices, with district weights."""

    def __init__(self, power, fields, districts):
        pw = pd.read_parquet(power).sort_values(["power_cell_id", "date"])
        self.cells = sorted(pw.power_cell_id.unique())
        self.dates = pd.DatetimeIndex(sorted(pw.date.unique()))
        self.pw = pw
        a = fields.merge(districts, on="county_fips").groupby(["district", "power_cell_id"]).area_acres.sum().unstack(fill_value=0)
        a = a.reindex(index=DISTRICTS, columns=self.cells, fill_value=0)
        self.W = (a.T / a.sum(axis=1)).T.to_numpy()                  # district x cell, rows sum to 1
        self.cell_lat = np.array([float(c.split("_")[0]) for c in self.cells])

    def m(self, col):
        return self.pw.pivot(index="power_cell_id", columns="date", values=col).loc[self.cells, self.dates].to_numpy()

    def day(self, ts):
        return self.dates.get_indexer(pd.DatetimeIndex(ts))


def trailing_mean(x, n):
    c = np.cumsum(np.nan_to_num(x), axis=1)
    out = np.full_like(x, np.nan)
    out[:, n - 1:] = (c[:, n - 1:] - np.concatenate([np.zeros((x.shape[0], 1)), c[:, :-n]], axis=1)) / n
    return out


def workable_model(g, nass):
    """Fit the workable-day probability on NASS days suitable; return the cell x day probability."""
    gw, P, ts, snow = g.m("GWETTOP"), np.nan_to_num(g.m("PRECTOTCORR")), g.m("TSOIL1"), np.nan_to_num(g.m("SNODP"))
    lp = np.log1p(P)
    lag = lambda x, k: np.concatenate([np.zeros((x.shape[0], k)), x[:, :-k]], axis=1)
    X = np.stack([gw, lp, lag(lp, 1), lag(lp, 2), ((ts < 0.5) | (snow > 1)).astype(float)])
    X = np.nan_to_num(X)
    obs = nass[(nass.metric == "days suitable") & nass.district.isin(DISTRICTS) & (nass.week_ending.dt.day_of_week == 6)
               & nass.week_ending.dt.month.between(4, 11)].copy()
    obs["end"] = g.day(obs.week_ending)
    obs = obs[obs.end >= 7]
    obs["d"] = obs.district.map({d: i for i, d in enumerate(DISTRICTS)})
    obs["year"] = obs.week_ending.dt.year

    def weekly(beta):
        p = sigmoid(beta[0] + np.tensordot(beta[1:], X, axes=1))
        c = np.cumsum(g.W @ p, axis=1)
        return c[obs.d, obs.end] - c[obs.d, obs.end - 7], p

    tr = obs.year.between(*TRAIN).to_numpy()
    loss = lambda b: np.mean((weekly(b)[0][tr] - obs.value.to_numpy()[tr]) ** 2)
    fit = optimize.minimize(loss, x0=np.array([3, -6, -1, -0.5, -0.2, -3.0]), method="L-BFGS-B")
    pred, p = weekly(fit.x)
    obs["pred"] = pred
    obs["woy"] = obs.week_ending.dt.isocalendar().week.astype(int)
    clim = obs[tr].groupby(["district", "woy"]).value.mean().rename("clim")
    obs = obs.join(clim, on=["district", "woy"])
    te = obs.year.between(*TEST)
    rmse = lambda a, b: float(np.sqrt(np.mean((a - b) ** 2)))
    res = {"coef_const_gwettop_rain0_rain1_rain2_cold": np.round(fit.x, 3).tolist(),
           "train_weeks": int(tr.sum()), "test_weeks": int(te.sum()),
           "test_r": float(obs[te].pred.corr(obs[te].value)), "test_rmse_days": rmse(obs[te].pred, obs[te].value),
           "test_rmse_climatology": rmse(obs[te].clim, obs[te].value),
           "test_bias_days": float((obs[te].pred - obs[te].value).mean())}
    spring = te & obs.week_ending.dt.month.isin([4, 5])
    res["test_r_apr_may"] = float(obs[spring].pred.corr(obs[spring].value))
    res["test_rmse_apr_may"] = rmse(obs[spring].pred, obs[spring].value)
    res["test_rmse_apr_may_climatology"] = rmse(obs[spring].clim, obs[spring].value)
    return p, res, obs


def planting(g, p, ts5, years, params):
    """Cumulative planted fraction per cell and day of the season window, for each year."""
    d0, tmin, rate = params
    out = {}
    for y in years:
        i0 = g.dates.get_loc(pd.Timestamp(y, 1, 1)) + SEASON[0] - 1
        sl = slice(i0, i0 + SEASON[1] - SEASON[0] + 1)
        doy = np.arange(SEASON[0], SEASON[1] + 1)
        allowed = (doy[None, :] >= d0) & (np.nan_to_num(ts5[:, sl], nan=-99) >= tmin)
        out[y] = np.clip(np.cumsum(rate * p[:, sl] * allowed, axis=1), 0, 1)
    return out


def fit_planting(g, p, ts5, nass, metric):
    obs = nass[(nass.metric == metric) & nass.district.isin(DISTRICTS)].copy()
    obs["year"] = obs.week_ending.dt.year
    obs = obs[obs.year.between(TRAIN[0], TEST[1])]
    obs["doy"] = obs.week_ending.dt.day_of_year
    obs = obs[obs.doy.between(SEASON[0], SEASON[1])]
    obs["d"] = obs.district.map({d: i for i, d in enumerate(DISTRICTS)})
    years = sorted(obs.year.unique())
    d50 = []
    for (y, dname), o in obs.groupby(["year", "district"]):
        o = o.sort_values("doy")
        x = interp_crossing(o.doy.to_numpy(float), o.value.to_numpy(float), 50)
        if not np.isnan(x):
            d50.append({"year": y, "district": dname, "nass50": x})
    d50 = pd.DataFrame(d50)

    # every parameter set once: squared errors per NASS week and modelled 50% date per district-year
    grid = [(d0, tmin, round(float(rate), 2)) for d0 in range(91, 136, 3) for tmin in (2, 4, 6, 8, 10, 12)
            for rate in np.arange(0.02, 0.16, 0.02)]
    sq = np.empty((len(grid), len(obs)))
    m50 = np.empty((len(grid), len(d50)))
    for gi, prm in enumerate(grid):
        F = planting(g, p, ts5, years, prm)
        dist = {y: g.W @ F[y] for y in years}
        sq[gi] = (np.array([dist[y][d, k - SEASON[0]] for y, d, k in zip(obs.year, obs.d, obs.doy)]) * 100 - obs.value.to_numpy()) ** 2
        for j, (y, dname) in enumerate(zip(d50.year, d50.district)):
            k = np.flatnonzero(dist[y][DISTRICTS.index(dname)] >= 0.5)
            m50[gi, j] = SEASON[0] + k[0] if len(k) else np.nan

    # rolling origin: each test year uses parameters fitted on the 15 years before it, and is compared with
    # those years' mean NASS date (climatology); practice changes (earlier soybean planting) stay in the fit
    rows = []
    for t in range(TEST[0], TEST[1] + 1):
        win = obs.year.between(t - 15, t - 1).to_numpy()
        gi = int(np.argmin(sq[:, win].mean(axis=1)))
        clim = d50[d50.year.between(t - 15, t - 1)].groupby("district").nass50.mean()
        for j in np.flatnonzero(d50.year.to_numpy() == t):
            rows.append({"year": t, "district": d50.district[j], "nass50": d50.nass50[j], "model50": m50[gi, j],
                         "clim50": clim.get(d50.district[j], np.nan), "params": grid[gi],
                         "rmse_pp_year": float(np.sqrt(sq[gi, obs.year.to_numpy() == t].mean()))})
    te = pd.DataFrame(rows).dropna(subset=["model50", "clim50"])
    final = int(np.argmin(sq[:, obs.year.between(TEST[1] - 14, TEST[1]).to_numpy()].mean(axis=1)))
    res = {"params_d0_tmin_rate_2011_2025": grid[final],
           "rolling_params_by_year": te.groupby("year").params.first().astype(str).to_dict(),
           "test_district_years": len(te), "test_mae50_days": float((te.model50 - te.nass50).abs().mean()),
           "test_bias50_days": float((te.model50 - te.nass50).mean()),
           "test_mae50_climatology_days": float((te.clim50 - te.nass50).abs().mean()),
           "test_bias50_climatology_days": float((te.clim50 - te.nass50).mean()),
           "test_r50_across_years": float(te.groupby("year")[["model50", "nass50"]].mean().corr().iloc[0, 1]),
           "test_rmse_pp": float(te.groupby("year").rmse_pp_year.first().mean())}
    return grid[final], res, te


def gdd_matrix(g):
    tx, tn = np.clip(g.m("T2M_MAX"), 10, 30), np.clip(g.m("T2M_MIN"), 10, 30)
    return (tx + tn) / 2 - 10


def fit_gdd_stage(g, gdd, nass, stage_metric, plant_metric="corn planted"):
    """GDD from NASS 50% planted to NASS 50% of a stage, per district-year; training median, test error in days."""
    D = g.W @ np.nan_to_num(gdd)
    rows = []
    for (y, dname), o in nass[nass.district.isin(DISTRICTS)].groupby([nass.week_ending.dt.year, "district"]):
        if not TRAIN[0] <= y <= TEST[1]:
            continue
        dates = {}
        for metric in (plant_metric, stage_metric):
            s = o[o.metric == metric].sort_values("week_ending")
            x = interp_crossing(days_since_epoch(s.week_ending), s.value.to_numpy(float), 50)
            dates[metric] = pd.NaT if np.isnan(x) else pd.Timestamp(int(round(x)), unit="D")
        if pd.isna(dates[plant_metric]) or pd.isna(dates[stage_metric]) or dates[stage_metric] <= dates[plant_metric]:
            continue
        i0, i1 = g.day([dates[plant_metric], dates[stage_metric]])
        cum = np.cumsum(D[DISTRICTS.index(dname), i0 + 1:i0 + 250])
        rows.append({"year": y, "district": dname, "plant": dates[plant_metric], "stage": dates[stage_metric],
                     "gdd": float(cum[i1 - i0 - 1]), "i0": i0, "cum": cum})
    t = pd.DataFrame(rows)
    t["obs_days"] = [(s - p).days for s, p in zip(t.stage, t.plant)]
    # rolling origin: a year's GDD requirement is the median of the 5 years before it (hybrids change),
    # the baseline is those years' mean interval in days
    t["need"] = [t[t.year.between(y - 5, y - 1)].gdd.median() for y in t.year]
    t["base_days"] = [t[t.year.between(y - 5, y - 1)].obs_days.mean() for y in t.year]
    t["pred_days"] = [int(np.argmax(c >= n)) + 1 if (c >= n).any() else np.nan for c, n in zip(t.cum, t.need)]
    te = t[t.year.between(*TEST)]
    err = te.pred_days - te.obs_days
    need = float(t[t.year.between(TEST[1] - 4, TEST[1])].gdd.median())
    res = {"gdd_c_2021_2025": round(need, 1), "gdd_by_period": t.groupby(t.year // 5 * 5).gdd.median().round(0).to_dict(),
           "test_district_years": len(te), "test_mae_days": float(err.abs().mean()), "test_bias_days": float(err.mean()),
           "test_mae_baseline_interval_days": float((te.base_days - te.obs_days).abs().mean())}
    return need, res, t.drop(columns=["cum", "i0"])


def frost_dates(dates, tmin, thr):
    """Last spring (Jan-Jun) and first autumn (Jul-Dec) day of year with tmin <= thr, per year (NaN if none)."""
    df = pd.DataFrame({"date": dates, "t": tmin})
    df = df[df.t <= thr]
    spring = df[df.date.dt.month <= 6].groupby(df.date.dt.year).date.max().dt.day_of_year
    autumn = df[df.date.dt.month >= 7].groupby(df.date.dt.year).date.min().dt.day_of_year
    return spring, autumn


def coop_check(g, cache):
    feats = json.loads(get(COOP_LIST, cache / "IACLIMATE.geojson"))["features"]
    st = [(f["id"], *f["geometry"]["coordinates"][:2]) for f in feats
          if (f["properties"].get("archive_begin") or "9999") <= "1981-01-01" and not f["properties"].get("archive_end")
          and not f["id"].startswith(("IAC", "IA0000"))]

    def one(s):
        sid, lon, lat = s
        cell = f"{round(lat / 0.5) * 0.5:+.1f}_{round(lon / 0.625) * 0.625:.3f}"
        if cell not in g.cells:
            return None
        text = get(COOP.format(sid=sid), cache / f"{sid}_lh.csv").decode()
        d = pd.read_csv(io.StringIO("\n".join(l for l in text.splitlines() if not l.startswith("#"))))
        d["date"] = pd.to_datetime(d.day)
        d["tmin"] = (pd.to_numeric(d.low, errors="coerce") - 32) * 5 / 9
        d["tmax"] = (pd.to_numeric(d.high, errors="coerce") - 32) * 5 / 9
        ci = g.cells.index(cell)
        pw = pd.DataFrame({"date": g.dates, "tmin": g.tmin[ci], "tmax": g.tmax[ci]})
        rows = []
        # summer maxima: heat days per year (Jun-Aug) at 32 and 35 C
        hj = d[["date", "tmax"]].merge(pw[["date", "tmax"]], on="date", suffixes=("_st", "_pw"))
        hj = hj[hj.date.dt.month.isin([6, 7, 8]) & (hj.date.dt.year <= 2025)].dropna()
        for thr in (32.0, 35.0):
            cnt = hj.assign(st=hj.tmax_st >= thr, pw=hj.tmax_pw >= thr).groupby(hj.date.dt.year)[["pw", "st"]].sum()
            rows += [{"sid": sid, "threshold_c": thr, "event": "heat_days_jun_aug", "year": y, "power": r.pw, "station": r.st}
                     for y, r in cnt.iterrows()]
        rows.append({"sid": sid, "threshold_c": np.nan, "event": "tmax_jun_aug_mean", "year": 0,
                     "power": hj.tmax_pw.mean(), "station": hj.tmax_st.mean()})
        for thr in (0.0, -2.2):
            s_sp, s_au = frost_dates(d.date, d.tmin, thr)
            p_sp, p_au = frost_dates(pw.date, pw.tmin, thr)
            for name, a, b in (("last_spring", p_sp, s_sp), ("first_autumn", p_au, s_au)):
                j = pd.concat([a.rename("power"), b.rename("station")], axis=1).dropna()
                j = j[j.index <= 2025]
                rows += [{"sid": sid, "threshold_c": thr, "event": name, "year": y, "power": r.power, "station": r.station}
                         for y, r in j.iterrows()]
        return pd.DataFrame(rows)
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = pd.concat([r for r in ex.map(one, st) if r is not None], ignore_index=True)
    res["diff"] = res.power - res.station
    summ = res.groupby(["threshold_c", "event"], dropna=False).agg(stations=("sid", "nunique"), station_years=("diff", "size"),
                                                     bias_days=("diff", "mean"), mae_days=("diff", lambda s: s.abs().mean()))
    # year-to-year agreement: per station, correlation of the two date series
    summ["median_station_r"] = res.groupby(["threshold_c", "event", "sid"]).apply(
        lambda x: x.power.corr(x.station), include_groups=False).groupby(level=[0, 1], dropna=False).median()
    return summ, res


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tables", required=True)
    ap.add_argument("--power", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out, cache, ref = Path(args.out), Path(args.cache), Path(args.reference)
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    fields = pd.read_parquet(Path(args.tables) / "fields.parquet", columns=["CSBID", "county_fips", "power_cell_id", "area_acres", "smap_cell_id"])
    districts = pd.read_parquet(ref / "iowa_county_district.parquet")
    nass = pd.read_parquet(ref / "nass_iowa_progress.parquet")
    g = Grid(args.power, fields, districts)
    g.tmin, g.tmax = g.m("T2M_MIN"), g.m("T2M_MAX")
    tmax = g.tmax
    print(f"{len(g.cells)} cells, {g.dates[0].date()}..{g.dates[-1].date()}")

    # 1. workable days
    p, res, wk = workable_model(g, nass)
    print("workable days vs NASS days suitable:", json.dumps(res, indent=1))
    wk.to_csv(out / "validation_days_suitable.csv", index=False)
    summary = {"workable": res}

    # 2025: does SMAP surface wetness track NASS days suitable as well as the model?
    con = duckdb.connect()
    con.register("f", fields.merge(districts, on="county_fips"))
    sm = con.execute(f"""SELECT f.district, s.date, sum(f.area_acres * s.smap_sm_surface_wetness) / sum(f.area_acres) AS w
        FROM f JOIN '{Path(args.tables) / 'smap_cellday.parquet'}' s USING (smap_cell_id) GROUP BY 1, 2""").df()
    sm["date"] = pd.to_datetime(sm.date)
    w25 = wk[wk.year == 2025].copy()
    w25["smap_wetness_week"] = [sm[(sm.district == d) & sm.date.between(e - pd.Timedelta(days=6), e)].w.mean()
                                for d, e in zip(w25.district, w25.week_ending)]
    w25 = w25.dropna(subset=["smap_wetness_week"])
    summary["2025_smap"] = {"weeks": len(w25), "r_model": float(w25.pred.corr(w25.value)),
                            "r_smap_surface_wetness": float(w25.smap_wetness_week.corr(w25.value))}
    print("2025 district-weeks:", summary["2025_smap"])

    # 2. planting
    ts5 = trailing_mean(g.m("TSOIL1"), 5)
    params = {}
    for crop, metric in CROPS.items():
        params[crop], res, d50 = fit_planting(g, p, ts5, nass, metric)
        print(f"{crop} planting:", json.dumps(res, default=str))
        summary[f"{crop}_planting"] = res
        d50.to_csv(out / f"validation_{crop}_planted50.csv", index=False)

    # 3. silking and maturity GDD
    gdd = gdd_matrix(g)
    gdd_need = {}
    for stage in ("corn silking", "corn mature"):
        gdd_need[stage], res, t = fit_gdd_stage(g, gdd, nass, stage)
        print(f"{stage}:", json.dumps(res))
        summary[stage.replace(" ", "_")] = res
        t.to_csv(out / f"validation_{stage.replace(' ', '_')}.csv", index=False)

    # 4. frost against COOP stations
    fsum, fres = coop_check(g, cache)
    print("POWER minus COOP stations (frost: day of year; heat: days per Jun-Aug; tmax: C):"); print(fsum.round(2).to_string())
    fres.to_csv(out / "validation_frost_coop.csv", index=False)
    summary["power_vs_coop"] = fsum.reset_index().to_dict(orient="records")

    # 5. events per cell and year
    years = range(1981, 2027)
    F = {c: planting(g, p, ts5, years, params[c]) for c in CROPS}
    rows = []
    for ci, cell in enumerate(g.cells):
        frost = {thr: frost_dates(pd.Series(g.dates), pd.Series(g.tmin[ci]), thr) for thr in (0.0, -2.2)}
        for y in years:
            i0 = g.dates.get_loc(pd.Timestamp(y, 1, 1))
            r = {"power_cell_id": cell, "year": y}
            warm = np.flatnonzero(np.nan_to_num(ts5[ci, i0 + SEASON[0] - 1:i0 + SEASON[1]], nan=-99) >= 10)
            r["soil10_doy"] = SEASON[0] + warm[0] if len(warm) else np.nan
            for crop in CROPS:
                for lvl in (0.1, 0.5, 0.9):
                    k = np.flatnonzero(F[crop][y][ci] >= lvl)
                    r[f"{crop}_planted{int(lvl * 100)}_doy"] = SEASON[0] + k[0] if len(k) else np.nan
            a, b = g.day([pd.Timestamp(y, 4, 15), pd.Timestamp(y, 5, 31)])
            r["workable_days_apr15_may31"] = float(p[ci, a:b + 1].sum())
            for thr, tag in ((0.0, "0c"), (-2.2, "m2c")):
                sp, au = frost[thr]
                r[f"last_spring_frost_{tag}_doy"] = sp.get(y, np.nan)
                r[f"first_autumn_frost_{tag}_doy"] = au.get(y, np.nan) if y <= 2025 else np.nan
            plant = r["corn_planted50_doy"]
            for off in HEAT_OFFSETS:
                tag = "" if off == 0 else f"_plant{off:+d}d"
                if np.isnan(plant):
                    continue
                s0 = i0 + int(plant) - 1 + off
                cum = np.cumsum(np.nan_to_num(gdd[ci, s0 + 1:s0 + 250]))
                if not (cum >= gdd_need["corn silking"]).any():
                    continue
                silk = s0 + 1 + int(np.argmax(cum >= gdd_need["corn silking"]))
                if silk + 7 >= len(g.dates):
                    continue
                win = tmax[ci, silk - 7:silk + 8]
                r[f"silk_doy{tag}"] = silk - i0 + 1
                r[f"heat35_days_silk{tag}"] = int((win >= 35).sum())
                r[f"heat32_days_silk{tag}"] = int((win >= 32).sum())
                if (cum >= gdd_need["corn mature"]).any():
                    r[f"mature_doy{tag}"] = s0 + 2 + int(np.argmax(cum >= gdd_need["corn mature"])) - i0
            r["killing_frost_after_corn10"] = (float(r["last_spring_frost_m2c_doy"] > r["corn_planted10_doy"])
                                               if not np.isnan(r["corn_planted10_doy"]) else np.nan)
            if "mature_doy" in r and y <= 2025:
                r["frost_before_maturity"] = float(r["first_autumn_frost_m2c_doy"] < r["mature_doy"])
            rows.append(r)
    cy = pd.DataFrame(rows)
    cy.to_parquet(out / "cell_year.parquet", index=False)

    # 6. per-cell summary: quantiles over SUMMARY_YEARS, trend per decade over 1981-2025
    metrics = [c for c in cy.columns if c not in ("power_cell_id", "year")]
    summ = []
    for cell, c in cy[cy.year <= 2025].groupby("power_cell_id"):
        r = {"power_cell_id": cell}
        recent = c[c.year.between(*SUMMARY_YEARS)]
        for m_ in metrics:
            v = recent[m_].dropna()
            if m_.startswith(("heat", "killing", "frost_before")):
                r[f"{m_}_mean"] = v.mean()
                if m_.startswith("heat"):
                    r[f"{m_}_p_any"] = (v > 0).mean()
            else:
                for q in (0.1, 0.5, 0.9):
                    r[f"{m_}_p{int(q * 100)}"] = v.quantile(q)
            full = c[["year", m_]].dropna()
            if len(full) > 20 and full[m_].std() > 0:
                lr = stats.linregress(full.year, full[m_])
                r[f"{m_}_trend_per_decade"], r[f"{m_}_trend_p"] = lr.slope * 10, lr.pvalue
        summ.append(r)
    pd.DataFrame(summ).to_parquet(out / "cell_summary.parquet", index=False)

    # Iowa-wide view of the main windows (median over cells of the per-cell quantiles)
    s = pd.DataFrame(summ)
    show = ["soil10_doy", "corn_planted50_doy", "soybeans_planted50_doy", "last_spring_frost_0c_doy",
            "first_autumn_frost_0c_doy", "silk_doy", "mature_doy", "workable_days_apr15_may31"]
    view = pd.DataFrame({m_: [s[f"{m_}_p10"].median(), s[f"{m_}_p50"].median(), s[f"{m_}_p90"].median(),
                              s[f"{m_}_trend_per_decade"].median(), (s[f"{m_}_trend_p"] < 0.05).mean()] for m_ in show},
                        index=["p10", "p50", "p90", "trend_per_decade", "share_cells_p<0.05"]).T
    print("median over cells, 1991-2025 (day of year unless days):"); print(view.round(2).to_string())
    heat = pd.DataFrame({off: [s[f"heat35_days_silk{'' if off == 0 else f'_plant{off:+d}d'}_p_any"].median(),
                               s[f"heat32_days_silk{'' if off == 0 else f'_plant{off:+d}d'}_mean"].median()] for off in HEAT_OFFSETS},
                        index=["P(>=1 day >=35C at silking)", "mean days >=32C at silking"]).T
    heat.index.name = "planting shift, days"
    print(heat.round(3).to_string())
    risk = {k: float(s[f"{k}_mean"].median()) for k in ("killing_frost_after_corn10", "frost_before_maturity")}
    print("median over cells:", risk)
    summary.update({"windows": view.reset_index().to_dict(orient="records"), "heat_by_shift": heat.reset_index().to_dict(orient="records"),
                    "frost_risk": risk, "params": {k: list(v) for k, v in params.items()}, "gdd_need": gdd_need})
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float))


if __name__ == "__main__":
    main()
