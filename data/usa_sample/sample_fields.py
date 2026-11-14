"""Stream the `fields` COPY block of the pg dump (stdin) and write a stratified sample as CSV.
Only the fields table is read. Allocation: proportional to each state's field count, min 40."""

import collections
import csv
import json
import random
import sys

TOTAL, MIN_STATE, MIN_ACRES = int(sys.argv[2]), 40, 10.0
rng = random.Random(20261114)
res = collections.defaultdict(list)
seen = collections.Counter()
K = 1500
inside = False
for raw in sys.stdin.buffer:
    if not inside:
        inside = raw.startswith(b"COPY public.fields ")
        continue
    if raw.startswith(b"\\."):
        break
    c = raw.rstrip(b"\n").split(b"\t")
    if c[12] != b"interior_point" or c[6] == b"\\N":
        continue
    st = c[7].decode()
    try:
        acres = json.loads(c[4].decode().replace("\\\\", "\\"))["sourceProperties"][
            "CSBACRES"
        ]
    except (ValueError, KeyError, TypeError):  # row without a usable acreage
        continue
    if acres < MIN_ACRES:
        continue
    seen[st] += 1
    row = (
        c[6].decode(),
        st,
        c[8].decode(),
        c[9].decode(),
        round(acres, 2),
        float(c[10]),
        float(c[11]),
    )
    if len(res[st]) < K:
        res[st].append(row)
    else:
        j = rng.randrange(seen[st])
        if j < K:
            res[st][j] = row
tot = sum(seen.values())
alloc = {s: min(K, max(MIN_STATE, round(TOTAL * n / tot))) for s, n in seen.items()}
with open(sys.argv[1], "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(
        [
            "CSBID",
            "STATEFIPS",
            "CNTYFIPS",
            "CNTY",
            "CSBACRES",
            "centroid_lon",
            "centroid_lat",
        ]
    )
    for s in sorted(res):
        for row in sorted(rng.sample(res[s], min(alloc[s], len(res[s])))):
            w.writerow(row)
print(
    "eligible",
    tot,
    "written",
    sum(min(alloc[s], len(res[s])) for s in res),
    dict(sorted(alloc.items())),
)
