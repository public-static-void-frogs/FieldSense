"""Yield lost in a season a weather hazard hits, per rule and crop, from the regional panel.

    python rule_engine/planner/scripts/regional_hazard_panel.py --root <sample> --out <dir>
    python rule_engine/scripts/build_hazard_yield_loss.py <dir>/result.json

Writes rule_engine/data/hazard_yield_loss.csv (rule, crop, loss, se, county_years, counties,
sample, finding). The engine multiplies `loss` by how often the hazard hits the field to get the
expected loss per season, which sets the risk level (engine.EXPECTED_LOSS_BANDS).

The panel estimate is the change in NASS county yield when every field of the county is hit
(county effects, state trends, standard errors clustered by year). It is an association in
county yields, not a field trial. What is kept:

- the "dryland" row (counties with under 10 % of the crop irrigated) for a rule that is switched
  off on mostly irrigated crops (`unless county.irrigated_share`), the "all" row otherwise;
- a loss at least two standard errors below zero: `loss` is that loss (finding "loss");
- no such loss and a standard error of at most 5 points: `loss` is 0 (finding "no_loss_found");
- anything less precise is left out, and the engine then grades that rule and crop by how often
  the hazard hits, never above "medium".
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rule_engine.catalog import load_catalog  # noqa: E402
from rule_engine.rules import applies, load_rules  # noqa: E402

OUT = ROOT / "rule_engine" / "data" / "hazard_yield_loss.csv"
GATE_FACT = "county.irrigated_share"
MAX_SE_FOR_NO_LOSS = 5.0  # percentage points


def main() -> None:
    panel = json.loads(Path(sys.argv[1]).read_text())
    catalog = load_catalog()
    rows = []
    for rule in load_rules().rules:
        if not rule.hazard:
            continue
        gated = any(c.fact == GATE_FACT for c in rule.unless)
        for crop in catalog.crops.values():
            found = panel.get(f"{rule.id}/{crop.id}")
            if not found or not applies(rule, crop, catalog):
                continue
            sample = "dryland" if gated and found.get("dryland") else "all"
            est = found.get(sample) or {}
            if "loss_pct_all_hit" not in est:
                continue
            change, se = est["loss_pct_all_hit"], est["se_pct"]
            if change <= -2 * se:
                loss, finding = -change / 100, "loss"
            elif se <= MAX_SE_FOR_NO_LOSS:
                loss, finding = 0.0, "no_loss_found"
            else:
                continue
            rows.append(
                {
                    "rule": rule.id,
                    "crop": crop.id,
                    "loss": round(loss, 3),
                    "se": round(se / 100, 3),
                    "county_years": est["county_years"],
                    "counties": est["counties"],
                    "sample": sample,
                    "finding": finding,
                }
            )
    with OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(len(rows), "rows ->", OUT)


if __name__ == "__main__":
    main()
