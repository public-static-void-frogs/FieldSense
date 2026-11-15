"""How much the crops actually grown fall short of the planner's best plan, field by field.

For a sample of fields, the planner starts from the CDL history up to 2020 and values three
five-season plans for 2021-2025 under the same year odds, prices and costs:
  actual       the crops CDL shows in 2021-2025 (tillage and cover crop chosen at their best)
  alternation  corn and soybeans in turn, the better of the two phases (where both are planned)
  optimum      the solver's best fixed sequence (what the recommendation screen shows)

The sample is drawn from the v3 summary sample with probability proportional to the number of
CSB fields each sampled field stands for (its gridMET cell's fields / sampled fields there), so
it represents all CSB fields; sums use field acres. CDL labels are satellite estimates.

    cd backend && PYTHONPATH=.:.. python ../rule_engine/planner/scripts/rotation_gap.py \
        --root ../data/local/usa_sample_v3 --weights cell_weights.parquet --fields 1200 \
        --processes 4 --out gap.jsonl
"""

import argparse
import json
import sys
import time
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "backend")]

FIRST, LAST = 2021, 2025
SERVICE = {}


def sample(root: Path, weights: Path, size: int | None, seed: int) -> list[dict]:
    import duckdb
    import numpy as np

    rows = duckdb.sql(
        f"""
        WITH f AS (
            SELECT CSBID, STATEFIPS AS state, CNTYFIPS AS county, CSBACRES AS acres,
                   centroid_lon AS lon, centroid_lat AS lat, ix, iy,
                   STATEFIPS || CNTYFIPS AS county_fips
            FROM read_csv('{root}/fields.csv', all_varchar=true)
        ),
        k AS (SELECT county_fips, ix, iy, count(*) AS sampled FROM f GROUP BY ALL)
        SELECT f.*, w.n / k.sampled AS weight
        FROM f JOIN k USING (county_fips, ix, iy)
        JOIN read_parquet('{weights}') w
          ON w.county_fips = f.county_fips AND w.ix = f.ix::INT AND w.iy = f.iy::INT
        ORDER BY f.CSBID
        """
    ).fetchall()  # ordered: the draw below must pick the same fields on every run
    names = ["CSBID", "state", "county", "acres", "lon", "lat", "ix", "iy", "county_fips", "weight"]
    rows = [dict(zip(names, r)) for r in rows]
    if size is None:
        return rows
    p = np.array([r["weight"] for r in rows], dtype=float)
    picked = np.random.default_rng(seed).choice(len(rows), size, replace=False, p=p / p.sum())
    return [rows[i] for i in picked]


def best_value(model, start, allowed):
    """Best open-loop objective from `start`, actions limited by allowed(state) -> list."""
    memo = {}

    def value(state):
        if model.terminal(state):
            return 0.0, ()
        key = model.key(state)
        if key not in memo:
            options = []
            for action in allowed(state):
                after, path = value(model.transition(state, action))
                options.append((model.expected(state, action) + after, ((state, action),) + path))
            memo[key] = max(options, key=lambda o: o[0]) if options else (float("-inf"), ())
        return memo[key]

    return value(start)


def cash(model, path) -> float:
    total = 0.0
    for state, action in path:
        step = model.summary(state, action)
        total += step["revenueUsdPerAcre"] - step["costUsdPerAcre"]
    return total


def calibrate(advisor) -> None:
    """The repeat penalties measured on real yields instead of the rule file's ranges.

    Corn after corn: 3 % (Seifert et al. 2017, satellite-estimated field yields: 1.9 % in the
    second year of corn, 5.7 % after); soybeans after soybeans: 10 % (Seifert: 10.3 %; the
    county panel of repeat_yield_panel.py: 8.9 +- 3.8 %).

    The rule files carry calibrated ranges since 2026-11-15 (calibrate_yield_factors.py); with
    them this variant changes nothing.
    """
    rules = list(advisor.rules.rules)
    if any(r.id == "soy_after_soy_yield_penalty" for r in rules):
        return
    corn = next(r for r in rules if r.id == "continuous_corn_yield_penalty")
    rules[rules.index(corn)] = replace(corn, effect=replace(corn.effect, yield_factor=(0.95, 0.99)))
    rules.append(
        replace(
            corn,
            id="soy_after_soy_yield_penalty",
            applies_to={"crops": ("soybeans",)},
            effect=replace(corn.effect, yield_factor=(0.87, 0.93)),
        )
    )
    object.__setattr__(advisor.rules, "rules", tuple(rules))


def init(root: str, variant: str) -> None:
    from app.services.rotation_advice import RotationAdvice

    SERVICE["service"] = RotationAdvice(root, soil_lookup=False)
    SERVICE["variant"] = variant
    if variant == "calibrated":
        calibrate(SERVICE["service"].advisor)


def one(row: dict) -> dict:
    try:
        return _one(row)
    except Exception as error:  # one bad field must not stop the run
        return {"CSBID": row["CSBID"], "skip": "error", "error": repr(error)[:300]}


def _one(row: dict) -> dict:
    from rule_engine.planner import RotationModel, build_context

    service = SERVICE["service"]
    advisor = service.advisor
    out = {k: row[k] for k in ("CSBID", "state", "county_fips", "acres", "weight")}
    cdl = service._cdl_history(row["CSBID"])
    history = {k: v for k, v in cdl.items() if int(k[3:]) < FIRST}
    actual_codes = [cdl.get(f"CDL{y}") for y in range(FIRST, LAST + 1)]
    actual = [advisor.catalog.by_cdl(c) if c is not None else None for c in actual_codes]
    out["cdl"] = actual_codes
    out["actual"] = [c.id if c else None for c in actual]
    if None in actual:
        return {**out, "skip": "not_a_catalog_crop"}
    field = {
        "id": row["CSBID"],
        "crop": None,
        "area": float(row["acres"]) * 0.404686,
        "sourceId": row["CSBID"],
        "stateFips": row["state"],
        "countyFips": row["county"],
        "sourceYear": FIRST - 1,
        "sourceProperties": history,
        "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
    }
    started = time.time()
    record = service.engine_field(field)
    region, _ = advisor.region_for(record)
    service._apply_economics(record, None, None, region)
    candidates = advisor.candidate_ids(region)
    context = build_context(record, advisor, [service._path("season_summary")])
    context = replace(context, reference_aws_mm=service._reference_aws(row["state"]))
    climate = None
    if advisor.climate:
        climate = advisor.climate.record(record.get("latitude"), record.get("longitude"))
    if climate:
        merged = {s.year: s for s in climate.seasons} | context.seasons
        context = replace(context, seasons=merged)
    try:
        model = RotationModel(context, advisor, crops=tuple(candidates), horizon=LAST - FIRST + 1)
    except ValueError:
        return {**out, "skip": "no_modellable_crop"}
    missing = sorted({c.id for c in actual} - set(model.crops))
    if missing:
        return {**out, "skip": "actual_crop_not_planned", "missing": missing}
    start = model.open_loop_state
    out["history"] = list(context.history)
    out["region"] = region

    forced = []

    def fixed(crops):
        def allowed(state):
            options = [a for a in model.actions(state) if a.crop == crops[state.t]]
            if options:
                return options
            # the model's own rules forbid this crop here (a perennial ended before its minimum
            # life): the actual crop is still valued, without a cover crop
            forced.append(state.t)
            return [a for a in model.all_actions if a.crop == crops[state.t] and a.cover == "none"]

        return allowed

    plans = {"actual": best_value(model, start, fixed([c.id for c in actual]))}
    if {"corn", "soybeans"} <= set(model.crops):
        phases = [
            best_value(model, start, fixed([pair[(t + p) % 2] for t in range(5)]))
            for p in (0, 1)
            for pair in [("corn", "soybeans")]
        ]
        plans["alternation"] = max(phases, key=lambda o: o[0])
    plans["optimum"] = best_value(model, start, model.actions)
    for name, (objective, path) in plans.items():
        out[name] = {
            "objective": round(objective, 2),
            "cash": round(cash(model, path), 2),
            "crops": [a.crop for _, a in path],
            "management": [f"{a.tillage}/{a.cover}" for _, a in path],
        }
    out["actualForcedYears"] = sorted(set(forced))
    out["variant"] = SERVICE["variant"]
    out["seconds"] = round(time.time() - started, 1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--fields", type=int, default=1200)
    parser.add_argument("--processes", type=int, default=4)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--variant", choices=("rules", "calibrated"), default="rules")
    parser.add_argument("--only", type=Path, help="jsonl of an earlier run: its usable fields only")
    args = parser.parse_args()
    size = None if args.only else args.fields
    rows = sample(Path(args.root).resolve(), args.weights, size, args.seed)
    done = set()
    if args.out.exists():
        done = {json.loads(line)["CSBID"] for line in args.out.open()}
    if args.only:  # exactly the usable fields of that run, whatever sample they came from
        keep = {r["CSBID"] for r in map(json.loads, args.only.open()) if "optimum" in r}
        rows = [r for r in rows if r["CSBID"] in keep]
    rows = [r for r in rows if r["CSBID"] not in done]
    with (
        Pool(args.processes, init, (args.root, args.variant), maxtasksperchild=40) as pool,
        args.out.open("a") as handle,
    ):
        for i, result in enumerate(pool.imap_unordered(one, rows, chunksize=4), start=1):
            handle.write(json.dumps(result) + "\n")
            handle.flush()
            if i % 50 == 0:
                print(f"{i}/{len(rows)}", flush=True)


if __name__ == "__main__":
    main()
