"""Tabulate the planning problem of every sample field (see planner/tabular.py), in parallel.

    python rule_engine/planner/scripts/build_tables.py \
        --fields data/local/usa_sample/fields.jsonl \
        --summaries data/local/usa_sample/season_summary data/local/planner/season_summary \
        --out data/local/planner/tables --workers 14

Fields are processed in a fixed random order and written in shards of `--shard` fields
(`tables_0000.pkl`, ...), so a partial run is still a random sample. Fields where fewer than two
crops can be modelled are skipped: there is nothing to decide.
"""

import argparse
import pickle
import random
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from rule_engine import build_advisor  # noqa: E402
from rule_engine.planner import (  # noqa: E402
    RotationModel,
    build_context,
    read_fields,
    state_reference_aws,
)
from rule_engine.planner.tabular import tabulate  # noqa: E402

SHARED: dict = {}


def work(field_id: str):
    record = SHARED["fields"][field_id]
    try:
        context = build_context(
            record,
            SHARED["advisor"],
            SHARED["summaries"],
            SHARED["reference"].get(record.get("stateFips")),
        )
        model = RotationModel(context, SHARED["advisor"], horizon=SHARED["horizon"])
        if len(model.crops) < 2:
            return field_id, "fewer_than_two_crops", None
        return field_id, "ok", tabulate(model)
    except Exception as error:  # one bad field must not stop the run
        return field_id, f"error: {type(error).__name__}: {error}"[:120], None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fields", required=True)
    parser.add_argument("--summaries", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--shard", type=int, default=500)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fields = read_fields(args.fields)
    SHARED.update(
        fields=fields,
        advisor=build_advisor(),
        summaries=args.summaries,
        reference=state_reference_aws(fields),
        horizon=args.horizon,
    )
    ids = sorted(fields)
    random.Random(0).shuffle(ids)
    ids = ids[: args.limit] if args.limit else ids

    status: Counter = Counter()
    shard, written, started = [], 0, time.time()

    def flush() -> None:
        nonlocal shard, written
        if shard:
            with (out / f"tables_{written:04d}.pkl").open("wb") as handle:
                pickle.dump(shard, handle, protocol=pickle.HIGHEST_PROTOCOL)
            written += 1
            shard = []

    with Pool(args.workers) as pool:  # fork: the workers share the loaded fields and advisor
        for done, (_, state, table) in enumerate(pool.imap_unordered(work, ids, 8), 1):
            status[state.split(":")[0] if state.startswith("error") else state] += 1
            if state.startswith("error") and status["error"] <= 5:
                print(state, flush=True)
            if table is not None:
                shard.append(table)
                if len(shard) >= args.shard:
                    flush()
            if done % 250 == 0:
                rate = done / (time.time() - started)
                print(f"{done}/{len(ids)} fields, {rate:.1f}/s, {dict(status)}", flush=True)
    flush()
    print(f"done: {dict(status)}, {written} shards in {out}")


if __name__ == "__main__":
    main()
