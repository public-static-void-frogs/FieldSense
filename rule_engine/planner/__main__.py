"""Plan a rotation for one field of the national sample and print it as JSON.

    python -m rule_engine.planner --field 191825000034355 \
        --fields data/local/usa_sample/fields.jsonl \
        --summaries data/local/usa_sample/season_summary data/local/planner/season_summary \
        --horizon 5 --priorities soil --q-learning 20000
"""

import argparse
import json

from rule_engine import build_advisor
from rule_engine.planner import (
    Persistence,
    RotationModel,
    Weights,
    build_context,
    evaluate,
    exact_plan,
    fixed_rotation,
    myopic,
    open_loop_plan,
    q_learning,
    read_fields,
    state_reference_aws,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--field", required=True, help="field id in the fields file")
    parser.add_argument("--fields", required=True, help="fields.jsonl (engine field records)")
    parser.add_argument("--summaries", nargs="*", default=[], help="season summary roots")
    parser.add_argument("--crops", nargs="*")
    parser.add_argument("--priorities", nargs="*", default=[])
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--risk-usd-per-point", type=float, default=Weights.risk_usd_per_point)
    parser.add_argument("--soil-usd-per-t-c", type=float, default=Weights.soil_usd_per_t_c)
    parser.add_argument("--risk-aversion", type=float, default=0.0)
    parser.add_argument("--cover-cost-share", type=float, default=0.0)
    parser.add_argument(
        "--persistence",
        type=float,
        default=1.0,
        help="carry-over between years: 0 = independent years, 1 = analog years only",
    )
    parser.add_argument("--bandwidth", type=float, default=1.0, help="analog kernel width, in sd")
    parser.add_argument("--policy", help="policy.pt from scripts/train_policy.py (needs PyTorch)")
    parser.add_argument("--q-learning", type=int, default=0, metavar="EPISODES")
    args = parser.parse_args()

    advisor = build_advisor()
    fields = read_fields(args.fields)
    record = fields[args.field]
    reference = state_reference_aws(fields).get(record.get("stateFips"))
    context = build_context(record, advisor, args.summaries, reference)
    model = RotationModel(
        context,
        advisor,
        crops=tuple(args.crops) if args.crops else None,
        priorities=tuple(args.priorities),
        horizon=args.horizon,
        weights=Weights(
            args.risk_usd_per_point,
            args.soil_usd_per_t_c,
            args.risk_aversion,
            args.cover_cost_share,
        ),
        persistence=Persistence(args.persistence, args.bandwidth),
    )
    best = exact_plan(model)
    fixed = open_loop_plan(model)
    phases = (("corn", "soybeans"), ("soybeans", "corn"))
    compared = [
        fixed,
        myopic(model),
        fixed_rotation(model, ("corn",), "conventional", "none"),
        # A two-year rotation is scored from whichever phase follows the field's history better.
        *(
            max(
                (fixed_rotation(model, phase, tillage, cover) for phase in phases),
                key=lambda plan: plan.value,
            )
            for tillage, cover in (("conventional", "none"), ("no_till", "rye"))
        ),
    ]
    if args.policy:
        from rule_engine.planner.ppo import LearnedPolicy

        learned = LearnedPolicy.load(args.policy)
        compared.insert(0, evaluate(model, learned.act_for(model), "learned_policy_ppo"))
    if args.q_learning:
        compared.insert(0, q_learning(model, episodes=args.q_learning)[0])
    print(
        json.dumps(
            {
                "fieldId": str(record["id"]),
                "region": context.region,
                "history": list(context.history),
                "historySource": context.history_source,
                "yearsDrawn": [y.year for y in model.years],
                "crops": list(model.crops),
                "units": "USD per acre, land cost excluded",
                "yearCarryOver": model.chain.describe() if model.chain else None,
                "plan": best.to_dict(),
                "valueOfAdaptingUsdPerAcre": round(best.value - fixed.value, 2),
                "comparison": [
                    {
                        "method": p.method,
                        "expectedTotalUsdPerAcre": round(p.value, 2),
                        "sequence": [a.label() for a in p.actions],
                    }
                    for p in compared
                    if all(a.crop in model.crops for a in p.actions)
                ],
                "dataGaps": model.gaps,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
