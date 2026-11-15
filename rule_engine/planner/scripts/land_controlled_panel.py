"""The county repeat-yield panel of repeat_yield_panel.py with the land held fixed.

County fixed effects in that panel remove the soil a county always has. What they cannot remove
is the land that changes crop from year to year: in a year when a county grows more corn after
corn, its corn (and its soybeans) may sit on better or poorer fields than usual. Three ways to
take that out:

  1. Land control. For every county and year, the soil quality of the acres in corn and in
     soybeans that year: the mean NCCPI (NRCS National Commodity Crop Productivity Index,
     SSURGO) of the sampled CSB fields growing the crop, weighted by the CSB fields and acres
     each sampled field stands for. Added as a regressor (free slope), or as an offset with the
     slope soil_level.py measured between counties (corn 0.44, soybeans 0.48 per index unit).
  2. Other-crop control. The county's yield of the other crop the same year: whatever lifts
     both crops (land, local weather, management) shows in it. Corn after corn cannot change a
     soybean yield, so it does not absorb the effect being measured.
  3. Direct size. Within a county and year, how much better the corn-after-corn fields' soil is
     than the soil of corn after another crop, and the yield that difference alone is worth.

Placebos as before: the soybean repeat share should not move corn yield, nor the corn share
soybean yield. CDL labels are satellite estimates; their errors push the coefficients to zero.

    python rule_engine/planner/scripts/land_controlled_panel.py \
        --cdl data/local/usa_sample_v3/cdl_history_all.parquet \
        --fields ../Field-Shift-NASA/data/local/usa_sample_v2/all_fields.csv \
        --yields data/local/usa_sample_v3/yields/nass_yield.parquet \
        --sample data/local/usa_sample_v3/fields.csv \
        --soil data/local/usa_sample_v3/soil_base.parquet \
        --soil-extra data/local/usa_sample_v3/soil_extra.csv \
        --weights cell_weights.parquet
"""

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repeat_yield_panel import YEARS, demean, fit, shares  # noqa: E402

SLOPE = {"corn": 0.44, "soy": 0.48}  # soil_level.py


def land(con, sample: str, soil: str, extra: str, weights: str) -> None:
    """Table l: per county and year, the NCCPI of the sampled acres in corn and in soybeans."""
    con.execute(
        f"""CREATE TABLE f AS
        WITH x AS (
            SELECT f.CSBID, f.STATEFIPS || f.CNTYFIPS AS county_fips, f.ix::INT AS ix,
                   f.iy::INT AS iy, f.CSBACRES::DOUBLE AS acres, e.nccpi_corn, e.nccpi_soy
            FROM read_csv('{sample}', all_varchar=true) f
            JOIN read_parquet('{soil}') s USING (CSBID)
            JOIN read_csv('{extra}') e ON e.mukey::VARCHAR = s.mukey::VARCHAR
            WHERE e.nccpi_corn IS NOT NULL AND e.nccpi_soy IS NOT NULL
        ),
        k AS (SELECT county_fips, ix, iy, count(*) AS sampled FROM x GROUP BY ALL)
        SELECT x.*, w.n / k.sampled * x.acres AS w, c.* EXCLUDE (CSBID)
        FROM x JOIN k USING (county_fips, ix, iy)
        JOIN read_parquet('{weights}') w USING (county_fips, ix, iy)
        JOIN j0 c ON c.CSBID = x.CSBID"""
    )
    parts = []
    for year in YEARS:
        now, before = f"CDL{year}", f"CDL{year - 1}"

        def mean(index, cond):
            return f"sum(w * {index}) FILTER ({cond}) / nullif(sum(w) FILTER ({cond}), 0)"

        parts.append(
            f"""SELECT county_fips, {year} AS year,
                {mean("nccpi_corn", f"{now} = 1")} AS corn_land,
                {mean("nccpi_soy", f"{now} = 5")} AS soy_land,
                {mean("nccpi_corn", f"{now} = 1 AND {before} = 1")} AS cc_land,
                {mean("nccpi_corn", f"{now} = 1 AND {before} <> 1")} AS co_land,
                {mean("nccpi_soy", f"{now} = 5 AND {before} = 5")} AS ss_land,
                {mean("nccpi_soy", f"{now} = 5 AND {before} <> 5")} AS so_land,
                sum(w) FILTER ({now} = 1 AND {before} = 1) AS cc_w,
                sum(w) FILTER ({now} = 5 AND {before} = 5) AS ss_w,
                count(*) FILTER ({now} = 1) AS corn_n, count(*) FILTER ({now} = 5) AS soy_n
            FROM f GROUP BY county_fips"""
        )
    con.execute("CREATE TABLE l AS " + " UNION ALL ".join(parts))


def gap(rows, a: int, b: int, weight: int) -> dict:
    """Weighted mean of rows[a] - rows[b] (the soil gap), with a county-clustered error."""
    rows = [r for r in rows if r[a] is not None and r[b] is not None and r[weight]]
    d = np.array([r[a] - r[b] for r in rows])
    w = np.array([r[weight] for r in rows], float)
    county = np.unique([r[0] for r in rows], return_inverse=True)[1]
    mean = float(np.average(d, weights=w))
    scores = np.bincount(county, w * (d - mean)) / w.sum()
    return {"index_gap": round(mean, 4), "se": round(float(np.sqrt((scores**2).sum())), 4),
            "county_years": len(rows)}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("cdl", "fields", "yields", "sample", "soil", "soil-extra", "weights"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--memory", default="6GB")
    parser.add_argument("--min-acres", type=float, default=2000.0)
    parser.add_argument("--min-sampled", type=int, default=10, help="sampled fields per crop")
    args = parser.parse_args()
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{args.memory}'; SET threads = 4")
    con.execute(f"CREATE VIEW j0 AS SELECT * FROM read_parquet('{args.cdl}')")
    land(con, args.sample, args.soil, args.soil_extra, args.weights)
    shares(con, args.cdl, args.fields)
    data = con.execute(
        f"""SELECT s.county_fips, s.year, s.corn_acres, s.soy_acres,
            coalesce(s.corn_after_corn, 0) / nullif(s.corn_acres, 0) AS cc,
            coalesce(s.soy_after_soy, 0) / nullif(s.soy_acres, 0) AS ss,
            yc.yield_bu_acre AS corn_yield, ys.yield_bu_acre AS soy_yield,
            l.corn_land, l.soy_land, l.corn_n, l.soy_n,
            l.cc_land, l.co_land, l.ss_land, l.so_land, l.cc_w, l.ss_w
        FROM s JOIN l USING (county_fips, year)
        LEFT JOIN read_parquet('{args.yields}') yc
          ON yc.county_fips = s.county_fips AND yc.year = s.year AND yc.crop = 'CORN'
        LEFT JOIN read_parquet('{args.yields}') ys
          ON ys.county_fips = s.county_fips AND ys.year = s.year AND ys.crop = 'SOYBEANS'"""
    ).fetchall()
    keys = ["county", "year", "corn_acres", "soy_acres", "cc", "ss", "cy", "sy", "corn_land",
            "soy_land", "corn_n", "soy_n", "cc_land", "co_land", "ss_land", "so_land", "cc_w",
            "ss_w"]  # fmt: skip
    data = [dict(zip(keys, r)) for r in data]
    ok = [
        d
        for d in data
        if d["cy"] and d["sy"] and d["cc"] is not None and d["ss"] is not None
        and d["corn_land"] is not None and d["soy_land"] is not None
        and d["corn_n"] >= args.min_sampled and d["soy_n"] >= args.min_sampled
    ]  # fmt: skip
    corn = [d for d in ok if d["corn_acres"] >= args.min_acres]
    soy = [d for d in ok if d["soy_acres"] >= args.min_acres]

    def rows(sel, crop, y, *cols):
        w = "corn_acres" if crop == "corn" else "soy_acres"
        return [(d["county"], d["county"][:2] + str(d["year"]), d[w], y(d), *[c(d) for c in cols])
                for d in sel]  # fmt: skip

    def log_y(key):
        return lambda d: np.log(d[key])

    def offset(key, land_key, crop):
        return lambda d: np.log(d[key]) - np.log(1 + SLOPE[crop] * d[land_key])

    def col(key):
        return lambda d: d[key]

    out = {"sampled_fields_min": args.min_sampled}
    corn_names = ["corn_after_corn_share", "placebo_soy_after_soy_share"]
    soy_names = ["soy_after_soy_share", "placebo_corn_after_corn_share"]
    out["corn_no_land_control"] = fit(rows(corn, "corn", log_y("cy"), col("cc"), col("ss")),
                                      corn_names)  # fmt: skip
    out["corn_land_control"] = fit(
        rows(corn, "corn", log_y("cy"), col("cc"), col("ss"), col("corn_land")),
        corn_names + ["corn_land_nccpi"],
    )
    out["corn_land_offset"] = fit(
        rows(corn, "corn", offset("cy", "corn_land", "corn"), col("cc"), col("ss")), corn_names
    )
    out["corn_soy_yield_control"] = fit(
        rows(corn, "corn", log_y("cy"), col("cc"), col("ss"), col("corn_land"), log_y("sy")),
        corn_names + ["corn_land_nccpi", "log_soy_yield"],
    )
    out["soy_no_land_control"] = fit(rows(soy, "soy", log_y("sy"), col("ss"), col("cc")),
                                     soy_names)  # fmt: skip
    out["soy_land_control"] = fit(
        rows(soy, "soy", log_y("sy"), col("ss"), col("cc"), col("soy_land")),
        soy_names + ["soy_land_nccpi"],
    )
    out["soy_land_offset"] = fit(
        rows(soy, "soy", offset("sy", "soy_land", "soy"), col("ss"), col("cc")), soy_names
    )
    out["soy_corn_yield_control"] = fit(
        rows(soy, "soy", log_y("sy"), col("ss"), col("cc"), col("soy_land"), log_y("cy")),
        soy_names + ["soy_land_nccpi", "log_corn_yield"],
    )
    # 3. how much better the repeat fields' soil is, and the yield that is worth
    as_rows = [tuple(d[k] for k in keys) for d in data]
    ix = {k: i for i, k in enumerate(keys)}
    for name, a, b, w, crop in (("corn_after_corn", "cc_land", "co_land", "cc_w", "corn"),
                                ("soy_after_soy", "ss_land", "so_land", "ss_w", "soy")):  # fmt: skip
        g = gap(as_rows, ix[a], ix[b], ix[w])
        g["yield_pct_from_soil"] = round(100 * SLOPE[crop] * g["index_gap"], 2)
        out[f"{name}_soil_gap"] = g
    # how far the land of the crop's acres moves within a county (after both fixed effects)
    for name, sel, key, weight in (("corn", corn, "corn_land", "corn_acres"),
                                   ("soy", soy, "soy_land", "soy_acres")):  # fmt: skip
        w = np.array([d[weight] for d in sel], float)
        county = np.unique([d["county"] for d in sel], return_inverse=True)[1]
        state_year = np.unique([d["county"][:2] + str(d["year"]) for d in sel],
                               return_inverse=True)[1]  # fmt: skip
        x = demean(np.array([d[key] for d in sel], float), [county, state_year], w)
        out[f"{name}_land_within_sd"] = round(float(np.sqrt(np.average(x**2, weights=w))), 4)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
