"""Run the rotation rule engine over every field of the USA sample and report coverage.

    python data/usa_sample/run_engine.py --root data/local/usa_sample --workers 8

The intended crop is the field's most recent CDL crop when that crop is a candidate in the
field's state, else the state's first candidate. Writes under --root:
    engine_results.parquet   one row per field (state, top crop, scores, gap codes, rule ids)
    engine_rule_firing.csv   how many fields each rule fired on (top-ranked and intended crop)
"""

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from rule_engine import build_advisor

_advisor = None


def _init(root: str):
    global _advisor
    climate = Path(root) / "climate_record"
    _advisor = build_advisor(
        Path(root) / "season_summary",
        climate_root=climate if (climate / "grid.json").exists() else None,
    )


def _findings(candidate: dict) -> list[str]:
    return [
        f["ruleId"]
        for kind in ("risks", "benefits", "advisories")
        for f in candidate[kind]
    ]


def _one(line: str) -> dict:
    field = json.loads(line)
    advisor = _advisor
    region, _ = advisor.region_for(field)
    candidates = advisor.candidate_ids(region)
    last = None
    props = field["sourceProperties"]
    for year in sorted((k for k in props if k.startswith("CDL")), reverse=True):
        crop = advisor.catalog.by_cdl(props[year])
        if last is None:
            last = crop.id if crop else f"cdl_{props[year]}"
        if crop and crop.id in candidates:
            intended = crop.id
            break
    else:
        intended = candidates[0]
    result = advisor.advise(field, intended, [], "metric")
    ranked = sorted(result["candidates"], key=lambda c: c["rank"])
    top = ranked[0]
    mine = next(c for c in ranked if c["isIntended"])
    known = [h for h in result["history"] if h.get("crop")]
    slot = result["offSeason"]
    record = result["weatherRecord"]
    return {
        "csbid": field["sourceId"],
        "state": region,
        "county_fips": field["countyFips"],
        "last_cdl_crop": last,
        "history_years": len(result["history"]),
        "history_known_years": len(known),
        "intended": intended,
        "intended_rank": mine["rank"],
        "intended_score": mine["score"],
        "top": top["crop"],
        "top_group": top["group"],
        "top_non_forage": next(
            (c["crop"] for c in ranked if c["group"] != top["group"]), None
        )
        if "forage" in str(top["group"])
        or "hay" in str(top["group"])
        or "pasture" in str(top["group"])
        else top["crop"],
        "top_score": top["score"],
        "candidates": len(ranked),
        "intended_risks": len(mine["risks"]),
        "intended_high_risks": sum(r["level"] == "high" for r in mine["risks"]),
        "intended_rules": _findings(mine),
        "top_rules": _findings(top),
        "intended_calendar": mine["calendar"]["kind"],
        "intended_yield_level": mine["yield"]["level"] if mine["yield"] else None,
        "has_revenue": mine["revenue"] is not None,
        "field_gaps": sorted({g["code"] for g in result["dataGaps"]}),
        "intended_gaps": sorted({g["code"] for g in mine["dataGaps"]}),
        "weather_seasons": record["seasons"] if record else 0,
        "off_season_status": slot["status"],
        "off_season_after": slot["afterCrop"],
        "off_season_seeding_doy": slot["seedingDoy"],
        **{f"off_season_{o['id']}": o["level"] for o in slot["options"]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    lines = (args.root / "fields.jsonl").read_text().splitlines()[: args.limit]
    with ProcessPoolExecutor(
        args.workers, initializer=_init, initargs=(str(args.root),)
    ) as pool:
        rows = list(pool.map(_one, lines, chunksize=50))
    frame = pd.DataFrame(rows)
    frame.to_parquet(args.root / "engine_results.parquet", index=False)

    firing = Counter(rule for rules in frame["intended_rules"] for rule in rules)
    top_firing = Counter(rule for rules in frame["top_rules"] for rule in rules)
    table = pd.DataFrame(
        {"intended_crop_fields": pd.Series(firing), "top_crop_fields": pd.Series(top_firing)}
    ).fillna(0).astype(int).sort_values("intended_crop_fields", ascending=False)  # fmt: skip
    table.to_csv(args.root / "engine_rule_firing.csv", index_label="rule_id")

    n = len(frame)
    print(f"{n:,} fields ranked in {frame['state'].nunique()} states")
    print(f"history: {(frame['history_known_years'] >= 5).mean():.1%} with >= 5 known crop years, "
          f"{(frame['history_known_years'] == 0).mean():.1%} with none")  # fmt: skip
    print(f"intended crop kept at rank 1: {(frame['intended_rank'] == 1).mean():.1%}")
    print(
        f"intended crop with a high risk: {(frame['intended_high_risks'] > 0).mean():.1%}"
    )
    print(f"revenue estimate: {frame['has_revenue'].mean():.1%}")
    print(
        "calendar kind:",
        frame["intended_calendar"].value_counts(normalize=True).round(3).to_dict(),
    )
    print("yield level:", frame["intended_yield_level"].value_counts(normalize=True, dropna=False).round(3).to_dict())  # fmt: skip
    print("intended crop:", frame["intended"].value_counts().head(12).to_dict())
    print("top-ranked crop:", frame["top"].value_counts().head(12).to_dict())
    print("top-ranked group:", frame["top_group"].value_counts().to_dict())
    print("best crop outside the top group when forage wins:",
          frame["top_non_forage"].value_counts().head(12).to_dict())  # fmt: skip
    for column in ("field_gaps", "intended_gaps"):
        counts = Counter(code for codes in frame[column] for code in codes)
        print(
            column, {code: f"{count / n:.0%}" for code, count in counts.most_common(14)}
        )
    print(f"weather record: {(frame['weather_seasons'] > 0).mean():.1%} of fields, "
          f"median {frame['weather_seasons'].median():.0f} seasons")  # fmt: skip
    print("off-season slot:", frame["off_season_status"].value_counts(normalize=True).round(3).to_dict())  # fmt: skip
    for column in sorted(c for c in frame if c.startswith("off_season_") and c[11:] not in ("status", "after", "seeding_doy")):  # fmt: skip
        print(
            f"  {column[11:]}:",
            frame[column].value_counts(normalize=True).round(3).to_dict(),
        )
    print(f"rules that fired at least once: {len(table)}; top 12 on the intended crop:")
    print(table.head(12).to_string())


if __name__ == "__main__":
    main()
