"""Does a crop grown after itself do worse on the SAME field? A repeat-penalty test that removes
land quality: field fixed effects compare a field's repeat years with its own rotated years.

Panel: the sampled CSB fields, 2019-2023 (MODIS 16-day NDVI composites, CDL
2018-2023 for the crop and the crop before). Greenness of a field-year (season mean, peak, monthly windows)
is regressed on "same crop last year" and "same crop the two years before" with field and
county x year fixed effects, standard errors clustered by county. Soybeans after soybeans is the
known penalty and serves as the positive control for the method.

Greenness to yield: the county mean greenness of the crop's fields is set against log NASS county
yield with county and state x year effects; the slope turns a greenness change into a yield
change. MODIS pixels are 250 m, so small fields mix with their neighbours (toward zero); the test
is repeated on fields of 40 acres and more. CDL labels are satellite estimates.

    python rule_engine/planner/scripts/ndvi_field_panel.py --root data/local/usa_sample_v3 \
        --ndvi ../Field-Shift-NASA/data/local/planner/greenness/modis
"""

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repeat_yield_panel import demean  # noqa: E402

CROPS = {"corn": (1, "CORN"), "soybeans": (5, "SOYBEANS")}
# greenness of a field-year: day-of-year windows of the 16-day MODIS composites
WINDOWS = {
    "jun": (152, 181),
    "jul": (182, 212),
    "aug": (213, 243),
    "sep": (244, 273),
    "jul_aug": (182, 243),
    "jun_sep": (152, 273),
}
METRICS = ("season_mean", "peak", *WINDOWS)
YEARS = range(2019, 2024)


def plain(columns: dict) -> dict:
    """fetchnumpy gives masked arrays for nullable columns: numbers become float with NaN."""
    out = {}
    for key, value in columns.items():
        if isinstance(value, np.ma.MaskedArray):
            value = value.astype(float).filled(np.nan) if value.dtype.kind in "iuf" else value.data
        out[key] = np.asarray(value)
    return out


def ids(values) -> np.ndarray:
    return np.unique(values, return_inverse=True)[1]


def fit(y, X, groups, cluster, w=None) -> tuple[np.ndarray, np.ndarray]:
    w = np.ones(len(y)) if w is None else w
    y_ = demean(y, groups, w)
    X_ = np.column_stack([demean(X[:, k], groups, w) for k in range(X.shape[1])])
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X_ * sw[:, None], y_ * sw, rcond=None)
    resid = y_ - X_ @ beta
    bread = np.linalg.pinv((X_ * w[:, None]).T @ X_)
    order = np.argsort(cluster, kind="stable")
    bounds = np.flatnonzero(np.diff(cluster[order])) + 1
    scores = np.add.reduceat((X_ * (w * resid)[:, None])[order], np.r_[0, bounds], axis=0)
    n = len(bounds) + 1
    cov = bread @ (scores.T @ scores) @ bread * n / (n - 1)
    return beta, np.sqrt(np.maximum(np.diag(cov), 0))


def yield_slopes(con, yields: Path, code: int, nass: str) -> dict:
    """Per metric: log county yield on the county mean greenness of the crop's sampled fields,
    county and state x year effects, weighted by fields; slope and within R2."""
    means = ", ".join(f"avg(p.{m}) AS {m}" for m in METRICS)
    cy = plain(
        con.execute(
            f"""SELECT p.county, p.year, {means}, count(*) AS n, ln(y.yield_bu_acre) AS ly
            FROM p JOIN read_parquet('{yields}') y
              ON y.county_fips = p.county AND y.year = p.year AND y.crop = '{nass}'
            WHERE p.now = {code} AND y.yield_bu_acre > 0
            GROUP BY p.county, p.year, y.yield_bu_acre HAVING count(*) >= 10"""
        ).fetchnumpy()
    )
    county = ids(cy["county"])
    state_year = ids(np.char.add(cy["county"].astype("U2"), cy["year"].astype(str)))
    w = cy["n"].astype(float)
    ly = demean(cy["ly"].astype(float), [county, state_year], w)
    out = {}
    for m in METRICS:
        beta, se = fit(cy["ly"].astype(float), cy[m][:, None], [county, state_year], county, w=w)
        g = demean(cy[m].astype(float), [county, state_year], w)
        resid = ly - beta[0] * g
        out[m] = {
            "log_yield_per_ndvi": round(float(beta[0]), 3),
            "se": round(float(se[0]), 3),
            "within_r2": round(float(1 - np.sum(w * resid**2) / np.sum(w * ly**2)), 3),
            "county_years": len(ly),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--ndvi",
        required=True,
        type=Path,
        help="directory of <year>.parquet (field_id, date, ndvi)",
    )
    parser.add_argument("--yields", type=Path, help="default <root>/yields/nass_yield.parquet")
    parser.add_argument("--min-composites", type=int, default=10)
    args = parser.parse_args()
    root = args.root.resolve()
    yields = args.yields or root / "yields" / "nass_yield.parquet"
    con = duckdb.connect()
    con.execute("SET memory_limit = '4GB'; SET threads = 4")
    union = " UNION ALL ".join(
        f"SELECT CSBID, {y} AS year, CDL{y} AS now, CDL{y - 1} AS prev1, "
        f"{f'CDL{y - 2}' if y - 2 >= 2018 else 'NULL'} AS prev2 "
        f"FROM read_parquet('{root}/cdl_history_all.parquet')"
        for y in YEARS
    )
    files = ", ".join(f"'{args.ndvi}/{y}.parquet'" for y in YEARS)
    windows = ",\n".join(
        f"avg(ndvi) FILTER (dayofyear(date) BETWEEN {a} AND {b}) AS {k}"
        for k, (a, b) in WINDOWS.items()
    )
    con.execute(
        f"""CREATE TABLE n AS
        SELECT field_id, year(date) AS year, count(*) AS composites,
               avg(ndvi) AS season_mean, max(ndvi) AS peak, {windows}
        FROM read_parquet([{files}]) WHERE ndvi IS NOT NULL GROUP BY ALL"""
    )
    keep = " AND ".join(f"n.{m} IS NOT NULL" for m in METRICS)
    con.execute(
        f"""CREATE TABLE p AS
        WITH f AS (SELECT CSBID, STATEFIPS || CNTYFIPS AS county, CSBACRES::DOUBLE AS acres
                   FROM read_csv('{root}/fields.csv', all_varchar=true))
        SELECT c.*, f.county, f.acres, n.* EXCLUDE (field_id, year)
        FROM ({union}) c JOIN f USING (CSBID)
        JOIN n ON n.field_id = c.CSBID AND n.year = c.year
        WHERE c.now IN (1, 5) AND n.composites >= {args.min_composites}
          AND {keep} AND c.prev1 IS NOT NULL"""
    )
    slopes, best = {}, {}
    for crop, (code, nass) in CROPS.items():
        slopes[crop] = yield_slopes(con, yields, code, nass)
        # the greenness that best predicts the county yield stands in for yield
        best[crop] = max(METRICS, key=lambda m: slopes[crop][m]["within_r2"])
    out = {}
    for crop, (code, nass) in CROPS.items():
        rows = con.execute(
            f"""SELECT CSBID, county, year, acres, {", ".join(METRICS)},
                   (prev1 = {code})::INT AS repeat1,
                   CASE WHEN prev2 IS NULL THEN NULL
                        ELSE (prev1 = {code} AND prev2 = {code})::INT END AS repeat2
            FROM p WHERE now = {code}"""
        ).fetchnumpy()
        rows = plain(rows)
        field, county = rows["CSBID"], rows["county"]
        county_year = np.char.add(county.astype(str), rows["year"].astype(str))
        result = {}
        for label, keep in (("all", np.ones(len(field), bool)), ("40ac+", rows["acres"] >= 40)):
            # fields with both kinds of years are the ones that identify the effect
            f_id = ids(field[keep])
            rep = rows["repeat1"][keep].astype(float)
            both = np.bincount(f_id, rep) * (np.bincount(f_id) - np.bincount(f_id, rep)) > 0
            for metric in METRICS:
                y = rows[metric][keep].astype(float)
                X = rep[:, None]
                beta, se = fit(y, X, [f_id, ids(county_year[keep])], ids(county[keep]))
                result[f"{label}/{metric}"] = {
                    "repeat": round(float(beta[0]), 5),
                    "se": round(float(se[0]), 5),
                    "mean": round(float(y.mean()), 4),
                    "observations": int(keep.sum()),
                    "fields_with_both": int(both.sum()),
                }
            # second repeat year on top of the first, where two years back are known
            k2 = keep & ~np.isnan(rows["repeat2"].astype(float))
            X2 = np.column_stack([rows["repeat1"][k2], rows["repeat2"][k2]]).astype(float)
            beta, se = fit(
                rows[best[crop]][k2].astype(float),
                X2,
                [ids(field[k2]), ids(county_year[k2])],
                ids(county[k2]),
            )
            result[f"{label}/by_run ({best[crop]})"] = {
                "second_year": [round(float(beta[0]), 5), round(float(se[0]), 5)],
                "third_year_extra": [round(float(beta[1]), 5), round(float(se[1]), 5)],
                "observations": int(k2.sum()),
            }
        for label in ("all", "40ac+"):
            for metric in METRICS:
                r = result[f"{label}/{metric}"]
                slope = slopes[crop][metric]["log_yield_per_ndvi"]
                r["yield_change_pct"] = round(100 * r["repeat"] * slope, 2)
                r["yield_change_se"] = round(100 * r["se"] * abs(slope), 2)
        result["yield_proxy"] = slopes[crop]
        result["best_proxy"] = best[crop]
        out[crop] = result
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
