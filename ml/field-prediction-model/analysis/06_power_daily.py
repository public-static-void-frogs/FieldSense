"""Daily NASA POWER for every POWER cell, 1981-01-01 to 2026-09-30, with FAO-56 ET0 and soil wetness.

Two point requests per cell (POWER allows 20 parameters per request): the weather used by the field
panels plus clear-sky solar, and the MERRA-2 land surface: soil wetness of the top 5 cm, root zone
(~1 m) and profile, soil temperatures, snow and the evapotranspiration energy flux. Added columns:
- et0_mm: FAO-56 Penman-Monteith grass reference ET (Allen et al. 1998, eq. 6; G = 0 for days);
- gwetroot_pctl, gwettop_pctl: percentile of the day's soil wetness against the same cell's
  1991-2020 values within +-15 days of the day of year (0-100), comparable to SMAP's percentiles.
Checks, all printed: the 2025 days equal the daily panel's POWER columns; soil wetness and soil
temperature against SMAP L4 on the same 2025 days; ET0 against gridMET grass ET0.

Requests stop at 2026-09-30, the last MERRA-2 day: a request that reaches GEOS-IT days returns
precipitation x24 for the whole request (research/weather_climate.md).

Usage: python 06_power_daily.py --tables path/to/field_daily_2025 --cache power_daily_cache \
           --gridmet-cache gridmet_cache --out power_daily.parquet
"""
import argparse
import gzip
import io
import json
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
import duckdb
import numpy as np
import pandas as pd

START, END = "19810101", "20260930"
REQUESTS = {"wx": "T2M,T2M_MIN,T2M_MAX,T2MDEW,RH2M,QV2M,PRECTOTCORR,WS2M,WS10M,WD10M,PS,ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN",
            "land": "GWETTOP,GWETROOT,GWETPROF,TSOIL1,TSOIL2,TSURF,TS,SNODP,FRSNO,PRECSNOLAND,EVPTRNS"}
CLIMATE = (1991, 2020)
GRIDMET = ("http://thredds.northwestknowledge.net:8080/thredds/ncss/agg_met_pet_1979_CurrentYear_CONUS.nc"
           "?var=daily_mean_reference_evapotranspiration_grass&latitude={lat}&longitude={lon}"
           "&time_start=2001-01-01T00:00:00Z&time_end=2025-12-31T00:00:00Z&accept=csv")
GRIDMET_EVERY = 4                          # gridMET point requests are slow: check every 4th cell
CTX = ssl.create_default_context(cafile=certifi.where())


def get(url, timeout=300):
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "field-shift-research"})
            return urllib.request.urlopen(req, timeout=timeout, context=CTX).read()
        except Exception as e:  # POWER throttles bursts; back off and retry
            err = e
            time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"{url}: {err}")


def fetch(cell, kind, cache):
    path = cache / f"{cell}_{kind}.json.gz"
    if not path.exists():
        lat, lon = (float(v) for v in cell.split("_"))
        url = (f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={REQUESTS[kind]}&community=AG"
               f"&longitude={lon}&latitude={lat}&start={START}&end={END}&format=JSON")
        data = json.loads(get(url))
        assert "GEOSIT" not in data["header"]["sources"], "request reached GEOS-IT days"
        path.write_bytes(gzip.compress(json.dumps(data).encode()))
    data = json.loads(gzip.decompress(path.read_bytes()))
    df = pd.DataFrame(data["properties"]["parameter"]).replace(-999.0, np.nan)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    return df


def et0_fao56(lat_deg, d):
    """FAO-56 daily grass reference ET, mm/day, from POWER columns."""
    tx, tn, T = d.T2M_MAX, d.T2M_MIN, (d.T2M_MAX + d.T2M_MIN) / 2
    sat = lambda t: 0.6108 * np.exp(17.27 * t / (t + 237.3))
    es, ea = (sat(tx) + sat(tn)) / 2, sat(d.T2MDEW)
    delta = 4098 * sat(T) / (T + 237.3) ** 2
    gamma = 0.665e-3 * d.PS
    J = d.index.day_of_year.values
    lat = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * J / 365)
    dl = 0.409 * np.sin(2 * np.pi * J / 365 - 1.39)
    ws = np.arccos(-np.tan(lat) * np.tan(dl))
    ra = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(lat) * np.sin(dl) + np.cos(lat) * np.cos(dl) * np.sin(ws))
    z = 293 / 0.0065 * (1 - (d.PS / 101.3) ** (1 / 5.26))      # elevation from surface pressure
    rso = (0.75 + 2e-5 * z) * ra
    rs = d.ALLSKY_SFC_SW_DWN
    rnl = 4.903e-9 * ((tx + 273.16) ** 4 + (tn + 273.16) ** 4) / 2 * (0.34 - 0.14 * np.sqrt(ea)) * (1.35 * np.clip(rs / rso, 0, 1) - 0.35)
    rn = 0.77 * rs - rnl
    return (0.408 * delta * rn + gamma * 900 / (T + 273) * d.WS2M * (es - ea)) / (delta + gamma * (1 + 0.34 * d.WS2M))


def percentile_vs_climate(df, col):
    """Percentile of each day against the cell's CLIMATE-period values within +-15 days of its day of year."""
    out = np.full(len(df), np.nan)
    doy = np.minimum(df.date.dt.day_of_year.values, 365)
    clim = (df.date.dt.year >= CLIMATE[0]) & (df.date.dt.year <= CLIMATE[1])
    for _, idx in df.groupby("power_cell_id").indices.items():
        v, d, c = df[col].values[idx], doy[idx], clim.values[idx]
        for j in range(1, 366):
            dist = np.abs(d[c] - j)
            ref = np.sort(v[c][np.minimum(dist, 365 - dist) <= 15])
            ref = ref[~np.isnan(ref)]
            sel = d == j
            out[idx[sel]] = 100 * (np.searchsorted(ref, v[sel], side="left") + np.searchsorted(ref, v[sel], side="right")) / 2 / len(ref)
    return np.where(df[col].isna(), np.nan, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tables", required=True, help="output folder of 05_normalise_daily.py (2025 panel)")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--gridmet-cache", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cache, gcache = Path(args.cache), Path(args.gridmet_cache)
    cache.mkdir(parents=True, exist_ok=True)
    gcache.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    t = Path(args.tables)
    cells = [r[0] for r in con.execute(f"SELECT DISTINCT power_cell_id FROM '{t}/fields.parquet' ORDER BY 1").fetchall()]

    def cell_frame(cell):
        d = fetch(cell, "wx", cache).join(fetch(cell, "land", cache))
        d["et0_mm"] = et0_fao56(float(cell.split("_")[0]), d)
        return d.rename_axis("date").reset_index().assign(power_cell_id=cell)
    with ThreadPoolExecutor(max_workers=3) as ex:
        df = pd.concat(ex.map(cell_frame, cells), ignore_index=True)
    for c in ("GWETROOT", "GWETTOP"):
        df[c.lower() + "_pctl"] = percentile_vs_climate(df, c)
    df = df[["power_cell_id", "date"] + [c for c in df.columns if c not in ("power_cell_id", "date")]]
    print(f"{len(cells)} cells, {len(df):,} cell-days {df.date.min().date()}..{df.date.max().date()}")
    print("missing share:", df.isna().mean().round(4)[lambda s: s > 0].to_dict())
    con.register("pw", df)

    # 1. the panel's POWER columns are POWER: every 2025 value must match
    panel = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM '{t}/power_cellday.parquet'").fetchall()][2:]
    diff = con.execute(f"""SELECT count(*), {', '.join(f'max(abs(p.{c} - pw.{c.removeprefix("power_")}))' for c in panel)}
        FROM '{t}/power_cellday.parquet' p JOIN pw ON pw.power_cell_id = p.power_cell_id AND pw.date = p.date""").fetchone()
    print(f"panel check on {diff[0]:,} cell-days, max abs difference:", dict(zip(panel, diff[1:])))
    assert all(v < 1e-6 for v in diff[1:]), "POWER no longer reproduces the panel"
    df.to_parquet(args.out, compression="zstd", index=False)
    print(f"wrote {args.out}: {Path(args.out).stat().st_size / 1e6:.1f} MB")

    # 2. MERRA-2 land surface against SMAP L4, area-weighted to the POWER cell, same 2025 days
    sm = con.execute(f"""
        WITH w AS (SELECT power_cell_id, smap_cell_id, sum(area_acres) AS a FROM '{t}/fields.parquet' GROUP BY 1, 2)
        SELECT w.power_cell_id, s.date, {', '.join(f'sum(w.a * s.{c}) / sum(w.a) AS {c}' for c in
            ['smap_sm_surface_wetness', 'smap_sm_rootzone_wetness', 'smap_sm_profile_wetness', 'smap_sm_rootzone_pctl',
             'smap_soil_temp_layer1_c', 'smap_surface_temp_c', 'smap_et_mm'])}
        FROM w JOIN '{t}/smap_cellday.parquet' s USING (smap_cell_id) GROUP BY 1, 2""").df()
    m = sm.merge(df, on=["power_cell_id", "date"])
    m["evap_mm"] = m.EVPTRNS / 2.45                                # latent heat 2.45 MJ/kg
    rows = []
    for a, b in [("GWETTOP", "smap_sm_surface_wetness"), ("GWETROOT", "smap_sm_rootzone_wetness"),
                 ("GWETPROF", "smap_sm_profile_wetness"), ("gwetroot_pctl", "smap_sm_rootzone_pctl"),
                 ("TSOIL1", "smap_soil_temp_layer1_c"), ("TSURF", "smap_surface_temp_c"), ("evap_mm", "smap_et_mm")]:
        anom = m.groupby("date")[[a, b]].transform(lambda s: s - s.mean())   # spatial pattern of each day
        rows.append({"power": a, "smap": b, "r_daily": m[a].corr(m[b]), "r_spatial_anomaly": anom[a].corr(anom[b]),
                     "mean_power": m[a].mean(), "mean_smap": m[b].mean(), "rmse": np.sqrt(((m[a] - m[b]) ** 2).mean())})
    print(f"MERRA-2 vs SMAP L4, {len(m):,} cell-days 2025-04-01..2025-10-31:")
    print(pd.DataFrame(rows).round(3).to_string(index=False))

    # 3. ET0 against gridMET grass reference ET (4 km, station-calibrated), at POWER cell centres, 2001-2025.
    # The THREDDS server stalls under load: one probe decides whether to fetch, otherwise cached cells only.
    try:
        urllib.request.urlopen(GRIDMET.format(lat=42.0, lon=-93.75).replace("2001-01-01", "2025-12-01"), timeout=60).read()
        online = True
    except Exception as e:
        print(f"gridMET unreachable ({e}); comparing cached cells only")
        online = False

    def gridmet(cell):
        path = gcache / f"{cell}.csv"
        if not path.exists():
            if not online:
                return None
            lat, lon = cell.split("_")
            path.write_bytes(get(GRIDMET.format(lat=float(lat), lon=float(lon)), timeout=300))
        g = pd.read_csv(path)
        g.columns = ["time", "lat", "lon", "et0_gridmet"]
        # the CSV carries the packed integers (tenths of mm); scale_factor 0.1 is not applied
        assert (g.et0_gridmet.dropna() % 1 == 0).all()
        return pd.DataFrame({"power_cell_id": cell, "date": pd.to_datetime(g.time.str[:10]), "et0_gridmet": g.et0_gridmet * 0.1})
    with ThreadPoolExecutor(max_workers=3) as ex:
        got = [g for g in ex.map(gridmet, sorted(set(cells[::GRIDMET_EVERY]) | {p.stem for p in gcache.glob("*.csv")})) if g is not None]
    gm = pd.concat(got, ignore_index=True)
    gm = gm[gm.date.dt.year >= 2001]
    print(f"gridMET cells compared: {gm.power_cell_id.nunique()}")
    e = gm.merge(df[["power_cell_id", "date", "et0_mm"]], on=["power_cell_id", "date"]).dropna()
    e["month"] = e.date.dt.month
    print(f"ET0 vs gridMET, {len(e):,} cell-days: r = {e.et0_mm.corr(e.et0_gridmet):.3f}, "
          f"mean {e.et0_mm.mean():.2f} vs {e.et0_gridmet.mean():.2f} mm/day")
    by = e[e.month.between(4, 10)].groupby("month")[["et0_mm", "et0_gridmet"]].mean()
    by["ratio"] = by.et0_mm / by.et0_gridmet
    print(by.round(2).to_string())
    season = e[e.month.between(5, 9)].groupby([e.power_cell_id, e.date.dt.year])[["et0_mm", "et0_gridmet"]].sum()
    print(f"May-Sep sums per cell-year: r = {season.et0_mm.corr(season.et0_gridmet):.3f}, "
          f"ratio {season.et0_mm.mean() / season.et0_gridmet.mean():.3f}")
    gm.to_parquet(Path(args.out).with_name("gridmet_et0.parquet"), compression="zstd", index=False)


if __name__ == "__main__":
    main()
