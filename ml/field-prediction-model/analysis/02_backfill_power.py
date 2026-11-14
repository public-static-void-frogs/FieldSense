"""Recompute the POWER summer features for every POWER cell in field_dataset, for all years.

field_dataset holds these features only for target years 2019-2025. The definitions were matched
exactly against the POWER API (see research/data_sources/fields/field_dataset.md, section 3):
season = 1 May-30 Sep, hot day = T2M_MAX >= 32 C, cold day = T2M_MIN <= 0 C, dry day =
PRECTOTCORR < 1 mm, solar = sum of daily ALLSKY_SFC_SW_DWN (MJ/m2). Before any backfilled value is
used, the recomputed 2018-2024 seasons must equal the dataset's 2019-2025 rows for every cell.

Requests stop at 2025-09-30: a POWER daily request that reaches GEOS-IT days (from Oct 2026 here)
returns precipitation x24 for the whole request.

Usage: python 02_backfill_power.py --dataset path/to/field_dataset --cache power_cache --out power_seasons.csv
"""
import argparse
import json
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
import duckdb
import pandas as pd

START, END = "19890101", "20250930"
PARAMS = "T2M,T2M_MIN,T2M_MAX,PRECTOTCORR,ALLSKY_SFC_SW_DWN"
FEATURES = ["t2m_mean", "tmin_mean", "tmax_mean", "cold_days", "hot_days", "precip_sum", "dry_days", "solar_sum"]
DATASET_COLS = {"t2m_mean": "power_t2m_prev_season_mean", "tmin_mean": "power_tmin_prev_season_mean",
                "tmax_mean": "power_tmax_prev_season_mean", "cold_days": "power_cold_days_prev_season",
                "hot_days": "power_hot_days_prev_season", "precip_sum": "power_precip_prev_season_sum",
                "dry_days": "power_dry_days_prev_season", "solar_sum": "power_solar_prev_season"}
CTX = ssl.create_default_context(cafile=certifi.where())


def fetch(cell, cache):
    path = cache / f"{cell}.json"
    if path.exists():
        return json.loads(path.read_text())
    lat, lon = (float(v) for v in cell.split("_"))
    url = (f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={PARAMS}&community=AG"
           f"&longitude={lon}&latitude={lat}&start={START}&end={END}&format=JSON")
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "field-shift-research"})
            data = json.loads(urllib.request.urlopen(req, timeout=300, context=CTX).read())
            assert "GEOSIT" not in data["header"]["sources"], "request reached GEOS-IT days"
            path.write_text(json.dumps(data))
            return data
        except Exception as e:  # POWER throttles bursts; back off and retry
            err = e
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"{cell}: {err}")


def seasons(cell, data):
    p = data["properties"]["parameter"]
    df = pd.DataFrame(p).replace(-999.0, float("nan"))
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df[(df.index.month >= 5) & (df.index.month <= 9)]
    g = df.groupby(df.index.year)
    out = pd.DataFrame({
        "t2m_mean": g.T2M.mean(), "tmin_mean": g.T2M_MIN.mean(), "tmax_mean": g.T2M_MAX.mean(),
        "cold_days": g.T2M_MIN.apply(lambda s: int((s <= 0).sum())),
        "hot_days": g.T2M_MAX.apply(lambda s: int((s >= 32).sum())),
        "precip_sum": g.PRECTOTCORR.sum(), "dry_days": g.PRECTOTCORR.apply(lambda s: int((s < 1).sum())),
        "solar_sum": g.ALLSKY_SFC_SW_DWN.sum(), "n_days": g.T2M.count()})
    out.index.name = "season_year"
    out.insert(0, "power_cell_id", cell)
    return out.reset_index()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--cache", required=True, help="folder for raw POWER JSON (one file per cell)")
    ap.add_argument("--out", required=True, help="output CSV: one row per cell x season year")
    args = ap.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"CREATE VIEW fd AS SELECT * EXCLUDE (drought_dm) FROM read_parquet('{args.dataset}/year=*/part.parquet', union_by_name = true)")
    cells = [r[0] for r in con.execute("SELECT DISTINCT power_cell_id FROM fd ORDER BY 1").fetchall()]
    print(f"{len(cells)} POWER cells")
    with ThreadPoolExecutor(max_workers=4) as ex:  # POWER allows up to 5 concurrent requests
        data = dict(zip(cells, ex.map(lambda c: fetch(c, cache), cells)))
    table = pd.concat([seasons(c, d) for c, d in data.items()], ignore_index=True)
    assert (table.n_days == 153).all(), "a season is incomplete"

    # consistency gate: recomputed season t-1 must equal the dataset's target-year t values
    ref = con.execute(f"""SELECT DISTINCT power_cell_id, year - 1 AS season_year, {', '.join(DATASET_COLS.values())}
                          FROM fd WHERE power_t2m_prev_season_mean IS NOT NULL""").df()
    m = ref.merge(table, on=["power_cell_id", "season_year"], how="left", validate="one_to_one")
    worst = {f: float((m[f] - m[c]).abs().max()) for f, c in DATASET_COLS.items()}
    print("max |recomputed - dataset| over", len(m), "cell-seasons:", worst)
    assert all(v < 1e-6 for v in worst.values()), "backfill does not reproduce the dataset"

    table.drop(columns="n_days").to_csv(args.out, index=False)
    print(f"wrote {len(table)} cell-seasons, {table.season_year.min()}-{table.season_year.max()}")


if __name__ == "__main__":
    main()
