"""Do corn and soybeans do better after a small grain or hay, on the SAME field?

The same design as ndvi_field_panel.py: field and county x year fixed effects, standard errors
clustered by county, greenness turned into yield by the county slope. Corn after a small grain
(CDL 21-29, 205; double-crop wheat/soybeans included) or hay (36, 37) is set against corn after
soybeans; soybeans against soybeans after corn. The changes are greenness-implied and still
attenuated (MODIS mixes neighbouring fields): calibrate_yield_factors.py scales them.

    python rule_engine/planner/scripts/small_grain_field_panel.py --root data/local/usa_sample_v3 \
        --ndvi ../Field-Shift-NASA/data/local/planner/greenness/modis
"""

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ndvi_field_panel as P  # noqa: E402

SMALL = (21, 22, 23, 24, 25, 26, 27, 28, 29, 205)
HAY = (36, 37)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--ndvi", required=True, type=Path)
    args = ap.parse_args()
    root = args.root.resolve()
    yields = root / "yields" / "nass_yield.parquet"
    con = duckdb.connect()
    con.execute("SET memory_limit = '4GB'; SET threads = 4")
    union = " UNION ALL ".join(
        f"SELECT CSBID, {y} AS year, CDL{y} AS now, CDL{y - 1} AS prev1 "
        f"FROM read_parquet('{root}/cdl_history_all.parquet')"
        for y in P.YEARS
    )
    files = ", ".join(f"'{args.ndvi}/{y}.parquet'" for y in P.YEARS)
    windows = ",\n".join(
        f"avg(ndvi) FILTER (dayofyear(date) BETWEEN {a} AND {b}) AS {k}"
        for k, (a, b) in P.WINDOWS.items()
    )
    con.execute(
        f"""CREATE TABLE n AS SELECT field_id, year(date) AS year, count(*) AS composites,
        avg(ndvi) AS season_mean, max(ndvi) AS peak, {windows}
        FROM read_parquet([{files}]) WHERE ndvi IS NOT NULL GROUP BY ALL"""
    )
    keep = " AND ".join(f"n.{m} IS NOT NULL" for m in P.METRICS)
    con.execute(
        f"""CREATE TABLE p AS
        WITH f AS (SELECT CSBID, STATEFIPS || CNTYFIPS AS county, CSBACRES::DOUBLE AS acres
                   FROM read_csv('{root}/fields.csv', all_varchar=true))
        SELECT c.*, f.county, f.acres, n.* EXCLUDE (field_id, year)
        FROM ({union}) c JOIN f USING (CSBID)
        JOIN n ON n.field_id = c.CSBID AND n.year = c.year
        WHERE c.now IN (1, 5) AND n.composites >= 10 AND {keep} AND c.prev1 IS NOT NULL"""
    )
    small, hay = ", ".join(map(str, SMALL)), ", ".join(map(str, HAY))
    out = {}
    for crop, (code, nass) in P.CROPS.items():
        slopes = P.yield_slopes(con, yields, code, nass)
        best = max(P.METRICS, key=lambda m: slopes[m]["within_r2"])
        partner = 5 if code == 1 else 1
        rows = P.plain(
            con.execute(
                f"""SELECT CSBID, county, year, acres, {best} AS g,
                (prev1 IN ({small}))::INT AS sg, (prev1 IN ({hay}))::INT AS hay
                FROM p WHERE now = {code} AND (prev1 = {partner} OR prev1 IN ({small}, {hay}))"""
            ).fetchnumpy()
        )
        cy = np.char.add(rows["county"].astype(str), rows["year"].astype(str))
        res = {"proxy": best, "slope": slopes[best]["log_yield_per_ndvi"]}
        for label, k in (("all", np.ones(len(rows["g"]), bool)), ("40ac+", rows["acres"] >= 40)):
            f_id = P.ids(rows["CSBID"][k])
            X = np.column_stack([rows["sg"][k], rows["hay"][k]]).astype(float)
            beta, se = P.fit(
                rows["g"][k].astype(float), X, [f_id, P.ids(cy[k])], P.ids(rows["county"][k])
            )
            entry = {"observations": int(k.sum())}
            for j, name in enumerate(("after_small_grain", "after_hay")):
                x = X[:, j]
                both = (np.bincount(f_id, x) * (np.bincount(f_id) - np.bincount(f_id, x)) > 0).sum()
                entry[name] = {
                    "yield_change_pct": round(100 * beta[j] * res["slope"], 2),
                    "se": round(100 * se[j] * abs(res["slope"]), 2),
                    "obs": int(x.sum()),
                    "fields_with_both": int(both),
                }
            res[label] = entry
        out[crop] = res
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
