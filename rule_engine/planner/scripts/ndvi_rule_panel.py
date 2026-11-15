"""Same-field MODIS greenness test of the rule engine's crop-sequence yield rules other than corn
and soybeans (take-all, peanuts, potatoes, sugarbeets, pulses).

Panel: the sampled CSB fields, 2019-2023, the crop and the two crops before it from CDL
2018-2023. Each test compares a field's years in the rule's sequence ("treated") with its own
years in a comparison sequence. The greenness of a field-year is the mean NDVI of the 16-day
composites in the crop's main growing window. It is regressed on the treated flag with field and
county x year fixed effects, and standard errors are clustered by county. Soybeans after
soybeans is the positive control. Fields of 40 acres and more are reported separately, because
250 m pixels mix small fields with their neighbours.

Greenness to yield: for each crop, log NASS county yield is regressed on the county mean window
greenness of its sampled fields, with county and state x year effects, weighted by fields. The
slope times the greenness change is the canopy's yield floor. For soybeans after soybeans it
gives about a twelfth of the trial loss (Seifert et al. 2017), so a floor is a lower bound on
the loss and the direction is what the test checks. NASS publishes no county yields for
sugarbeets or potatoes. CDL labels are satellite estimates, not what the farmer declared.

    python rule_engine/planner/scripts/ndvi_rule_panel.py --root data/local/usa_sample_v3 \
        --ndvi ../Field-Shift-NASA/data/local/planner/greenness/modis

The small-grain and peanut county yields are fetched from Quick Stats on the first run (needs
USDA_DATA_KEY in .env or the environment) and cached in <root>/yields/nass_rule_crops.parquet.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "rule_engine" / "scripts"))
from fetch_nass_reference import API, _key  # noqa: E402
from ndvi_field_panel import fit, ids, plain  # noqa: E402

YEARS = range(2019, 2024)
HOSTS = "(21,22,23,24,27,205,26,225,236,237,238,254)"  # take-all host cereals and their doubles
PULSES = "(51,52,53)"  # chickpeas, lentils, peas
BROADLEAF = "(5,6,31,41,42,52,53)"
FALLOW = 61
# day-of-year window of each crop's main growth
WINDOWS = {
    "soybeans": (182, 243),
    "winter_wheat": (91, 151),
    "spring_small": (166, 212),
    "peanuts": (196, 258),
    "potatoes": (182, 227),
    "sugarbeets": (196, 258),
    "pulses": (152, 196),
}
# CDL code: (NASS county yield series, window); None where NASS has no county series
CROPS = {
    5: ("SOYBEANS", "soybeans"),
    24: ("WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE", "winter_wheat"),
    23: ("WHEAT, SPRING, (EXCL DURUM) - YIELD, MEASURED IN BU / ACRE", "spring_small"),
    22: ("WHEAT, SPRING, DURUM - YIELD, MEASURED IN BU / ACRE", "spring_small"),
    21: ("BARLEY - YIELD, MEASURED IN BU / ACRE", "spring_small"),
    10: ("PEANUTS - YIELD, MEASURED IN LB / ACRE", "peanuts"),
}
NAMES = {
    5: "soybeans",
    24: "winter wheat",
    23: "spring wheat",
    22: "durum",
    21: "barley",
    10: "peanuts",
}
OTHER = f"p1 NOT IN {HOSTS} AND p1 <> {FALLOW}"
# name: (rule id, crop now, window, treated, comparison)
TESTS = {
    "soybeans after soybeans (control)": (
        "soy_after_soy_yield_penalty", "now = 5", "soybeans", "p1 = 5", "p1 <> 5"),
    "winter wheat after a host vs a non-host": (
        "take_all_second_cereal", "now = 24", "winter_wheat", f"p1 IN {HOSTS}", OTHER),
    "winter wheat after a host vs early-harvested non-hosts": (
        "take_all_second_cereal", "now = 24", "winter_wheat", f"p1 IN {HOSTS}",
        "p1 IN (28,31,52,53)"),
    "winter wheat after a host vs soybeans": (
        None, "now = 24", "winter_wheat", f"p1 IN {HOSTS}", "p1 = 5"),
    "winter wheat after a host vs sorghum": (
        None, "now = 24", "winter_wheat", f"p1 IN {HOSTS}", "p1 = 4"),
    "winter wheat after fallow vs a non-host": (
        None, "now = 24", "winter_wheat", f"p1 = {FALLOW}", OTHER),
    "spring wheat after a host vs a non-host": (
        "take_all_second_cereal", "now = 23", "spring_small", f"p1 IN {HOSTS}", OTHER),
    "spring wheat after wheat or barley vs a broadleaf": (
        "take_all_second_cereal", "now = 23", "spring_small", "p1 IN (21,22,23,24,27,205)",
        f"p1 IN {BROADLEAF}"),
    "spring wheat after oats vs a broadleaf (oats host no take-all)": (
        None, "now = 23", "spring_small", "p1 = 28", f"p1 IN {BROADLEAF}"),
    "spring wheat after corn vs a broadleaf": (
        None, "now = 23", "spring_small", "p1 = 1", f"p1 IN {BROADLEAF}"),
    "durum after a host vs a non-host": (
        "take_all_second_cereal", "now = 22", "spring_small", f"p1 IN {HOSTS}", OTHER),
    "barley after a host vs a non-host": (
        "take_all_second_cereal", "now = 21", "spring_small", f"p1 IN {HOSTS}", OTHER),
    "barley after wheat or barley vs a broadleaf": (
        "take_all_second_cereal", "now = 21", "spring_small", "p1 IN (21,22,23,24,27,205)",
        f"p1 IN {BROADLEAF}"),
    "peanuts after peanuts": (
        "peanut_after_peanut", "now = 10", "peanuts", "p1 = 10",
        "p1 <> 10 AND p2 IS NOT NULL AND p2 <> 10"),
    "peanuts after a one-year break": (
        "peanut_one_year_break", "now = 10", "peanuts", "p1 <> 10 AND p2 = 10",
        "p1 <> 10 AND p2 IS NOT NULL AND p2 <> 10"),
    "potatoes within two years": (
        "potato_short_rotation", "now = 43 AND p2 IS NOT NULL", "potatoes",
        "p1 = 43 OR p2 = 43", "p1 <> 43 AND p2 <> 43"),
    "sugarbeets after sugarbeets": (
        "sugarbeet_after_sugarbeet", "now = 41", "sugarbeets", "p1 = 41",
        "p1 <> 41 AND p2 IS NOT NULL AND p2 <> 41"),
    "sugarbeets after a one-year break": (
        "sugarbeet_one_year_break", "now = 41", "sugarbeets", "p1 <> 41 AND p2 = 41",
        "p1 <> 41 AND p2 IS NOT NULL AND p2 <> 41"),
    "peas or lentils after a pulse": (
        "pulse_after_pulse", "now IN (52,53)", "pulses", f"p1 IN {PULSES}",
        f"p1 NOT IN {PULSES} AND p2 IS NOT NULL AND p2 <> now"),
    "peas or lentils after a one-year break": (
        "pea_lentil_one_year_break", "now IN (52,53)", "pulses",
        f"p1 NOT IN {PULSES} AND p2 = now",
        f"p1 NOT IN {PULSES} AND p2 IS NOT NULL AND p2 <> now"),
}  # fmt: skip


def fetch_yields(out: Path) -> None:
    """NASS survey county yields, 2019-2023, of the crops in CROPS other than soybeans."""
    key, rows = _key(), []
    for code, (series, _) in CROPS.items():
        if " - YIELD" not in series:
            continue
        for year in YEARS:
            query = {
                "key": key,
                "format": "JSON",
                "source_desc": "SURVEY",
                "agg_level_desc": "COUNTY",
                "short_desc": series,
                "year": str(year),
                "reference_period_desc": "YEAR",
            }
            try:
                with urllib.request.urlopen(
                    f"{API}?{urllib.parse.urlencode(query)}", timeout=300
                ) as resp:
                    data = json.load(resp)["data"]
            except urllib.error.HTTPError:  # Quick Stats answers 400 when nothing matches
                continue
            for r in data:
                value = r["Value"].replace(",", "").strip()
                if r["county_code"] in ("", "998") or not value.replace(".", "").isdigit():
                    continue
                rows.append((code, year, r["state_fips_code"] + r["county_code"], float(value)))
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["code", "year", "county_fips", "yield"]).to_parquet(out)


def slopes(con, min_fields: int) -> dict:
    """Per CDL code: log county yield per 1 % of window greenness."""
    out = {}
    for code, (_, window) in CROPS.items():
        a, b = WINDOWS[window]
        for minimum in (min_fields, 5):
            d = plain(
                con.execute(
                    f"""WITH g AS (
                          SELECT n.CSBID, n.year, avg(n.ndvi) FILTER (n.doy BETWEEN {a} AND {b}) g
                          FROM n JOIN p USING (CSBID, year) WHERE p.now = {code} GROUP BY ALL)
                        SELECT p.county, p.year, avg(g.g) g, count(*) k, ln(y.yield) ly
                        FROM g JOIN p USING (CSBID, year)
                        JOIN y ON y.code = {code} AND y.year = p.year AND y.county_fips = p.county
                        WHERE g.g IS NOT NULL AND y.yield > 0
                        GROUP BY p.county, p.year, y.yield HAVING count(*) >= {minimum}"""
                ).fetchnumpy()
            )
            if len(d["g"]) >= 30:
                break
        if len(d["g"]) < 30:
            out[code] = {"county_years": len(d["g"])}
            continue
        w = d["k"].astype(float)
        county = ids(d["county"])
        groups = [county, ids(np.char.add(d["county"].astype("U2"), d["year"].astype(str)))]
        beta, se = fit(d["ly"].astype(float), d["g"].astype(float)[:, None], groups, county, w=w)
        mean = float(np.average(d["g"], weights=w))
        out[code] = {
            "log_yield_per_pct": round(float(beta[0]) * mean / 100, 4),
            "se": round(float(se[0]) * mean / 100, 4),
            "county_years": len(d["g"]),
            "min_fields": minimum,
        }
    return out


def test(con, crop: str, window: str, treated: str, control: str) -> dict:
    a, b = WINDOWS[window]
    r = plain(
        con.execute(
            f"""WITH x AS (SELECT CSBID, year, county, acres, ({treated})::INT t FROM p
                           WHERE {crop} AND (({treated}) OR ({control}))),
                 g AS (SELECT CSBID, year, avg(ndvi) FILTER (doy BETWEEN {a} AND {b}) g,
                              count(*) FILTER (doy BETWEEN {a} AND {b}) k
                       FROM n JOIN (SELECT DISTINCT CSBID FROM x) USING (CSBID) GROUP BY ALL)
            SELECT x.*, g.g FROM x JOIN g USING (CSBID, year) WHERE g.k >= 2 AND g.g IS NOT NULL"""
        ).fetchnumpy()
    )
    out = {}
    for label, keep in (("all", np.ones(len(r["t"]), bool)), ("40ac+", r["acres"] >= 40)):
        field, t = ids(r["CSBID"][keep]), r["t"][keep].astype(float)
        both = int(((np.bincount(field, t) > 0) & (np.bincount(field, 1 - t) > 0)).sum())
        if both < 20:  # too few fields to compare within
            out[label] = {"fields_with_both": both}
            continue
        y = r["g"][keep].astype(float)
        county = ids(r["county"][keep])
        county_year = ids(np.char.add(r["county"][keep].astype(str), r["year"][keep].astype(str)))
        beta, se = fit(y, t[:, None], [field, county_year], county)
        base = float(y[t == 0].mean())
        out[label] = {
            "pct": round(100 * float(beta[0]) / base, 2),
            "se_pct": round(100 * float(se[0]) / base, 2),
            "observations": int(keep.sum()),
            "treated": int(t.sum()),
            "fields_with_both": both,
            "counties": int(county.max() + 1),
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
    parser.add_argument("--min-fields", type=int, default=10, help="per county-year, for slopes")
    args = parser.parse_args()
    root = args.root.resolve()
    crop_yields = root / "yields" / "nass_rule_crops.parquet"
    if not crop_yields.exists():
        fetch_yields(crop_yields)
    con = duckdb.connect()
    con.execute("SET memory_limit = '8GB'; SET threads = 6")
    union = " UNION ALL ".join(
        f"SELECT CSBID, {y} AS year, CDL{y} AS now, CDL{y - 1} AS p1, "
        f"{f'CDL{y - 2}' if y - 2 >= 2018 else 'NULL'} AS p2 "
        f"FROM read_parquet('{root}/cdl_history_all.parquet')"
        for y in YEARS
    )
    con.execute(
        f"""CREATE TABLE p AS
        WITH f AS (SELECT CSBID, STATEFIPS || CNTYFIPS AS county, CSBACRES::DOUBLE AS acres
                   FROM read_csv('{root}/fields.csv', all_varchar=true))
        SELECT c.*, f.county, f.acres FROM ({union}) c JOIN f USING (CSBID)
        WHERE c.p1 IS NOT NULL"""
    )
    files = ", ".join(f"'{args.ndvi}/{y}.parquet'" for y in YEARS)
    con.execute(
        f"""CREATE TABLE n AS SELECT field_id AS CSBID, year(date) AS year,
               dayofyear(date) AS doy, ndvi
        FROM read_parquet([{files}]) WHERE ndvi IS NOT NULL"""
    )
    con.execute(
        f"""CREATE TABLE y AS
        SELECT code, year, county_fips, "yield" FROM read_parquet('{crop_yields}')
        UNION ALL SELECT 5, year, county_fips, yield_bu_acre
        FROM read_parquet('{root}/yields/nass_yield.parquet')
        WHERE crop = 'SOYBEANS' AND year BETWEEN {YEARS[0]} AND {YEARS[-1]}"""
    )
    slope = slopes(con, args.min_fields)
    out = {"log_yield_per_pct_greenness": {NAMES[c]: s for c, s in slope.items()}}
    for name, (rule, crop, window, treated, control) in TESTS.items():
        result = {"rule": rule, **test(con, crop, window, treated, control)}
        code = int(crop.split("=")[1].split()[0]) if crop.startswith("now =") else None
        s = slope.get(code, {}).get("log_yield_per_pct")
        for label in ("all", "40ac+"):
            r = result[label]
            if s is not None and "pct" in r:
                r["yield_floor_pct"] = round(100 * r["pct"] * s, 2)
                r["yield_floor_se"] = round(100 * r["se_pct"] * s, 2)
        out[name] = result
        print(name, result["all"], flush=True)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
