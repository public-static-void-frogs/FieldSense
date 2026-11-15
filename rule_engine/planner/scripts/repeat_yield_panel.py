"""Do county yields fall when more of the county repeats a crop? A check of the rotation rules
against real yields, independent of the planner.

For every county and year 2019-2025: the share of corn acres that were corn the year before
(CDL, all CSB fields, by acres) and the same for soybeans, joined to the NASS county yield.
Regression of log yield on the repeat share with county and state x year fixed effects,
weighted by the crop's acres, standard errors clustered by county. County effects remove soil
and irrigation; state x year effects remove the year's weather and prices across the state.

Placebos: the soybean repeat share should not move corn yield, nor the corn share soybean yield.
CDL labels are satellite estimates; their errors push the coefficient toward zero.

    python rule_engine/planner/scripts/repeat_yield_panel.py \
        --cdl data/local/usa_sample_v3/cdl_history_all.parquet \
        --fields ../Field-Shift-NASA/data/local/usa_sample_v2/all_fields.csv \
        --yields data/local/usa_sample_v3/yields/nass_yield.parquet
"""

import argparse
import json

import duckdb
import numpy as np

CROPS = {"CORN": 1, "SOYBEANS": 5}
YEARS = range(2019, 2026)


def shares(con, cdl: str, fields: str):
    parts = []
    for year in YEARS:
        now, before, before2 = f"CDL{year}", f"CDL{year - 1}", f"CDL{year - 2}"
        three = (
            f"sum(a) FILTER ({now} = 1 AND {before} = 1 AND {before2} = 1)"
            if year - 2 >= 2018
            else "NULL"
        )
        parts.append(
            f"""SELECT county_fips, {year} AS year,
                sum(a) FILTER ({now} = 1) AS corn_acres,
                sum(a) FILTER ({now} = 1 AND {before} = 1) AS corn_after_corn,
                {three} AS corn_three,
                sum(a) FILTER ({now} = 5) AS soy_acres,
                sum(a) FILTER ({now} = 5 AND {before} = 5) AS soy_after_soy,
                sum(a) AS total_acres,
                sum(a) FILTER ({before} = 1) AS corn_prev,
                sum(a) FILTER ({before} = 5) AS soy_prev
            FROM j GROUP BY county_fips"""
        )
    con.execute(
        f"""CREATE TABLE j AS
        SELECT c.*, f.state_fips || f.county_fips AS county_fips, f.acres AS a
        FROM read_parquet('{cdl}') c
        JOIN read_csv('{fields}', all_varchar=true, types={{'acres': 'DOUBLE'}}) f
          ON f.source_id = c.CSBID"""
    )
    con.execute("CREATE TABLE s AS " + " UNION ALL ".join(parts))


def demean(x: np.ndarray, groups: list[np.ndarray], w: np.ndarray, rounds: int = 200):
    """Weighted residual of x on the fixed effects (alternating projections)."""
    x = x.copy()
    for _ in range(rounds):
        before = x.copy()
        for g in groups:
            sums = np.bincount(g, w * x)
            weights = np.bincount(g, w)
            x -= (sums / np.where(weights > 0, weights, 1))[g]
        if np.max(np.abs(x - before)) < 1e-10:
            break
    return x


def fit(rows: list[tuple], names: list[str]) -> dict:
    """rows: (county, state_year, weight, y, *regressors)."""
    county = np.unique([r[0] for r in rows], return_inverse=True)[1]
    state_year = np.unique([r[1] for r in rows], return_inverse=True)[1]
    w = np.array([r[2] for r in rows], dtype=float)
    y = np.array([r[3] for r in rows], dtype=float)
    X = np.array([r[4:] for r in rows], dtype=float)
    groups = [county, state_year]
    y_ = demean(y, groups, w)
    X_ = np.column_stack([demean(X[:, k], groups, w) for k in range(X.shape[1])])
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X_ * sw[:, None], y_ * sw, rcond=None)
    resid = y_ - X_ @ beta
    bread = np.linalg.inv((X_ * w[:, None]).T @ X_)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for c in np.unique(county):
        m = county == c
        score = (X_[m] * (w[m] * resid[m])[:, None]).sum(axis=0)
        meat += np.outer(score, score)
    n_c = len(np.unique(county))
    cov = bread @ meat @ bread * n_c / (n_c - 1)
    se = np.sqrt(np.diag(cov))
    return {
        "observations": len(rows),
        "counties": n_c,
        **{
            name: {"coef": round(float(b), 4), "se": round(float(s), 4)}
            for name, b, s in zip(names, beta, se)
        },
    }


def fit_iv(rows: list[tuple]) -> dict:
    """rows: (county, state_year, weight, y, x, control, instrument). 2SLS, one endogenous x."""
    county = np.unique([r[0] for r in rows], return_inverse=True)[1]
    state_year = np.unique([r[1] for r in rows], return_inverse=True)[1]
    w = np.array([r[2] for r in rows], dtype=float)
    cols = [
        demean(np.array([r[k] for r in rows], float), [county, state_year], w) for k in (3, 4, 5, 6)
    ]
    y, x, c, z = cols
    X, Z = np.column_stack([x, c]), np.column_stack([z, c])
    W = w[:, None]
    first, *_ = np.linalg.lstsq(Z * np.sqrt(W), x * np.sqrt(w), rcond=None)
    fitted = Z @ first
    first_resid = x - fitted
    sigma2 = np.sum(w * first_resid**2) / (len(rows) - 2)
    f_stat = first[0] ** 2 / (np.linalg.inv((Z * W).T @ Z)[0, 0] * sigma2)
    A = np.linalg.inv((Z * W).T @ X)
    beta = A @ ((Z * W).T @ y)
    resid = y - X @ beta
    meat = np.zeros((2, 2))
    for g in np.unique(county):
        m = county == g
        score = (Z[m] * (w[m] * resid[m])[:, None]).sum(axis=0)
        meat += np.outer(score, score)
    se = np.sqrt(np.diag(A @ meat @ A.T))
    return {
        "observations": len(rows),
        "repeat_share": {"coef": round(float(beta[0]), 4), "se": round(float(se[0]), 4)},
        "crop_share_control": {"coef": round(float(beta[1]), 4), "se": round(float(se[1]), 4)},
        "first_stage_f": round(float(f_stat), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cdl", required=True)
    parser.add_argument("--fields", required=True)
    parser.add_argument("--yields", required=True)
    parser.add_argument("--memory", default="4GB")
    parser.add_argument("--min-acres", type=float, default=2000.0)
    args = parser.parse_args()
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{args.memory}'; SET threads = 4")
    shares(con, args.cdl, args.fields)
    data = con.execute(
        f"""SELECT s.county_fips, s.year, s.corn_acres, s.soy_acres,
            coalesce(s.corn_after_corn, 0) / nullif(s.corn_acres, 0) AS cc,
            coalesce(s.corn_three, 0) / nullif(s.corn_acres, 0) AS ccc,
            coalesce(s.soy_after_soy, 0) / nullif(s.soy_acres, 0) AS ss,
            yc.yield_bu_acre AS corn_yield, ys.yield_bu_acre AS soy_yield,
            s.corn_acres / s.total_acres AS corn_now, s.corn_prev / s.total_acres AS corn_before,
            s.soy_acres / s.total_acres AS soy_now, s.soy_prev / s.total_acres AS soy_before
        FROM s
        LEFT JOIN read_parquet('{args.yields}') yc
          ON yc.county_fips = s.county_fips AND yc.year = s.year AND yc.crop = 'CORN'
        LEFT JOIN read_parquet('{args.yields}') ys
          ON ys.county_fips = s.county_fips AND ys.year = s.year AND ys.crop = 'SOYBEANS'"""
    ).fetchall()
    out = {}
    corn = [
        (c, c[:2] + str(y), ca, np.log(cy), cc, ss)
        for c, y, ca, sa, cc, ccc, ss, cy, sy, *_ in data
        if cy and ca and ca >= args.min_acres and sa and cc is not None and ss is not None
    ]
    soy = [
        (c, c[:2] + str(y), sa, np.log(sy), ss, cc)
        for c, y, ca, sa, cc, ccc, ss, cy, sy, *_ in data
        if sy and sa and sa >= args.min_acres and ca and cc is not None and ss is not None
    ]
    out["corn_yield"] = fit(corn, ["corn_after_corn_share", "placebo_soy_after_soy_share"])
    out["soy_yield"] = fit(soy, ["soy_after_soy_share", "placebo_corn_after_corn_share"])
    corn3 = [
        (c, c[:2] + str(y), ca, np.log(cy), cc - ccc, ccc)
        for c, y, ca, sa, cc, ccc, ss, cy, sy, *_ in data
        if cy and ca and ca >= args.min_acres and ccc is not None and y >= 2020
    ]
    out["corn_yield_by_run"] = fit(corn3, ["second_year_corn_share", "third_year_plus_corn_share"])
    # instrument: last year's crop share of the county's fields, set before this year's weather;
    # this year's share is a control (more corn reaches poorer land)
    iv_corn = [
        (c, c[:2] + str(y), ca, np.log(cy), cc, cn, cb)
        for c, y, ca, sa, cc, ccc, ss, cy, sy, cn, cb, sn, sb in data
        if cy and ca and ca >= args.min_acres and cc is not None and cb is not None
    ]
    iv_soy = [
        (c, c[:2] + str(y), sa, np.log(sy), ss, sn, sb)
        for c, y, ca, sa, cc, ccc, ss, cy, sy, cn, cb, sn, sb in data
        if sy and sa and sa >= args.min_acres and ss is not None and sb is not None
    ]
    out["corn_yield_iv"] = fit_iv(iv_corn)
    out["soy_yield_iv"] = fit_iv(iv_soy)
    # the variation left after the fixed effects: how far the share moves within a county
    for name, rows in (("corn", corn), ("soy", soy)):
        w = np.array([r[2] for r in rows])
        county = np.unique([r[0] for r in rows], return_inverse=True)[1]
        state_year = np.unique([r[1] for r in rows], return_inverse=True)[1]
        x = demean(np.array([r[4] for r in rows]), [county, state_year], w)
        out[f"{name}_share_within_sd"] = round(float(np.sqrt(np.average(x**2, weights=w))), 4)
        out[f"{name}_share_mean"] = round(float(np.average([r[4] for r in rows], weights=w)), 4)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
