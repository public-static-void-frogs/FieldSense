"""Do the weather-hazard rules hold outside the Corn Belt? A county-year test by ERS farm resource
region.

The rules' thresholds (a day of 35 C at flowering, a -2 C frost after emergence, ...) were written
for the Corn Belt. For each hazard rule and each crop it applies to that has NASS county yields,
this script asks, region by region:

- how often the rule fires: the hazard is evaluated as the engine does it (stage day from the
  state calendar, window, weekly metric, aggregate, threshold) on every sampled field's season
  summary, and the share of seasons hit gives the level a field would see (0.1 reported, 0.25
  medium, 0.5 high);
- whether a hit costs yield: log NASS county yield on the share of the county's sampled fields
  hit that year, with county fixed effects and state quadratic trends, standard errors clustered
  by year (one weather year hits many counties at once). The coefficient is the yield change
  when every field of the county is hit.

Season summaries hold the weeks from day 91 (1 April) to day 307; temperature and rain from
1981, the Drought Monitor from 2000, SMAP root-zone moisture from 2015. County yields mix
irrigated and dryland fields, so a hazard that irrigation removes shows less loss where much of
the crop is irrigated (the Plains, the West, the Delta). The "dryland" row repeats the test on
the counties where under 10 % of the crop's harvested acres are irrigated
(rule_engine/data/county_irrigated_share.csv; a county or crop without a Census row counts as
dryland). CDL labels are not used: every sampled field of a county counts, whatever it grew.

rule_engine/scripts/build_hazard_yield_loss.py turns <dir>/result.json into the loss table the
engine sets risk levels from.

    python rule_engine/planner/scripts/regional_hazard_panel.py --root data/local/usa_sample_v3 \
        --out <dir>

Needs USDA_DATA_KEY on the first run, to fetch county yields of the crops other than corn and
soybeans into <root>/yields/nass_county_crops.parquet. Writes <dir>/exposure.parquet (county,
year, rule, crop, share of fields hit), <dir>/levels.parquet (per field, rule and crop: seasons,
hits) and prints the results as JSON.
"""

import argparse
import csv
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
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rule_engine" / "scripts"))
from fetch_nass_reference import API, _key  # noqa: E402
from rule_engine.catalog import load_catalog  # noqa: E402
from rule_engine.reference import load_reference  # noqa: E402
from rule_engine.rules import applies, load_rules  # noqa: E402
from rule_engine.summary import WEEK0_DOY, WEEKS  # noqa: E402

REGIONS = ROOT / "rule_engine" / "planner" / "data" / "ers_regions.csv"
STATE_CROPS = ROOT / "rule_engine" / "data" / "state_crops.csv"
IRRIGATED = ROOT / "rule_engine" / "data" / "county_irrigated_share.csv"
DRYLAND_BELOW = 0.1  # share of the crop's harvested acres irrigated
YEARS = range(1981, 2026)
LEVEL_YEARS = range(1996, 2026)  # the engine counts weather hazards over its 1996-2025 record
SERIES = {  # catalog crop: NASS county yield series (corn and soybeans: nass_yield.parquet)
    "sorghum": "SORGHUM, GRAIN - YIELD, MEASURED IN BU / ACRE",
    "winter_wheat": "WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE",
    "spring_wheat": "WHEAT, SPRING, (EXCL DURUM) - YIELD, MEASURED IN BU / ACRE",
    "durum_wheat": "WHEAT, SPRING, DURUM - YIELD, MEASURED IN BU / ACRE",
    "barley": "BARLEY - YIELD, MEASURED IN BU / ACRE",
    "oats": "OATS - YIELD, MEASURED IN BU / ACRE",
    "cotton": "COTTON, UPLAND - YIELD, MEASURED IN LB / ACRE",
    "peanuts": "PEANUTS - YIELD, MEASURED IN LB / ACRE",
    "rice": "RICE - YIELD, MEASURED IN LB / ACRE",
    "sunflower": "SUNFLOWER - YIELD, MEASURED IN LB / ACRE",
    "canola": "CANOLA - YIELD, MEASURED IN LB / ACRE",
}
STATE_ALPHA = dict(
    zip(
        "01 04 05 06 08 09 10 12 13 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 "
        "36 37 38 39 40 41 42 44 45 46 47 48 49 50 51 53 54 55 56".split(),
        "AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM "
        "NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(),
        strict=True,
    )
)


def fetch_yields(out: Path) -> None:
    key, rows = _key(), []
    for crop, series in SERIES.items():
        for start in range(YEARS[0], YEARS[-1] + 1, 5):
            query = {
                "key": key,
                "format": "JSON",
                "source_desc": "SURVEY",
                "agg_level_desc": "COUNTY",
                "short_desc": series,
                "reference_period_desc": "YEAR",
                "year__GE": str(start),
                "year__LE": str(min(start + 4, YEARS[-1])),
            }
            try:
                with urllib.request.urlopen(
                    f"{API}?{urllib.parse.urlencode(query)}", timeout=600
                ) as resp:
                    data = json.load(resp)["data"]
            except urllib.error.HTTPError:  # 400 when nothing matches
                continue
            for r in data:
                value = r["Value"].replace(",", "").strip()
                if r["county_code"] in ("", "998") or not value.replace(".", "").isdigit():
                    continue
                rows.append(
                    (crop, int(r["year"]), r["state_fips_code"] + r["county_code"], float(value))
                )
            print(crop, start, len(data), file=sys.stderr, flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["crop", "year", "county_fips", "yield"]).to_parquet(out)


def windows() -> pd.DataFrame:
    """One row per (state, crop, hazard rule): the weekly bins the engine reads, as it reads them."""
    catalog, rules, reference = load_catalog(), load_rules(), load_reference()
    with STATE_CROPS.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    state_key = next(k for k in rows[0] if k in ("state", "region", "state_alpha"))
    crop_key = next(k for k in rows[0] if k in ("crop", "crop_id"))
    by_state: dict[str, set[str]] = {}
    for r in rows:
        by_state.setdefault(r[state_key], set()).add(r[crop_key])
    out = []
    for rule in rules.rules:
        h = rule.hazard
        if h is None:
            continue
        for state, crops in by_state.items():
            for crop_id in sorted(crops & ({"corn", "soybeans"} | set(SERIES))):
                crop = catalog.crops[crop_id]
                if not applies(rule, crop, catalog):
                    continue
                calendar = reference.calendar(crop, state)
                doy = calendar.stages.get(h.stage)
                if doy is None:
                    continue
                start, end = doy + h.window_days[0], doy + h.window_days[1]
                first = max(0, (start - WEEK0_DOY) // 7)
                last = min(WEEKS - 1, (end - WEEK0_DOY) // 7)
                if last < first:
                    continue
                out.append(
                    {
                        "state": state,
                        "crop": crop_id,
                        "rule": rule.id,
                        "metric": h.metric,
                        "agg": h.aggregate,
                        "compare": h.compare,
                        "threshold": float(h.threshold),
                        "first": first,
                        "last": last,
                        "calendar": calendar.kind,
                    }
                )
    return pd.DataFrame(out)


def exposure(con, root: Path, win: pd.DataFrame, out: Path) -> None:
    con.register("win_df", win)
    con.execute("CREATE OR REPLACE TABLE win AS SELECT * FROM win_df")
    metrics = sorted(win.metric.unique())
    con.execute(
        "CREATE OR REPLACE TABLE fips_state AS SELECT * FROM (VALUES "
        + ", ".join(f"('{f}', '{s}')" for f, s in STATE_ALPHA.items())
        + ") t(fips, state)"
    )
    con.execute(
        "CREATE OR REPLACE TABLE levels (csbid VARCHAR, county VARCHAR, rule VARCHAR, "
        "crop VARCHAR, seasons INT, hits INT)"
    )
    parts = []
    for year in YEARS:
        cols = ", ".join(metrics)
        value = " ".join(
            f"WHEN w.metric = '{m}' AND w.agg = '{a}' THEN "
            f"list_aggregate(list_slice(s.{m}, w.first + 1, w.last + 1), '{a}')"
            for m in metrics
            for a in ("sum", "min", "max")
        )
        con.execute(
            f"""CREATE OR REPLACE TEMP TABLE v AS
            WITH s AS (SELECT csbid, county_fips, {cols}
                       FROM read_parquet('{root}/season_summary/{year}/*.parquet')),
            x AS (SELECT s.csbid, s.county_fips AS county, w.rule, w.crop, w.compare, w.threshold,
                         CASE {value} END AS value
                  FROM s JOIN fips_state f ON f.fips = left(s.county_fips, 2)
                  JOIN win w ON w.state = f.state)
            SELECT *, CASE WHEN compare = 'ge' THEN value >= threshold
                           ELSE value <= threshold END AS hit
            FROM x WHERE value IS NOT NULL"""
        )
        parts.append(
            con.execute(
                f"""SELECT county, {year} AS year, rule, crop, avg(hit::INT) AS share,
                           count(*) AS fields FROM v GROUP BY ALL"""
            ).df()
        )
        if year in LEVEL_YEARS:
            con.execute(
                """INSERT INTO levels SELECT csbid, county, rule, crop, 1, hit::INT FROM v"""
            )
            con.execute(
                """CREATE OR REPLACE TABLE levels AS SELECT csbid, county, rule, crop,
                       sum(seasons)::INT seasons, sum(hits)::INT hits FROM levels GROUP BY ALL"""
            )
        print(year, file=sys.stderr, flush=True)
    pd.concat(parts).to_parquet(out / "exposure.parquet")
    con.execute(f"COPY levels TO '{out}/levels.parquet' (FORMAT parquet)")


def demean(x: np.ndarray, groups: np.ndarray) -> np.ndarray:
    sums = np.zeros((groups.max() + 1,) + x.shape[1:])
    np.add.at(sums, groups, x)
    counts = np.bincount(groups).reshape((-1,) + (1,) * (x.ndim - 1))
    return x - (sums / counts)[groups]


def effect(d: pd.DataFrame) -> dict | None:
    """log yield on share hit; county effects, state quadratic trends, SE clustered by year."""
    if len(d) < 100 or d.share.std() == 0 or d.year.nunique() < 6:
        return None
    county = d.county.astype("category").cat.codes.to_numpy()
    t = (d.year.to_numpy() - 2000) / 10.0
    states = pd.get_dummies(d.county.str[:2]).to_numpy(float)
    X = np.column_stack([d.share.to_numpy(), states * t[:, None], states * (t**2)[:, None]])
    y = np.log(d["yield"].to_numpy())
    Xd, yd = demean(X, county), demean(y, county)
    beta, *_ = np.linalg.lstsq(Xd, yd, rcond=None)
    resid = yd - Xd @ beta
    bread = np.linalg.pinv(Xd.T @ Xd)
    years = d.year.to_numpy()
    scores = np.array([Xd[years == yr].T @ resid[years == yr] for yr in np.unique(years)])
    g = len(scores)
    cov = bread @ (scores.T @ scores) @ bread * g / (g - 1)
    b, se = float(beta[0]), float(np.sqrt(max(cov[0, 0], 0)))
    return {
        "loss_pct_all_hit": round(100 * (np.exp(b) - 1), 1),
        "se_pct": round(100 * se, 1),
        "mean_share_hit": round(float(d.share.mean()), 3),
        "county_years": len(d),
        "counties": int(county.max() + 1),
        "years": g,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--reuse", action="store_true", help="reuse <out>/exposure.parquet")
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    crop_yields = root / "yields" / "nass_county_crops.parquet"
    if not crop_yields.exists():
        fetch_yields(crop_yields)
    con = duckdb.connect()
    con.execute("SET memory_limit = '6GB'; SET threads = 8")
    con.execute(
        f"""CREATE TABLE y AS
        SELECT crop, year, county_fips, "yield" FROM read_parquet('{crop_yields}')
        UNION ALL SELECT lower(crop), year, county_fips, yield_bu_acre
        FROM read_parquet('{root}/yields/nass_yield.parquet')"""
    )
    win = windows()
    win.to_csv(out / "windows.csv", index=False)
    if not (args.reuse and (out / "exposure.parquet").exists()):
        exposure(con, root, win, out)
    with REGIONS.open(newline="") as handle:
        region = {r["county_fips"]: r["region"] for r in csv.DictReader(handle)}
    panel = con.execute(
        f"""SELECT e.*, y."yield" FROM read_parquet('{out}/exposure.parquet') e
            JOIN y ON y.crop = e.crop AND y.year = e.year AND y.county_fips = e.county
            WHERE y."yield" > 0"""
    ).df()
    panel["region"] = panel.county.map(region)
    with IRRIGATED.open(newline="") as handle:
        irrigated = {
            (r["crop"], r["county_fips"]): float(r["share"]) for r in csv.DictReader(handle)
        }
    share = [irrigated.get(key, 0.0) for key in zip(panel.crop, panel.county, strict=True)]
    panel["dryland"] = np.array(share) < DRYLAND_BELOW
    levels = con.execute(
        f"""SELECT county, rule, crop, hits / seasons AS share FROM
            read_parquet('{out}/levels.parquet') WHERE seasons >= 10"""
    ).df()
    levels["region"] = levels.county.map(region)
    result = {}
    for (rule, crop), d in panel.groupby(["rule", "crop"]):
        rows = {"all": effect(d), "dryland": effect(d[d.dryland])}
        for reg, dr in d.groupby("region"):
            rows[reg] = effect(dr)
        lv = levels[(levels.rule == rule) & (levels.crop == crop)]
        for reg, lr in lv.groupby("region"):
            if rows.get(reg) is None:
                rows[reg] = {}
            rows[reg]["fields"] = len(lr)
            rows[reg]["level_share"] = {
                "none": round(float((lr.share < 0.1).mean()), 3),
                "low": round(float(((lr.share >= 0.1) & (lr.share < 0.25)).mean()), 3),
                "medium": round(float(((lr.share >= 0.25) & (lr.share < 0.5)).mean()), 3),
                "high": round(float((lr.share >= 0.5).mean()), 3),
            }
        result[f"{rule}/{crop}"] = rows
    (out / "result.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
