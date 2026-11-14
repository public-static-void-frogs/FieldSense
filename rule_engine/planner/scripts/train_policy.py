"""Train one rotation policy across the tabulated fields and score it on held-out counties.

    python rule_engine/planner/scripts/train_policy.py \
        --tables data/local/planner/tables --out data/local/planner/policy

Writes `policy.pt` and `report.json` (exact plan values of the learned policy, the optimum and
the myopic rule on the held-out fields and on the training fields).
"""

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from rule_engine.planner.ppo import (  # noqa: E402
    Config,
    FieldSet,
    LearnedPolicy,
    benchmark,
    is_test_county,
    train,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tables", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--iterations", type=int, default=Config.iterations)
    parser.add_argument("--envs", type=int, default=Config.envs)
    parser.add_argument("--hidden", type=int, default=Config.hidden)
    parser.add_argument("--entropy", type=float, default=Config.entropy)
    parser.add_argument("--lr", type=float, default=Config.lr)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--watch", type=int, default=300, help="held-out fields scored in the log")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    tables = []
    for path in sorted(Path(args.tables).glob("tables_*.pkl")):
        with path.open("rb") as handle:
            tables += pickle.load(handle)
    held = [t for t in tables if is_test_county(t.county)]
    seen = [t for t in tables if not is_test_county(t.county)]
    print(f"{len(seen)} training fields, {len(held)} held-out fields in other counties")

    data = FieldSet(seen, args.device)
    test = FieldSet(held, args.device)
    watch = FieldSet(held[: args.watch], args.device)
    config = Config(
        envs=args.envs,
        iterations=args.iterations,
        hidden=args.hidden,
        entropy=args.entropy,
        lr=args.lr,
        seed=args.seed,
    )
    started = time.time()
    net = train(data, config, watch)
    minutes = (time.time() - started) / 60

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    LearnedPolicy(net).save(out / "policy.pt")
    report = {
        "trainingFields": len(seen),
        "heldOutFields": len(held),
        "trainingMinutes": round(minutes, 1),
        "plansSampled": config.envs * config.iterations,
        "config": config.__dict__,
        "heldOut": benchmark(net.to(args.device), test),
        "training": benchmark(net, FieldSet(seen[:2000], args.device)),
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
