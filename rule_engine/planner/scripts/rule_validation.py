"""Do the engine's rules predict real yields? Every rule tested alone and combined, next to random
rules that should predict nothing.

For every sampled field and year 2019-2025 where CDL shows corn or soybeans, the rules are
evaluated with the engine's own fact builders on what is observed: the CDL history before that
year, the SSURGO soil of the field, the season's weather (timed hazards) and the county's
cause-of-loss record. Rules that read the tillage, the cover crop or the herbicide program are not
testable (no field records them) and are listed as such.

A rule's exposure is the share of a county's sampled corn (or soybean) acres where it fires in a
year. Log NASS county yield is regressed on it with county and state x year fixed effects,
weighted by the sampled acres the share stands for, standard errors clustered by county. The
coefficient is the yield change of a county where the rule fires on every acre against one where
it fires on none; for a rule with a yield factor it can be set against log(midpoint factor).

Controls for false positives, run through the same regression:
  noise_field_k   fires on a random set of fields (the same fields every year)
  noise_year_k    fires on a random set of field-years
  random_k        a rule drawn at random from the same facts and thresholds the real rules use
  <hazard>@next   a weather hazard evaluated on the following season, which cannot affect this one
Combined: the sum of log yield factors of the fired yield rules (a calibrated set gives a
coefficient of 1), the risk points, the benefit points and the hazard hits, in one regression.

CDL labels are satellite estimates and the county share is estimated from a sample: both push the
coefficients toward zero.

    python rule_engine/planner/scripts/rule_validation.py --root data/local/usa_sample_v3 \
        --weights cell_weights.parquet --out rule_validation
"""

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

import duckdb
import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "backend"), str(Path(__file__).resolve().parent)]

from repeat_yield_panel import demean  # noqa: E402
from rule_engine.engine import LEVEL_WEIGHT  # noqa: E402
from rule_engine.facts import (  # noqa: E402
    HistoryYear,
    candidate_facts,
    county_facts,
    field_facts,
    hazard_result,
    history_facts,
)
from rule_engine.rules import Condition, applies, check  # noqa: E402
from rule_engine.summary import SCALAR_KEYS, SeasonSummary, _clean  # noqa: E402

YEARS = range(2019, 2026)
CROPS = {1: "corn", 5: "soybeans"}
NASS = {"corn": "CORN", "soybeans": "SOYBEANS"}
UNOBSERVED = ("field.practice.", "herbicide.")
NOISE = 20
RANDOM = 60
W = {}


def testable(rule) -> bool:
    return not any(c.fact.startswith(UNOBSERVED) for c in rule.when)


def _hash(*parts) -> float:
    digest = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


def init(root: str, random_rules: list) -> None:
    from app.services.rotation_advice import RotationAdvice

    service = RotationAdvice(root, soil_lookup=False)
    advisor = service.advisor
    W.update(service=service, advisor=advisor, root=Path(root), random_rules=random_rules)
    W["rules"] = [r for r in advisor.rules.rules if testable(r)]
    W["noise_p"] = [0.05 + 0.45 * _hash("p", k) for k in range(NOISE)]


def seasons_of(root: Path, county: str, ids: list[str], years) -> dict:
    files = [root / "season_summary" / str(y) / f"{county}.parquet" for y in years]
    files = [f for f in files if f.exists()]
    if not files:
        return {}
    con = duckdb.connect()
    con.execute("SET threads = 1")
    con.execute("CREATE TEMP TABLE ids (csbid VARCHAR)")
    con.executemany("INSERT INTO ids VALUES (?)", [(i,) for i in ids])
    paths = ", ".join(f"'{f}'" for f in files)
    result = con.execute(
        f"SELECT * FROM read_parquet([{paths}], union_by_name=true) JOIN ids USING (csbid)"
    )
    columns = [d[0] for d in result.description]
    out = {}
    for record in result.fetchall():
        row = dict(zip(columns, record))
        out[(row["csbid"], int(row["year"]))] = SeasonSummary(
            csbid=row["csbid"],
            county_fips=str(row["county_fips"]),
            year=int(row["year"]),
            cdl_prev1=_clean(row.get("cdl_prev1")),
            cdl_prev2=_clean(row.get("cdl_prev2")),
            scalars={k: _clean(row.get(k)) for k in SCALAR_KEYS},
            weekly={k: list(v) for k, v in row.items() if isinstance(v, list)},
        )
    return out


def field_years(county: str, fields: list[tuple]):
    """Yield (csbid, year, crop id, weight, facts, season, next season) for corn/soy field-years."""
    service, advisor = W["service"], W["advisor"]
    catalog = advisor.catalog
    seasons = seasons_of(W["root"], county, [f[0] for f in fields], range(2019, 2027))
    for csbid, weight, state, cdl in fields:
        record = {"stateFips": state, "countyFips": county}
        soil = service._sampled_soil(csbid)
        if soil:
            record["soil"] = soil
        region, _ = advisor.region_for(record)
        for year in YEARS:
            crop_id = CROPS.get(cdl.get(year))
            if crop_id is None:
                continue
            crop = catalog.crops[crop_id]
            history = []
            for past in sorted(y for y in cdl if y < year):
                found = catalog.by_cdl(cdl[past])
                history.append(HistoryYear(past, found.id if found else None, cdl[past], "cdl"))
            season = seasons.get((csbid, year))
            facts = {
                **candidate_facts(crop),
                **history_facts(history, crop, catalog),
                **field_facts(record, history, [season] if season else []),
                **county_facts([season] if season else []),
            }
            calendar = advisor.reference.calendar(crop, region)
            yield (
                csbid,
                year,
                crop,
                weight,
                facts,
                calendar,
                season,
                seasons.get((csbid, year + 1)),
            )


def _hazard_hit(rule, calendar, season) -> bool | None:
    if season is None:
        return None
    result = hazard_result(rule.hazard, calendar, [season])
    if result is None or not result.per_season:
        return None
    return result.per_season[0][2]


def work(task: tuple) -> dict:
    county, fields = task
    catalog = W["advisor"].catalog
    agg: dict = {}
    for csbid, year, crop, weight, facts, calendar, season, following in field_years(
        county, fields
    ):
        cell = agg.setdefault((county, year, crop.id), defaultdict(float))
        cell["_weight"] += weight
        cell["_fields"] += 1
        index = {"yield_index": 0.0, "risk_points": 0.0, "benefit_points": 0.0, "hazard_hits": 0.0}
        for rule in W["rules"]:
            if not applies(rule, crop, catalog):
                continue
            if rule.hazard is not None:
                hit = _hazard_hit(rule, calendar, season)
                if hit is None:
                    continue
                cell[f"n:{rule.id}"] += weight
                cell[rule.id] += weight * hit
                index["hazard_hits"] += hit
                later = _hazard_hit(rule, calendar, following)
                if later is not None:
                    cell[f"n:{rule.id}@next"] += weight
                    cell[f"{rule.id}@next"] += weight * later
                continue
            fired = all(check(c, facts)[0] for c in rule.when)
            cell[f"n:{rule.id}"] += weight
            cell[rule.id] += weight * fired
            if not fired:
                continue
            if rule.effect.yield_factor:
                low, high = rule.effect.yield_factor
                index["yield_index"] += math.log((low + high) / 2)
            elif rule.effect.kind == "risk":
                index["risk_points"] += LEVEL_WEIGHT[rule.effect.level]
            elif rule.effect.kind == "benefit":
                index["benefit_points"] += 1
        for name, value in index.items():
            cell[name] += weight * value
        for k, p in enumerate(W["noise_p"]):
            cell[f"noise_field_{k}"] += weight * (_hash("f", k, csbid) < p)
            cell[f"noise_year_{k}"] += weight * (_hash("y", k, csbid, year) < p)
        for k, (crop_id, conditions) in enumerate(W["random_rules"]):
            if crop_id != crop.id:
                continue
            fired = all(check(Condition(*c), facts)[0] for c in conditions)
            cell[f"n:random_{k}"] += weight
            cell[f"random_{k}"] += weight * fired
    return {key: dict(value) for key, value in agg.items()}


def random_rules(pilot: list[dict], rules, seed: int) -> list:
    """Rules drawn from the facts the real rules read, with thresholds inside observed values."""
    names = sorted(
        {c.fact for r in rules for c in r.when if not c.fact.startswith(("candidate.",))}
    )
    rng = random.Random(seed)
    out = []
    while len(out) < RANDOM:
        crop = rng.choice(sorted(CROPS.values()))
        pool = [f for f in pilot if f["candidate.crop"] == crop]
        conditions = []
        for name in rng.sample(names, rng.choice((1, 1, 2))):
            values = [f.get(name) for f in pool if f.get(name) is not None]
            values = [v for v in values if not isinstance(v, (list, tuple, set, dict))]
            if len(set(map(str, values))) < 2:
                continue
            value = rng.choice(values)
            if isinstance(value, bool) or isinstance(value, str):
                conditions.append((name, "eq", value))
            else:
                q = rng.uniform(0.1, 0.9)
                threshold = float(np.quantile(np.array(values, dtype=float), q))
                conditions.append((name, rng.choice(("ge", "le")), threshold))
        if not conditions:
            continue
        rate = np.mean([all(check(Condition(*c), f)[0] for c in conditions) for f in pool])
        if 0.05 <= rate <= 0.95:  # a rule that fires everywhere or nowhere tests nothing
            out.append((crop, tuple(conditions)))
    return out


def fit(rows: list[tuple], names: list[str]) -> dict:
    """rows: (county, state_year, weight, y, *x). Weighted two-way FE OLS, clustered by county."""
    county = np.unique([r[0] for r in rows], return_inverse=True)[1]
    state_year = np.unique([r[1] for r in rows], return_inverse=True)[1]
    w = np.array([r[2] for r in rows], dtype=float)
    groups = [county, state_year]
    y = demean(np.array([r[3] for r in rows], dtype=float), groups, w)
    X = np.column_stack(
        [
            demean(np.array([r[4 + k] for r in rows], dtype=float), groups, w)
            for k in range(len(names))
        ]
    )
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    resid = y - X @ beta
    bread = np.linalg.pinv((X * w[:, None]).T @ X)
    order = np.argsort(county)
    bounds = np.flatnonzero(np.diff(county[order])) + 1
    scores = np.add.reduceat((X * (w * resid)[:, None])[order], np.r_[0, bounds], axis=0)
    n_c = len(bounds) + 1
    cov = bread @ (scores.T @ scores) @ bread * n_c / (n_c - 1)
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    within_r2 = 1 - np.sum(w * resid**2) / np.sum(w * y**2)
    return {
        "observations": len(rows),
        "counties": n_c,
        "within_r2": float(within_r2),
        "coef": dict(zip(names, map(float, beta))),
        "se": dict(zip(names, map(float, se))),
        "within_sd": {
            n: float(np.sqrt(np.average(X[:, k] ** 2, weights=w))) for k, n in enumerate(names)
        },
    }


def p_value(coef: float, se: float) -> float:
    return math.erfc(abs(coef / se) / math.sqrt(2)) if se > 0 else 1.0


def bh(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg q-values."""
    n = len(pvalues)
    order = sorted(range(n), key=lambda i: pvalues[i])
    q = [0.0] * n
    running = 1.0
    for rank, i in reversed(list(enumerate(order, start=1))):
        running = min(running, pvalues[i] * n / rank)
        q[i] = running
    return q


def load_tasks(root: Path, weights: Path) -> list[tuple]:
    con = duckdb.connect()
    con.execute("SET memory_limit = '3GB'")
    rows = con.execute(
        f"""
        WITH f AS (
            SELECT CSBID, STATEFIPS AS state, STATEFIPS || CNTYFIPS AS county_fips,
                   CSBACRES::DOUBLE AS acres, ix::INT AS ix, iy::INT AS iy
            FROM read_csv('{root}/fields.csv', all_varchar=true)
        ),
        k AS (SELECT county_fips, ix, iy, count(*) AS sampled FROM f GROUP BY ALL)
        SELECT f.CSBID, f.state, f.county_fips, f.acres * w.n / k.sampled AS weight,
               c.* EXCLUDE (CSBID)
        FROM f JOIN k USING (county_fips, ix, iy)
        JOIN read_parquet('{weights}') w USING (county_fips, ix, iy)
        JOIN read_parquet('{root}/cdl_history_all.parquet') c ON c.CSBID = f.CSBID
        """
    )
    columns = [d[0] for d in rows.description]
    by_county = defaultdict(list)
    for record in rows.fetchall():
        row = dict(zip(columns, record))
        cdl = {int(k[3:]): int(v) for k, v in row.items() if k.startswith("CDL") and v is not None}
        if any(cdl.get(y) in CROPS for y in YEARS):
            by_county[row["county_fips"]].append((row["CSBID"], row["weight"], row["state"], cdl))
    return sorted(by_county.items(), key=lambda t: -len(t[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--yields", type=Path, help="default <root>/yields/nass_yield.parquet")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--processes", type=int, default=3)
    parser.add_argument("--counties", type=int, help="only the first N counties (a trial run)")
    parser.add_argument("--min-fields", type=int, default=5)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--cells", type=Path, help="county_years.json of an earlier run: analyse only"
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    root = args.root.resolve()
    if args.cells:
        init(str(root), [])
        cells = {tuple(k[:3]): k[3] for k in json.loads(args.cells.read_text())}
    else:
        cells = compute(root, args)
    yields_path = args.yields or root / "yields" / "nass_yield.parquet"
    yields = {
        (c, crop, int(y)): v
        for c, crop, y, v in duckdb.sql(
            f"SELECT county_fips, crop, year, yield_bu_acre FROM '{yields_path}'"
        ).fetchall()
        if v
    }
    cells = {
        key: value
        for key, value in cells.items()
        if value["_fields"] >= args.min_fields and (key[0], NASS[key[2]], key[1]) in yields
    }
    if not args.cells:
        (args.out / "county_years.json").write_text(json.dumps([[*k, v] for k, v in cells.items()]))
    analyse(cells, yields, args.out)


def compute(root: Path, args) -> dict:
    tasks = load_tasks(root, args.weights)
    if args.counties:
        tasks = tasks[: args.counties]
    print(f"{len(tasks)} counties, {sum(len(t[1]) for t in tasks):,} fields", flush=True)
    # random rules: thresholds from the facts of a few counties
    init(str(root), [])
    pilot = []
    for county, fields in tasks[:: max(1, len(tasks) // 6)][:6]:
        pilot += [facts for *_, facts, _c, _s, _n in field_years(county, fields[:200])]
    rules = random_rules(pilot, W["rules"], args.seed)
    (args.out / "random_rules.json").write_text(json.dumps(rules, indent=1, default=str))
    agg: dict = {}
    with Pool(args.processes, init, (str(root), rules), maxtasksperchild=60) as pool:
        for i, part in enumerate(pool.imap_unordered(work, tasks), start=1):
            agg.update(part)
            if i % 200 == 0:
                print(f"{i}/{len(tasks)} counties", flush=True)
    return agg


INDICES = ("yield_index", "risk_points", "benefit_points", "hazard_hits")


def share_rows(cells: dict, yields: dict, crop: str, names: list[str]) -> list[tuple]:
    rows = []
    for (county, year, c), v in cells.items():
        if c != crop:
            continue
        shares = []
        for name in names:
            exposed = v["_weight"] if name in INDICES else v.get(f"n:{name}", v["_weight"])
            shares.append(v.get(name, 0.0) / exposed if exposed > 0 else 0.0)
        y = math.log(yields[(county, NASS[crop], year)])
        rows.append((county, county[:2] + str(year), v["_weight"], y, *shares))
    return rows


def kind_of(name: str, real: dict) -> str:
    if name.startswith("noise_"):
        return "noise"
    if name.startswith("random_"):
        return "random"
    if "@" in name:
        return "next_season"
    return "rule" if name in real else "index"


def analyse(cells: dict, yields: dict, out: Path) -> None:
    real = {r.id: r for r in W["rules"]}
    untestable = sorted(r.id for r in W["advisor"].rules.rules if not testable(r))
    results, joint = [], {}
    for crop in sorted(NASS):
        mine = [v for k, v in cells.items() if k[2] == crop]
        names = sorted({n for v in mine for n in v if not n.startswith(("_", "n:"))})
        kept = []
        for name in names:
            rows = share_rows(cells, yields, crop, [name])
            if len(rows) < 200:
                continue
            fitted = fit(rows, [name])
            mean = float(np.average([r[4] for r in rows], weights=[r[2] for r in rows]))
            if fitted["within_sd"][name] < 0.005 or not 0.005 < mean < 0.995:
                continue  # too little movement within counties to test
            kind = kind_of(name, real)
            rule = real.get(name.split("@")[0])
            if kind == "rule":
                kept.append(name)
            factor = rule.effect.yield_factor if rule and kind == "rule" else None
            coef, se = fitted["coef"][name], fitted["se"][name]
            results.append(
                {
                    "crop": crop,
                    "name": name,
                    "kind": kind,
                    "effect": rule.effect.kind if rule else None,
                    "level": rule.effect.level if rule else None,
                    "evidence": rule.evidence_strength if rule else None,
                    "claimed_log_factor": math.log(sum(factor) / 2) if factor else None,
                    "coef": coef,
                    "se": se,
                    "p": p_value(coef, se),
                    "q": None,
                    "mean_share": mean,
                    "within_sd": fitted["within_sd"][name],
                    "observations": fitted["observations"],
                }
            )
        # every testable real rule in one regression: what each adds given the others
        if kept:
            joint[crop] = fit(share_rows(cells, yields, crop, kept), kept)
    for kind in ("rule", "random", "noise", "next_season"):
        group = [r for r in results if r["kind"] == kind]
        for r, q in zip(group, bh([r["p"] for r in group])):
            r["q"] = q
    combined = {
        crop: fit(share_rows(cells, yields, crop, list(INDICES)), list(INDICES))
        for crop in sorted(NASS)
    }
    (out / "combined.json").write_text(
        json.dumps({"combined": combined, "joint": joint, "untestable": untestable}, indent=1)
    )
    with (out / "results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"{len(results)} tests written to {out}", flush=True)


if __name__ == "__main__":
    main()
