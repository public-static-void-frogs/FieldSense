"""U.S. Drought Monitor class at every field for every weekly map 2018-2025, and the M2 drought-season units.

field_dataset holds one April drought snapshot per year and the 2025 daily panel holds one year, so in-season
drought exposure is rebuilt here from the weekly USDM shapefiles (WGS84, one multipolygon per class D0-D4):

- class at a field centroid = highest DM polygon containing it, -1 = none;
- validated against the 2025 daily panel, where a map is in force from its valid date + 2 days and the
  stale-coded class decodes as drought_dm if drought_map_age_days <= 8 else -1. The panel never carries the
  2025-06-10 map, so on 12-18 June 2025 it reads every field as out of drought; that map is reported apart;
- drought season (Sivozmina_Proposal.md section 4.3, step 1): D2+ in >= 4 of the maps dated in July-August;
- crop history from CSB via field_dataset (CDL t = field_cdl_prev1 of year t+1 or field_cdl_prev2 of year t+2)
  and the 2025 panel (CDL 2024, 2023 for every field). CDL 2025 is in neither.

Usage: python 07_usdm_field_drought.py --dataset path/to/field_dataset --daily path/to/field_daily_2025_enriched/2025 \
           --cache usdm_cache --out outdir
"""
import argparse
import datetime as dt
import io
import json
import ssl
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import shapefile
import shapely

CTX = ssl.create_default_context(cafile=certifi.where())
FIRST, LAST = dt.date(2018, 1, 2), dt.date(2025, 12, 30)
SHP_URL = "https://droughtmonitor.unl.edu/data/shapefiles_m/USDM_{d}_M.zip"
JSON_URL = "https://droughtmonitor.unl.edu/data/json/usdm_{d}.json"
BBOX = (-97.5, 39.5, -89.0, 44.5)                    # Iowa with a margin, lon/lat
CORN, SOY = 1, 5
SMALL_GRAIN = (21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 205, 225, 226, 230, 234, 235, 236, 237, 240, 254)
HAY = (36, 37, 58)                                   # alfalfa, other hay, clover; grassland/pasture (176) is not a rotation crop


def get(url):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "field-shift-research"})
            return urllib.request.urlopen(req, timeout=180, context=CTX).read()
        except Exception as e:
            err = e
            if getattr(e, "code", None) == 404:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{url}: {err}")


def fetch(day, cache):
    d = day.strftime("%Y%m%d")
    shp, js = cache / f"USDM_{d}_M.zip", cache / f"usdm_{d}.json"
    if shp.exists():
        return day, "shapefile"
    if js.exists():
        return day, "geojson"
    try:
        shp.write_bytes(get(SHP_URL.format(d=d)))
        return day, "shapefile"
    except Exception:
        js.write_bytes(get(JSON_URL.format(d=d)))
        return day, "geojson"


def read_map(day, source, cache):
    """{dm: geometry clipped to BBOX}"""
    d = day.strftime("%Y%m%d")
    if source == "shapefile":
        z = zipfile.ZipFile(cache / f"USDM_{d}_M.zip")
        prj = [n for n in z.namelist() if n.lower().endswith(".prj")]
        assert prj and b"GCS_WGS_1984" in z.read(prj[0]), f"{d}: unexpected CRS"
        base = [n[:-4] for n in z.namelist() if n.lower().endswith(".shp")][0]
        r = shapefile.Reader(shp=io.BytesIO(z.read(base + ".shp")), shx=io.BytesIO(z.read(base + ".shx")),
                             dbf=io.BytesIO(z.read(base + ".dbf")))
        names = [f[0] for f in r.fields[1:]]
        items = [(int(rec[names.index("DM")]), shapely.geometry.shape(s.__geo_interface__)) for rec, s in
                 zip(r.records(), r.shapes())]
    else:
        gj = json.loads((cache / f"usdm_{d}.json").read_bytes())
        items = [(int(f["properties"]["DM"]), shapely.geometry.shape(f["geometry"])) for f in gj["features"]]
    box, out = shapely.box(*BBOX), {}
    for dm, g in items:
        parts = shapely.get_parts(g)
        parts = parts[shapely.intersects(shapely.envelope(parts), box)]
        if len(parts):
            g = shapely.intersection(shapely.make_valid(shapely.multipolygons(parts)), box)
            out[dm] = shapely.union(out[dm], g) if dm in out else g
    return out


def classify(geoms, lon, lat):
    cls = np.full(len(lon), -1, dtype=np.int8)
    for dm in sorted(geoms):
        shapely.prepare(geoms[dm])
        cls[shapely.contains_xy(geoms[dm], lon, lat)] = dm
    return cls


def crop_history(con, dataset, daily):
    """CDL per field and year 2013-2024 from every source that carries it; mismatches between sources are counted."""
    con.execute(f"""CREATE TABLE src AS
        WITH fd AS (SELECT DISTINCT CSBID, year, field_cdl_prev1 AS p1, field_cdl_prev2 AS p2
                    FROM read_parquet('{dataset}/year=*/part.parquet', union_by_name = true, hive_partitioning = false)
                    WHERE field_cdl_prev1 IS NOT NULL OR field_cdl_prev2 IS NOT NULL),
             dp AS (SELECT DISTINCT CSBID, field_cdl_prev1 AS p1, field_cdl_prev2 AS p2
                    FROM read_parquet('{daily}/*.parquet') WHERE date = DATE '2025-07-01')
        SELECT CSBID, year - 1 AS cdl_year, p1 AS cdl, 'fd_prev1' AS src FROM fd WHERE p1 IS NOT NULL
        UNION ALL SELECT CSBID, year - 2, p2, 'fd_prev2' FROM fd WHERE p2 IS NOT NULL
        UNION ALL SELECT CSBID, 2024, p1, 'daily_prev1' FROM dp WHERE p1 IS NOT NULL
        UNION ALL SELECT CSBID, 2023, p2, 'daily_prev2' FROM dp WHERE p2 IS NOT NULL""")
    check = con.execute("""SELECT cdl_year, count(*) AS field_years, count(*) FILTER (WHERE n_values > 1) AS conflicting
        FROM (SELECT CSBID, cdl_year, count(DISTINCT cdl) AS n_values FROM src GROUP BY ALL) GROUP BY 1 ORDER BY 1""").df()
    hist = con.execute("""SELECT CSBID, cdl_year, arg_min(cdl, CASE src WHEN 'daily_prev1' THEN 0 WHEN 'daily_prev2' THEN 1
        WHEN 'fd_prev1' THEN 2 ELSE 3 END) AS cdl FROM src GROUP BY ALL""").df()
    return check, hist


def study_units(sd):
    """Fields, acres and county counts per season x crop x drought x treatment arm (CSB-derivable treatments only)."""
    rows, contrasts = [], []
    sd = sd[sd.crop_t.isin([CORN, SOY])].copy()
    for c in [c for c in sd.columns if c.startswith("crop_t")]:
        sd[c] = sd[c].astype(float)
    other = {CORN: SOY, SOY: CORN}
    name = {CORN: "corn", SOY: "soy"}

    def tag(code, crop):
        if pd.isna(code):
            return None
        return "same" if code == crop else "rotated" if code == other[crop] else "other"

    for crop in (CORN, SOY):
        s = sd[sd.crop_t == crop].copy()
        s["T1"] = [tag(c, crop) for c in s.crop_t1]
        s["T1"] = s["T1"].map({"same": f"{name[crop]} after {name[crop]}", "rotated": f"{name[crop]} after {name[other[crop]]}",
                               "other": f"{name[crop]} after other"})
        seq = [None if pd.isna(a) or pd.isna(b) else
               "".join("C" if c == CORN else "S" if c == SOY else "O" for c in (a, b)) for a, b in zip(s.crop_t2, s.crop_t1)]
        s["seq_t2_t1"] = seq
        prev5 = s[[f"crop_t{k}" for k in range(1, 6)]]
        groups = prev5.apply(lambda col: np.select([col == CORN, col == SOY, col.isin(SMALL_GRAIN), col.isin(HAY)],
                                                   ["corn", "soy", "small_grain", "hay"], "other"))
        groups = groups.where(prev5.notna())
        s["T2"] = np.where(prev5.notna().all(axis=1), np.where(groups.nunique(axis=1) >= 3, ">=3 groups", "1-2 groups"), None)
        prev3 = s[["crop_t1", "crop_t2", "crop_t3"]]
        has = prev3.isin(SMALL_GRAIN + HAY).any(axis=1)
        s["T3"] = np.where(prev3.notna().all(axis=1), np.where(has, "small grain/hay present", "absent"), None)
        # host return interval; ">= 2 years" against "1 year" is the same split as T1 for corn and soybeans
        s["T5"] = np.select([s.crop_t1 == crop, s.crop_t1.notna() & (s.crop_t2 == crop),
                             s.crop_t1.notna() & s.crop_t2.notna()], ["1 year", "2 years", ">=3 years"], None)
        for t in ("T1", "seq_t2_t1", "T2", "T3", "T5"):
            g = s[s[t].notna()].groupby(["season", "usdm_drought_season", t])
            agg = g.agg(fields=("CSBID", "size"), acres=("area_acres", "sum")).reset_index()
            per_county = s[s[t].notna()].groupby(["season", "usdm_drought_season", t, "county_fips"]).size()
            agg["counties_ge100"] = [int((per_county.loc[(a, b, c)] >= 100).sum()) for a, b, c in
                                     zip(agg.season, agg.usdm_drought_season, agg[t])]
            agg = agg.rename(columns={t: "arm"}).assign(crop=name[crop], treatment=t)
            rows.append(agg)
        pairs = [("T1", f"{name[crop]} after {name[crop]}", f"{name[crop]} after {name[other[crop]]}"),
                 ("T3", "small grain/hay present", "absent"), ("T2", ">=3 groups", "1-2 groups")]
        for t, a, b in pairs:
            pc = s[s[t].isin([a, b])].groupby(["season", "usdm_drought_season", "county_fips", t]).size().unstack(t, fill_value=0)
            for col in (a, b):
                if col not in pc:
                    pc[col] = 0
            g = pc.groupby(level=[0, 1])
            contrasts.append(pd.DataFrame({
                "crop": name[crop], "treatment": t, "arm_a": a, "arm_b": b,
                "fields_a": g[a].sum(), "fields_b": g[b].sum(),
                "counties_both_ge100": g.apply(lambda x: int(((x[a] >= 100) & (x[b] >= 100)).sum())),
                "counties_both_ge30": g.apply(lambda x: int(((x[a] >= 30) & (x[b] >= 30)).sum()))}).reset_index())
    units = pd.concat(rows, ignore_index=True)[["season", "crop", "usdm_drought_season", "treatment", "arm",
                                                "fields", "acres", "counties_ge100"]]
    return units.sort_values(["season", "crop", "treatment", "usdm_drought_season", "arm"]), \
        pd.concat(contrasts, ignore_index=True).sort_values(["season", "crop", "treatment", "usdm_drought_season"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--daily", required=True, help="2025 daily panel folder (*.parquet), used for validation and CDL 2023-2024")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True, help="output root: writes usdm/ and m2/ below it")
    args = ap.parse_args()
    cache, out = Path(args.cache), Path(args.out)
    cache.mkdir(parents=True, exist_ok=True)
    (out / "usdm").mkdir(parents=True, exist_ok=True)
    (out / "m2").mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit = '3GB'")
    con.execute("SET threads = 4")

    fields = con.execute(f"""SELECT DISTINCT CSBID, county_fips, centroid_lon, centroid_lat, area_acres
        FROM read_parquet('{args.dataset}/year=*/part.parquet', union_by_name = true, hive_partitioning = false)
        ORDER BY CSBID""").df()
    assert fields.CSBID.is_unique, "field attributes are not constant"
    lon, lat = fields.centroid_lon.to_numpy(), fields.centroid_lat.to_numpy()
    print(f"{len(fields):,} fields")

    days = [FIRST + dt.timedelta(weeks=k) for k in range((LAST - FIRST).days // 7 + 1)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        sources = dict(ex.map(lambda d: fetch(d, cache), days))
    pd.DataFrame({"map_date": days, "source": [sources[d] for d in days]}).to_parquet(
        out / "usdm" / "map_dates.parquet", index=False, compression="zstd")
    print(f"{len(days)} maps {days[0]} .. {days[-1]}; GeoJSON fallback: {sum(v == 'geojson' for v in sources.values())}")

    years = range(FIRST.year, LAST.year + 1)
    keys = ["d1_jul_aug", "d2_jul_aug", "d1_may_sep", "d2_may_sep", "maps_jul_aug", "maps_may_sep"]
    acc = {y: {k: np.zeros(len(fields), np.int16) for k in keys} | {"max_jul_aug": np.full(len(fields), -1, np.int8)}
           for y in years}
    csbid = pa.array(fields.CSBID)
    schema = pa.schema([("CSBID", pa.string()), ("map_date", pa.date32()), ("dm", pa.int8())])
    with pq.ParquetWriter(out / "usdm" / "field_map_class_2018_2025.parquet", schema, compression="zstd") as w:
        for day in days:
            cls = classify(read_map(day, sources[day], cache), lon, lat)
            idx = np.flatnonzero(cls >= 0)
            w.write_table(pa.table({"CSBID": csbid.take(pa.array(idx)), "map_date": pa.array([day] * len(idx), pa.date32()),
                                    "dm": pa.array(cls[idx], pa.int8())}, schema=schema))
            a = acc[day.year]
            if 7 <= day.month <= 8:
                a["d1_jul_aug"] += cls >= 1
                a["d2_jul_aug"] += cls >= 2
                a["maps_jul_aug"] += 1
                np.maximum(a["max_jul_aug"], cls, out=a["max_jul_aug"])
            if 5 <= day.month <= 9:
                a["d1_may_sep"] += cls >= 1
                a["d2_may_sep"] += cls >= 2
                a["maps_may_sep"] += 1
    share = con.execute(f"SELECT year(map_date) AS y, count(*) FROM '{out}/usdm/field_map_class_2018_2025.parquet' GROUP BY 1 ORDER BY 1").fetchall()
    print("field-map rows with D0+ by year:", share)

    # validation: the class implied by the 2025 panel on the first panel day each map is in force
    panel_days = pd.DataFrame([(m, max(m + dt.timedelta(days=2), dt.date(2025, 4, 1))) for m in days if m.year >= 2025 or
                               m == dt.date(2024, 12, 31)], columns=["map_date", "day"])
    panel_days = panel_days[(panel_days.day <= panel_days.map_date + dt.timedelta(days=8)) & (panel_days.day <= dt.date(2025, 10, 31))]
    con.register("panel_days", panel_days)
    con.execute(f"""CREATE TABLE implied AS SELECT p.map_date, e.CSBID,
            CASE WHEN e.drought_map_age_days <= 8 THEN CAST(e.drought_dm AS TINYINT) ELSE -1 END AS panel,
            e.drought_valid_date = p.map_date OR e.drought_map_age_days > 8 AS consistent
        FROM read_parquet('{args.daily}/*.parquet') e JOIN panel_days p ON e.date = p.day""")
    assert con.execute("SELECT bool_and(consistent) FROM implied").fetchone()[0], "panel map in force is not valid date + 2 days"
    con.execute(f"""CREATE TABLE cmp AS SELECT i.map_date, i.CSBID, i.panel, coalesce(o.dm, -1) AS ours
        FROM implied i LEFT JOIN '{out}/usdm/field_map_class_2018_2025.parquet' o USING (CSBID, map_date)""")
    val = con.execute("""SELECT map_date, count(*) AS fields, count(*) FILTER (WHERE panel = ours) AS agree,
        count(*) FILTER (WHERE panel <> ours) AS disagree, count(*) FILTER (WHERE panel >= 0) AS panel_d0plus,
        count(*) FILTER (WHERE ours >= 0) AS ours_d0plus FROM cmp GROUP BY 1 ORDER BY 1""").df()
    print("validation against the 2025 panel:\n" + val.to_string(index=False))
    # a map that no panel row ever carries was skipped when the panel was built (2025-06-10): count it apart
    used = {r[0] for r in con.execute(f"SELECT DISTINCT drought_valid_date FROM read_parquet('{args.daily}/*.parquet')").fetchall()}
    val["in_panel"] = [m in used or d0 == 0 for m, d0 in zip(val.map_date.dt.date, val.ours_d0plus)]
    skipped = [m.date() for m in val.map_date[~val.in_panel]]
    print("maps missing from the panel:", [str(m) for m in skipped])
    for m in skipped:
        con.execute("DELETE FROM cmp WHERE map_date = ?", [m])
    val.to_csv(out / "usdm" / "validation_2025.csv", index=False)
    val = val[val.in_panel]
    n, bad = int(val.fields.sum()), int(val.disagree.sum())
    print(f"total {n:,} field-maps, disagreements {bad:,}")
    if bad:
        print(con.execute("SELECT panel, ours, count(*) FROM cmp WHERE panel <> ours GROUP BY ALL ORDER BY 3 DESC").df().to_string(index=False))
    assert bad <= 1e-4 * n, "polygon classes do not reproduce the 2025 panel"
    con.execute("DROP TABLE implied; DROP TABLE cmp")

    check, hist = crop_history(con, args.dataset, args.daily)
    print("CDL sources per year (field-years, conflicting values):\n" + check.to_string(index=False))
    wide = hist.pivot(index="CSBID", columns="cdl_year", values="cdl").reindex(fields.CSBID)
    del hist
    print("CDL coverage by year:", {int(y): int(wide[y].notna().sum()) for y in wide.columns})

    frames, base = [], fields[["CSBID", "county_fips", "area_acres"]].astype({"CSBID": "category", "county_fips": "category"})
    for y in years:
        a = acc[y]
        f = base.assign(season=y)
        for k in keys + ["max_jul_aug"]:
            f[k] = a[k]
        f["usdm_drought_season"] = f.d2_jul_aug >= 4
        for k in range(0, 6):
            col = y - k
            f["crop_t" if k == 0 else f"crop_t{k}"] = wide[col].to_numpy() if col in wide.columns else np.nan
        frames.append(f)
    sd = pd.concat(frames, ignore_index=True)
    for c in [c for c in sd.columns if c.startswith("crop_t")]:
        sd[c] = sd[c].astype("Int16")
    sd.to_parquet(out / "m2" / "field_season_drought.parquet", index=False, compression="zstd")
    print("drought seasons (fields, counties with any):\n" + sd.groupby("season").agg(
        fields_drought=("usdm_drought_season", "sum"), maps_jul_aug=("maps_jul_aug", "max"),
        counties=("county_fips", lambda c: c[sd.loc[c.index, "usdm_drought_season"]].nunique())).to_string())

    units, contrasts = study_units(sd[sd.season <= 2024])
    units.to_csv(out / "m2" / "study_units_summary.csv", index=False)
    contrasts.to_csv(out / "m2" / "contrast_capacity.csv", index=False)
    pd.set_option("display.width", 250)
    print(units[units.treatment == "T1"].to_string(index=False))
    print(contrasts.to_string(index=False))


if __name__ == "__main__":
    main()
