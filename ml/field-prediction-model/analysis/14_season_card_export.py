"""Export the 2025 "field season" card data for the demo page: real CSB fields with every layer built so far.

Two fields per county (the largest that was corn in 2024 and the largest that was soybeans in 2024), each
with its own SMAP L4, IMERG and POWER cells for 1 April - 31 October 2025, its decoded USDM class per 2025
map (07), its CDL history and drought seasons 2018-2025 (07), the M3 windows of its POWER cell (10), the
county water ledger for corn and soybeans (11) and the county's cover-crop risk (11). CDL 2025 is not in
the data, so the 2025 crop is the rotation guess (corn after soybeans, soybeans after corn) and says so.

Usage: python 14_season_card_export.py --data path/to/Field-Shift-NASA-data --out season_card_2025.json
"""
import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

START, END = "2025-04-01", "2025-10-31"
CDL = {1: "corn", 5: "soybeans"}


def r(a, nd=1):
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), nd) for v in a]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    D = Path(args.data)
    con = duckdb.connect()
    t = D / "field_daily_2025"
    dates = pd.date_range(START, END)

    pick = con.execute(f"""
        SELECT * FROM (
            SELECT f.*, row_number() OVER (PARTITION BY county_fips, field_cdl_prev1 ORDER BY area_acres DESC) AS k
            FROM '{t}/fields.parquet' f WHERE field_cdl_prev1 IN (1, 5))
        WHERE k = 1 ORDER BY county_fips, field_cdl_prev1""").df()
    ids = pick.CSBID.tolist()
    con.register("pick", pick[["CSBID"]])
    districts = pd.read_parquet(D / "reference/iowa_county_district.parquet").set_index("county_fips")

    hist = con.execute(f"""SELECT h.* FROM '{D}/m2/field_season_drought.parquet' h JOIN pick USING (CSBID)""").df()
    usdm = con.execute(f"""SELECT u.CSBID, u.map_date, u.dm FROM '{D}/usdm/field_map_class_2018_2025.parquet' u JOIN pick USING (CSBID)
                           WHERE u.map_date BETWEEN DATE '2025-03-20' AND DATE '2025-10-31'""").df()
    maps = [d for d in pd.read_parquet(D / "usdm/map_dates.parquet").map_date if pd.Timestamp("2025-03-20") <= pd.Timestamp(d) <= pd.Timestamp(END)]

    fields = {}
    for p in pick.itertuples():
        h = hist[hist.CSBID == p.CSBID].set_index("season")
        crops = {int(y): (int(h.loc[y + 1, "crop_t1"]) if (y + 1) in h.index and pd.notna(h.loc[y + 1, "crop_t1"]) else None)
                 for y in range(2018, 2025)}
        u = usdm[usdm.CSBID == p.CSBID].set_index("map_date").dm
        fields[p.CSBID] = {
            "county": p.county_fips, "acres": round(p.area_acres, 1), "lon": round(p.centroid_lon, 4), "lat": round(p.centroid_lat, 4),
            "power": p.power_cell_id, "imerg": p.imerg_cell_id, "smap": p.smap_cell_id,
            "crops": crops, "crop_2024": CDL[int(p.field_cdl_prev1)], "crop_2025_guess": "soybeans" if p.field_cdl_prev1 == 1 else "corn",
            "d2_weeks_jul_aug": {int(y): int(v) for y, v in h.d2_jul_aug.items()},
            "usdm_2025": [int(u.get(m, -1)) for m in maps]}

    cells = {k: sorted({f[k] for f in fields.values()}) for k in ("smap", "imerg", "power")}
    con.register("sc", pd.DataFrame({"smap_cell_id": cells["smap"]}))
    sm = con.execute(f"""SELECT s.smap_cell_id, s.date, s.smap_sm_rootzone_pctl, s.smap_sm_rootzone, s.smap_sm_surface_wetness,
                                s.smap_soil_temp_layer1_c, s.smap_et_mm
                         FROM '{t}/smap_cellday.parquet' s JOIN sc USING (smap_cell_id) ORDER BY 1, 2""").df()
    im = pd.read_parquet(t / "imerg_cellday.parquet", columns=["imerg_cell_id", "date", "imerg_precipitation"])
    pw = pd.read_parquet(D / "power/power_daily.parquet", columns=["power_cell_id", "date", "et0_mm", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"])
    pw = pw[pw.date.between(START, END)]

    def series(df, key, cell, col):
        s = df[df[key] == cell].set_index("date")[col]
        s.index = pd.to_datetime(s.index)
        return s.reindex(dates).to_numpy(float)
    smap = {c: {"rz_pctl": r(series(sm, "smap_cell_id", c, "smap_sm_rootzone_pctl"), 0),
                "rz_vwc": r(series(sm, "smap_cell_id", c, "smap_sm_rootzone"), 3),
                "surf_wet": r(series(sm, "smap_cell_id", c, "smap_sm_surface_wetness"), 2),
                "soil_t": r(series(sm, "smap_cell_id", c, "smap_soil_temp_layer1_c"), 1),
                "et": r(series(sm, "smap_cell_id", c, "smap_et_mm"), 2)} for c in cells["smap"]}
    imerg = {c: r(series(im, "imerg_cell_id", c, "imerg_precipitation"), 1) for c in cells["imerg"]}
    power = {c: {"et0": r(series(pw, "power_cell_id", c, "et0_mm"), 2), "tmax": r(series(pw, "power_cell_id", c, "T2M_MAX"), 1),
                 "tmin": r(series(pw, "power_cell_id", c, "T2M_MIN"), 1), "rain": r(series(pw, "power_cell_id", c, "PRECTOTCORR"), 1)}
             for c in cells["power"]}

    # M3: per-cell quantiles 1991-2025 and the cell's own 2025 events
    cs = pd.read_parquet(D / "m3/cell_summary.parquet").set_index("power_cell_id")
    cy = pd.read_parquet(D / "m3/cell_year.parquet").set_index(["power_cell_id", "year"])
    events = ["soil10_doy", "corn_planted50_doy", "soybeans_planted50_doy", "last_spring_frost_0c_doy",
              "first_autumn_frost_0c_doy", "last_spring_frost_m2c_doy", "first_autumn_frost_m2c_doy", "silk_doy", "mature_doy"]
    m3 = {}
    for c in cells["power"]:
        s, y = cs.loc[c], cy.loc[(c, 2025)]
        m3[c] = {e: {"p10": s.get(f"{e}_p10"), "p50": s.get(f"{e}_p50"), "p90": s.get(f"{e}_p90"), "y2025": y.get(e),
                     "trend": s.get(f"{e}_trend_per_decade"), "trend_p": s.get(f"{e}_trend_p")} for e in events}
        m3[c]["heat35_p_any"] = {str(o): s.get(f"heat35_days_silk{'' if o == 0 else f'_plant{o:+d}d'}_p_any") for o in (-10, 0, 10, 20)}
        m3[c]["workable_days_apr15_may31"] = {"p10": s.get("workable_days_apr15_may31_p10"), "p50": s.get("workable_days_apr15_may31_p50"),
                                              "p90": s.get("workable_days_apr15_may31_p90"), "y2025": y.get("workable_days_apr15_may31")}
        m3[c]["killing_frost_after_corn10"] = s.get("killing_frost_after_corn10_mean")
        m3[c]["frost_before_maturity"] = s.get("frost_before_maturity_mean")

    nass = {}
    for crop in ("corn", "soybeans"):
        v = pd.read_csv(D / f"m3/validation_{crop}_planted50.csv")
        for row in v[v.year == 2025].itertuples():
            nass.setdefault(row.district, {})[crop] = {"nass50": row.nass50, "model50": row.model50}

    # county ledger 2025 and its history
    counties = sorted({f["county"] for f in fields.values()})
    con.register("cty", pd.DataFrame({"county_fips": counties}))
    led = con.execute(f"""SELECT l.county_fips, l.crop, l.date, l.rel_soil_water, l.ks FROM '{D}/water/ledger_daily.parquet' l
                          JOIN cty USING (county_fips) WHERE l.date BETWEEN DATE '{START}' AND DATE '{END}' ORDER BY 1, 2, 3""").df()
    season = pd.read_parquet(D / "water/county_season.parquet")
    m9 = pd.read_parquet(D / "water/m9_county_year.parquet")
    soils = pd.read_parquet(D / "reference/county_soils.parquet").set_index("county_fips")
    ledger, county_info = {}, {}
    for c in counties:
        ledger[c] = {}
        for crop in ("corn", "soybeans"):
            l = led[(led.county_fips == c) & (led.crop == crop)].set_index("date")
            l.index = pd.to_datetime(l.index)
            l = l.reindex(dates)
            s = season[(season.county_fips == c) & (season.crop == crop)]
            h = s[s.year.between(1991, 2025)]
            s25 = s[s.year == 2025].iloc[0]
            g = m9[(m9.county_fips == c) & (m9.prev_crop == crop)]
            ledger[c][crop] = {
                "rsw": r(l.rel_soil_water.to_numpy(float), 3), "ks": r(l.ks.to_numpy(float), 2),
                "p": 0.55 if crop == "corn" else 0.50,
                "y2025": {"plant": str(s25.plant_date.date()), "mature": str(s25.mature_date.date()),
                          "silk": str(s25.silk_date.date()) if crop == "corn" and pd.notna(s25.get("silk_date")) else None,
                          "m6": round(s25.m6_etc_mm), "m7": round(s25.m7_gap_mm), "rain": round(s25.rain_mm), "stress_days": int(s25.stress_days)},
                "hist": {"m6_p50": round(h.m6_etc_mm.median()), "m7_p50": round(h.m7_gap_mm.median()), "m7_p90": round(h.m7_gap_mm.quantile(0.9)),
                         "worst_year": int(h.loc[h.m7_gap_mm.idxmax(), "year"]), "worst_m7": round(h.m7_gap_mm.max())},
                "m9_after": {b: round(float(g[g.branch == b].dry_start.mean()), 3) for b in ("bare", "cover")},
                "m9_extra_depletion": round(float((g[g.branch == "bare"].set_index("harvest_year").paw_plant_frac
                                                   - g[g.branch == "cover"].set_index("harvest_year").paw_plant_frac).mean()), 3)}
        f0 = pick[pick.county_fips == c].iloc[0]
        county_info[c] = {"name": f0.county_name, "district": districts.loc[c, "district"],
                          "csr2": round(soils.loc[c, "csr2"]), "aws100": round(soils.loc[c, "aws_0_100cm_mm"]),
                          "fields": pick[pick.county_fips == c].CSBID.tolist()}

    out = {"dates": [d.strftime("%Y-%m-%d") for d in dates], "usdm_maps": [str(pd.Timestamp(m).date()) for m in maps],
           "counties": county_info, "fields": fields, "smap": smap, "imerg": imerg, "power": power, "m3": m3,
           "nass2025": nass, "ledger": ledger}
    def clean(v):                                       # JSON has no NaN: missing values become null
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items()}
        if isinstance(v, list):
            return [clean(x) for x in v]
        if isinstance(v, (float, np.floating)):
            return None if np.isnan(v) else float(v)
        if isinstance(v, np.integer):
            return int(v)
        return v
    text = json.dumps(clean(out), separators=(",", ":"), allow_nan=False)
    Path(args.out).write_text(text)
    print(f"{len(fields)} fields in {len(counties)} counties; cells: SMAP {len(cells['smap'])}, IMERG {len(cells['imerg'])}, "
          f"POWER {len(cells['power'])}; {len(text) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
