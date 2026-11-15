"""Backtest of the first-season forecast: every past year forecast from earlier years only.

    python rule_engine/planner/scripts/backtest.py \
        --summaries data/local/usa_sample_v2/season_summary --out data/local/planner/backtest

For each county with a yield record, each crop (corn, soybeans) and each target year Y, forecasts
are built from years before Y and compared with what happened in Y: the county yield and the
marketing-year price of Y less the ERS regional cost of Y (land excluded), in Y-1 dollars.

Every forecast is a set of outcome years j with odds:

    yield_j = expected yield x (yield_j / trend_j)      trend: line through the county yields
    price_j = price factor of j x the last known price (Y-1)
    cost    = the ERS regional cost of Y-1

and the variants (VARIANTS) differ in three choices:

    price factor   level   constant-dollar price of j over the mean of the history
                   change  constant-dollar price of j over that of j-1, scaled to mean 1
    trend read at  the last observed year, or one year further (the target year)
    odds of year j equal, or the analog-year chain of planner/chance.py started after Y-1, on
                   drought and price carry-over or on drought alone

Two things differ from the live forecast: the live planning price is a futures-based projected
price (here: last year's price), and years without a county yield are left out instead of being
modelled from the weather.

A county yield is the finest yield record there is, so this tests the county-level forecast.
Nothing here tests how a single field differs from its county.

Writes <out>/backtest.parquet (one row per county, crop and year) and <out>/backtest.json.
"""

import argparse
import csv
import json
import sys
from multiprocessing import Pool
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from rule_engine.planner.chance import EDGE_WEEKS, Persistence, YearChain, _edge  # noqa: E402
from rule_engine.planner.sampler import (  # noqa: E402
    _cpi,
    _history_rows,
    _series,
    _trend,
    price_changes,
    price_levels,
)
from rule_engine.planner.tables import DATA, NATIONAL, ers_region  # noqa: E402
from rule_engine.regions import STATE_FIPS  # noqa: E402

CROPS = {"corn": "yield_corn_bu_ac", "soybeans": "yield_soy_bu_ac"}
MIN_HISTORY_YEARS = 15
LOSS_BINS = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0001)
# name: (price factor, years past the last observed one the trend is read at, analog signals)
VARIANTS = {
    "level_analog": ("level", 0, ("drought", "price")),  # the model before this backtest
    "level_equal": ("level", 0, ()),
    "change_equal": ("change", 1, ()),
    "change_analog": ("change", 1, ("drought", "price")),
    "change_drought": ("change", 1, ("drought",)),
}


def quantile(values: list[float], weights: list[float], q: float) -> float:
    total, acc = sum(weights), 0.0
    for value, weight in sorted(zip(values, weights)):
        acc += weight
        if acc >= q * total:
            return value
    return max(values)


def cost_history() -> dict[tuple[str, str, int], float]:
    with (DATA / "costs_regional_history.csv").open(newline="") as handle:
        return {
            (r["crop"], r["region"], int(r["year"])): float(r["usd_per_acre"])
            for r in csv.DictReader(handle)
        }


def county_forecasts(task) -> list[dict]:
    """Every (crop, year) forecast of one county."""
    county, rows, first_year = task
    state = STATE_FIPS.get(county[:2])
    region = ers_region(county)
    cpi, costs, history = _cpi(), cost_history(), _history_rows()
    prices = {crop: _series(history, "price", crop, state or "US")[0] for crop in CROPS}
    seasons = sorted(rows)
    drought = {
        y: (
            _edge(rows[y]["dm_max"], slice(0, EDGE_WEEKS)),
            _edge(rows[y]["dm_max"], slice(-EDGE_WEEKS, None)),
        )
        for y in seasons
    }
    out = []
    for target in range(first_year, max(seasons) + 1):
        if target not in rows or target - 1 not in rows or target not in cpi:
            continue
        before = [y for y in seasons if y < target]
        levels = {
            c: price_levels({y: p for y, p in prices[c].items() if y < target}) for c in CROPS
        }

        def level(year):
            found = [levels[c][year] for c in CROPS if year in levels[c]]
            return sum(found) / len(found) if found else None

        known = {c: {y: p for y, p in prices[c].items() if y < target} for c in CROPS}
        factors = {"level": levels, "change": {c: price_changes(known[c]) for c in CROPS}}
        odds = {}
        for signals in {v[2] for v in VARIANTS.values()}:
            first = [1.0] * len(before)
            if signals:
                start = {
                    y: {
                        "drought": drought[y][0] if "drought" in signals else None,
                        "price": level(y - 1) if "price" in signals else None,
                    }
                    for y in before
                }
                end = {
                    y: {
                        "drought": drought[y][1] if "drought" in signals else None,
                        "price": level(y) if "price" in signals else None,
                    }
                    for y in before
                }
                chain = YearChain(before, start, end, Persistence())
                if chain.signals:
                    first = chain.matrix[chain.latest]
            odds[signals] = dict(zip(before, first))
        to_base = cpi[target - 1] / cpi[target]  # year Y dollars -> Y-1 dollars
        for crop, column in CROPS.items():
            observed = {y: rows[y][column] for y in before if (rows[y][column] or 0) > 0}
            actual_yield, price = rows[target][column], prices[crop]
            if len(observed) < MIN_HISTORY_YEARS or not (actual_yield or 0) > 0:
                continue
            if target not in price or target - 1 not in price:
                continue
            cost_before = costs.get(
                (crop, region, target - 1), costs.get((crop, NATIONAL, target - 1))
            )
            cost_actual = costs.get((crop, region, target), costs.get((crop, NATIONAL, target)))
            if cost_before is None or cost_actual is None:
                continue
            trend = _trend(observed)
            actual_net = actual_yield * price[target] * to_base - cost_actual * to_base
            row = {
                "county": county,
                "state": state,
                "crop": crop,
                "year": target,
                "actual_yield": actual_yield,
                "actual_price": price[target] * to_base,
                "planning_price": price[target - 1],
                "actual_net": actual_net,
                "naive_yield": sum(observed[y] for y in sorted(observed)[-5:]) / 5,
            }
            for name, (mode, ahead, signals) in VARIANTS.items():
                factor = factors[mode][crop]
                expected = trend(max(observed) + ahead)
                years = [y for y in observed if trend(y) > 0 and y in factor]
                yields = [expected * observed[y] / trend(y) for y in years]
                sale = [factor[y] * price[target - 1] for y in years]
                net = [y * p - cost_before for y, p in zip(yields, sale)]
                weights = [odds[signals][y] for y in years]
                total = sum(weights)
                weights = [w / total for w in weights]
                row[f"{name}_loss"] = sum(w for n, w in zip(net, weights) if n < 0)
                row[f"{name}_net_mean"] = sum(n * w for n, w in zip(net, weights))
                row[f"{name}_yield_mean"] = sum(y * w for y, w in zip(yields, weights))
                row[f"{name}_price_mean"] = sum(p * w for p, w in zip(sale, weights))
                for label, values, actual in (
                    ("net", net, actual_net),
                    ("yield", yields, actual_yield),
                ):
                    for q in (10, 50, 90):
                        row[f"{name}_{label}_p{q}"] = quantile(values, weights, q / 100)
                row[f"{name}_effective_years"] = 1.0 / sum(w * w for w in weights)
            out.append(row)
    return out


def load(summaries: Path, per_county: int) -> dict[str, dict]:
    """{county: {year: {yields, dm_max}}} from the first sampled field(s) of each county."""
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit = '3GB'; SET threads = 4; SET preserve_insertion_order = false")
    years = sorted(p.name for p in summaries.iterdir() if p.name.isdigit())
    con.execute(f"""
        CREATE TABLE pick AS
        SELECT county_fips, csbid FROM read_parquet('{summaries}/{years[-1]}/*.parquet')
        QUALIFY row_number() OVER (PARTITION BY county_fips ORDER BY csbid) <= {per_county}
    """)
    rows = []
    for year in years:  # one year at a time: a single query over every file needs too much memory
        rows += con.execute(f"""
            SELECT s.county_fips, s.csbid, s.year, s.yield_corn_bu_ac, s.yield_soy_bu_ac, s.dm_max
            FROM read_parquet('{summaries}/{year}/*.parquet', union_by_name = true) s
            JOIN pick USING (county_fips, csbid)
        """).fetchall()
    found: dict[str, dict] = {}
    for county, _, year, corn, soy, dm_max in rows:
        found.setdefault(county, {})[year] = {
            "yield_corn_bu_ac": corn,
            "yield_soy_bu_ac": soy,
            "dm_max": dm_max,
        }
    return found


def report(frame) -> dict:
    """Calibration and error summaries per crop."""
    out = {}
    for crop, part in frame.groupby("crop"):
        loss = part["actual_net"] < 0
        result = {
            "forecasts": len(part),
            "counties": int(part["county"].nunique()),
            "years": [int(part["year"].min()), int(part["year"].max())],
            "lossShare": round(float(loss.mean()), 3),
        }
        result["variants"] = {}
        for name in VARIANTS:
            predicted = part[f"{name}_loss"]
            bins = []
            for low, high in zip(LOSS_BINS, LOSS_BINS[1:]):
                inside = (predicted >= low) & (predicted < high)
                if inside.any():
                    bins.append(
                        {
                            "predictedFrom": low,
                            "predictedTo": min(high, 1.0),
                            "forecasts": int(inside.sum()),
                            "meanPredicted": round(float(predicted[inside].mean()), 3),
                            "observed": round(float(loss[inside].mean()), 3),
                        }
                    )
            brier = float(((predicted - loss) ** 2).mean())
            base = float(((loss.mean() - loss) ** 2).mean())
            section = {
                "meanPredictedLoss": round(float(predicted.mean()), 3),
                "brier": round(brier, 4),
                "brierOfConstantBaseRate": round(base, 4),
                "brierSkill": round(1 - brier / base, 3) if base else None,
                "lossBins": bins,
                "effectiveYears": round(float(part[f"{name}_effective_years"].mean()), 1),
            }
            for label in ("net", "yield"):
                actual = part[f"actual_{label}"]
                low, high = part[f"{name}_{label}_p10"], part[f"{name}_{label}_p90"]
                section[label] = {
                    "insideP10P90": round(float(((actual >= low) & (actual <= high)).mean()), 3),
                    "belowP10": round(float((actual < low).mean()), 3),
                    "aboveP90": round(float((actual > high).mean()), 3),
                    "meanForecast": round(float(part[f"{name}_{label}_mean"].mean()), 1),
                    "meanActual": round(float(actual.mean()), 1),
                    "meanAbsError": round(
                        float((part[f"{name}_{label}_mean"] - actual).abs().mean()), 1
                    ),
                }
            by_year = part.assign(loss=loss).groupby("year")
            years = by_year.agg(predicted=(f"{name}_loss", "mean"), observed=("loss", "mean"))
            section["yearLevel"] = {
                "meanAbsGap": round(
                    float((years["predicted"] - years["observed"]).abs().mean()), 3
                ),
                "correlation": round(float(years["predicted"].corr(years["observed"])), 3),
            }
            section["priceMeanAbsErrorUsd"] = round(
                float((part[f"{name}_price_mean"] - part["actual_price"]).abs().mean()), 2
            )
            result["variants"][name] = section
        result["naiveYieldMeanAbsError"] = round(
            float((part["naive_yield"] - part["actual_yield"]).abs().mean()), 1
        )
        by_year = part.assign(loss=loss).groupby("year")
        result["byYear"] = [
            {
                "year": int(year),
                "forecasts": len(rows),
                "observedLoss": round(float(rows["loss"].mean()), 3),
                "actualNet": round(float(rows["actual_net"].mean()), 0),
                "predictedLoss": {
                    name: round(float(rows[f"{name}_loss"].mean()), 3) for name in VARIANTS
                },
                "forecastNet": {
                    name: round(float(rows[f"{name}_net_mean"].mean()), 0) for name in VARIANTS
                },
            }
            for year, rows in by_year
        ]
        out[crop] = result
    return out


def main() -> None:
    import pandas as pd

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--summaries", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--first-year", type=int, default=1997)
    parser.add_argument("--fields-per-county", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    counties = load(args.summaries, args.fields_per_county)
    print(f"{len(counties):,} counties loaded", flush=True)
    tasks = [(county, rows, args.first_year) for county, rows in sorted(counties.items())]
    with Pool(args.workers) as pool:
        rows = [
            row
            for part in pool.imap_unordered(county_forecasts, tasks, chunksize=20)
            for row in part
        ]
    frame = pd.DataFrame(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.out / "backtest.parquet", index=False)
    summary = report(frame)
    (args.out / "backtest.json").write_text(json.dumps(summary, indent=2) + "\n")
    for crop, result in summary.items():
        print(crop, result["forecasts"], "forecasts, loss share", result["lossShare"])
        for name, v in result["variants"].items():
            bins = " ".join(f"{b['meanPredicted']:.2f}>{b['observed']:.2f}" for b in v["lossBins"])
            print(
                f"  {name:15s} skill {v['brierSkill']:.3f} predLoss {v['meanPredictedLoss']:.3f}"
                f" netIn {v['net']['insideP10P90']:.3f} lo {v['net']['belowP10']:.3f}"
                f" hi {v['net']['aboveP90']:.3f} netMAE {v['net']['meanAbsError']:.0f}"
                f" net {v['net']['meanForecast']:.0f}/{v['net']['meanActual']:.0f}"
                f" yieldMAE {v['yield']['meanAbsError']:.1f} yrCorr {v['yearLevel']['correlation']:.2f}"
                f" | {bins}"
            )


if __name__ == "__main__":
    main()
