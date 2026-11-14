"""Ground check of SMAP L4 and POWER soil columns against the ISU Soil Moisture Network (29 Iowa stations).

The network (Iowa Environmental Mesonet, Iowa State University) measures daily soil temperature at
4 in (10 cm) and volumetric water content at 12, 24 and 50 in (30, 60, 127 cm) since 2013-2023.
A station is a point and a SMAP cell is 9 km, so the scores that matter are temporal: correlation and
unbiased RMSE (ubRMSE, the SMAP L4 validation metric) per station, then the median over stations.
Compared, on the days both exist:
- 4 in soil temperature vs SMAP soil_temp_layer1 (2025) and POWER TSOIL1 (2013-2025);
- the spring date when the 5-day mean soil temperature first reaches 10 C, per station-year;
- 12/24 in water content vs SMAP sm_rootzone (2025) and POWER GWETROOT (2013-2025).

Usage: python 09_insitu_soil.py --tables path/to/field_daily_2025 --power power_daily.parquet \
           --cache isusm_cache --out insitu/
"""
import argparse
import io
import json
import ssl
import urllib.request
from pathlib import Path

import certifi
import numpy as np
import pandas as pd
from pyproj import Transformer

CTX = ssl.create_default_context(cafile=certifi.where())
STATIONS = "https://mesonet.agron.iastate.edu/geojson/network/ISUSM.geojson"
DAILY = ("https://mesonet.agron.iastate.edu/cgi-bin/request/isusm.py?station={sid}&mode=daily"
         "&sts={start}T00:00Z&ets=2026-01-01T00:00Z&format=comma")
X0, Y0, RES = -17367530.44516138, 7314540.83081304, 9008.055210146     # EASE-Grid 2.0 M09 (EPSG:6933)
WARM_C = 10.0


def get(url, path):
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "field-shift-research"})
        path.write_bytes(urllib.request.urlopen(req, timeout=300, context=CTX).read())
    return path.read_bytes()


def stations(cache):
    feats = json.loads(get(STATIONS, cache / "ISUSM.geojson"))["features"]
    st = pd.DataFrame([{"sid": f["id"], "name": f["properties"]["sname"], "county": f["properties"]["county"],
                        "begin": f["properties"]["archive_begin"], "lon": f["geometry"]["coordinates"][0],
                        "lat": f["geometry"]["coordinates"][1]} for f in feats])
    x, y = Transformer.from_crs(4326, 6933, always_xy=True).transform(st.lon.values, st.lat.values)
    st["smap_cell_id"] = [f"r{int((Y0 - b) // RES):04d}c{int((a - X0) // RES):04d}" for a, b in zip(x, y)]
    st["power_cell_id"] = [f"{round(la / 0.5) * 0.5:+.1f}_{round(lo / 0.625) * 0.625:.3f}" for lo, la in zip(st.lon, st.lat)]
    return st


def daily(st, cache):
    frames = []
    for s in st.itertuples():
        text = get(DAILY.format(sid=s.sid, start=s.begin[:10]), cache / f"{s.sid}.csv").decode()
        d = pd.read_csv(io.StringIO(text), na_values=[-99, "-99", "M", "None"])
        if d.empty:
            continue
        frames.append(pd.DataFrame({
            "sid": s.sid, "date": pd.to_datetime(d.valid),
            "soil_t10_c": (d.soil04t - 32) * 5 / 9,
            "vwc30": d.soil12vwc / 100, "vwc60": d.soil24vwc / 100, "vwc127": d.soil50vwc / 100,   # % -> m3/m3
            "tmax_c": (d.high - 32) * 5 / 9, "tmin_c": (d.low - 32) * 5 / 9, "precip_mm": d.precip * 25.4}))
    df = pd.concat(frames, ignore_index=True)
    # sensor glitches: drop impossible values rather than interpolate
    df.loc[~df.soil_t10_c.between(-30, 50), "soil_t10_c"] = np.nan
    for c in ("vwc30", "vwc60", "vwc127"):
        df.loc[~df[c].between(0.01, 0.6), c] = np.nan
    return df


def scores(m, a, b):
    """Per-station temporal scores of a against b, then the median over stations."""
    rows = []
    for sid, g in m.dropna(subset=[a, b]).groupby("sid"):
        if len(g) < 60:
            continue
        d = g[a] - g[b]
        rows.append({"sid": sid, "n": len(g), "r": g[a].corr(g[b]), "bias": d.mean(), "ubrmse": d.std()})
    s = pd.DataFrame(rows)
    if s.empty:
        return {"stations": 0}
    return {"stations": len(s), "days": int(s.n.sum()), "median_r": s.r.median(), "r_p10": s.r.quantile(0.1),
            "median_bias": s.bias.median(), "median_ubrmse": s.ubrmse.median()}


def warm_dates(df, col, start="03-15"):
    """First day from `start` whose trailing 5-day mean reaches WARM_C, per site and year."""
    df = df.sort_values("date").copy()
    df["t5"] = df.groupby("sid")[col].transform(lambda s: s.rolling(5, min_periods=4).mean())
    md = df.date.dt.strftime("%m-%d")
    spring = df[(md >= start) & (df.date.dt.month <= 6)]
    first = spring[spring.t5 >= WARM_C].groupby(["sid", spring.date.dt.year]).date.min()
    # keep a season only if its record starts below the threshold, so the crossing itself was observed
    start = spring.dropna(subset=["t5"]).groupby(["sid", spring.date.dt.year]).t5.first()
    return first[first.index.isin(start[start < WARM_C].index)].dt.day_of_year.rename(col)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tables", required=True)
    ap.add_argument("--power", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cache, out = Path(args.cache), Path(args.out)
    cache.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    st = stations(cache)
    df = daily(st, cache)
    smap = pd.read_parquet(Path(args.tables) / "smap_cellday.parquet",
                           columns=["smap_cell_id", "date", "smap_soil_temp_layer1_c", "smap_sm_rootzone", "smap_sm_surface"])
    smap["date"] = pd.to_datetime(smap.date)
    in_grid = st.smap_cell_id.isin(smap.smap_cell_id.unique())
    power = pd.read_parquet(args.power, columns=["power_cell_id", "date", "TSOIL1", "GWETROOT", "GWETTOP"])
    in_power = st.power_cell_id.isin(power.power_cell_id.unique())
    print(f"{len(st)} stations, {df.sid.nunique()} with data, {len(df):,} station-days "
          f"{df.date.min().date()}..{df.date.max().date()}; inside the panel's SMAP grid: {int(in_grid.sum())}, "
          f"inside its POWER cells: {int(in_power.sum())}")
    st.to_parquet(out / "isusm_stations.parquet", index=False)
    df.to_parquet(out / "isusm_daily.parquet", compression="zstd", index=False)

    m = df.merge(st[["sid", "smap_cell_id", "power_cell_id"]], on="sid")
    m = m.merge(smap, on=["smap_cell_id", "date"], how="left").merge(power, on=["power_cell_id", "date"], how="left")
    m["vwc_30_60"] = m[["vwc30", "vwc60"]].mean(axis=1, skipna=False)
    rows = {
        "soil T 10 cm vs SMAP layer 1, 2025": scores(m, "smap_soil_temp_layer1_c", "soil_t10_c"),
        "soil T 10 cm vs POWER TSOIL1, 2025": scores(m[m.date.dt.year == 2025], "TSOIL1", "soil_t10_c"),
        "soil T 10 cm vs POWER TSOIL1, all years": scores(m, "TSOIL1", "soil_t10_c"),
        "VWC 30-60 cm vs SMAP root zone, 2025": scores(m, "smap_sm_rootzone", "vwc_30_60"),
        "VWC 30-60 cm vs POWER GWETROOT, 2025": scores(m[m.date.dt.year == 2025], "GWETROOT", "vwc_30_60"),
        "VWC 30-60 cm vs POWER GWETROOT, all years": scores(m, "GWETROOT", "vwc_30_60")}
    table = pd.DataFrame(rows).T
    print(table.round(3).to_string())
    table.to_csv(out / "insitu_scores.csv")

    # spring soil-warm date (day of year): station vs model, per station-year
    # SMAP starts on 1 April 2025, so its comparison counts crossings from 4 April for both sides
    w = pd.concat([warm_dates(m, "soil_t10_c").rename("station"), warm_dates(m, "TSOIL1"),
                   warm_dates(m, "soil_t10_c", "04-04").rename("station_from_apr4"),
                   warm_dates(m, "TSOIL1", "04-04").rename("TSOIL1_from_apr4"),
                   warm_dates(m, "smap_soil_temp_layer1_c", "04-04")], axis=1)
    w.index.names = ["sid", "year"]
    for c, ref in (("TSOIL1", "station"), ("TSOIL1_from_apr4", "station_from_apr4"),
                   ("smap_soil_temp_layer1_c", "station_from_apr4")):
        d = (w[c] - w[ref]).dropna()
        if c != "TSOIL1":
            d = d[d.index.get_level_values("year") == 2025]
        print(f"10 C soil date, {c} minus {ref}{'' if c == 'TSOIL1' else ', 2025'}: n = {len(d)}, mean {d.mean():+.1f} d, "
              f"median {d.median():+.1f} d, MAE {d.abs().mean():.1f} d, within 7 d: {(d.abs() <= 7).mean():.0%}")
    w.reset_index().to_csv(out / "soil_warm_dates.csv", index=False)


if __name__ == "__main__":
    main()
