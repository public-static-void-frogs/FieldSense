"""Further SSURGO map-unit properties from USDA NRCS Soil Data Access, one row per map unit.

    python rule_engine/planner/scripts/fetch_soil_extra.py --mukeys <csv with a mukey column> \
        --out <mukey_extra.csv>

Per map unit (mukey):
    nccpi_all, nccpi_corn, nccpi_soy, nccpi_small_grains
        National Commodity Crop Productivity Index 3.0 (0-1), mean of the major components
        weighted by their share of the map unit
    bedrock_depth_cm      shallowest depth to bedrock in the map unit (muaggatt.brockdepmin)
    restriction_depth_cm  shallowest root-restricting layer of the major components
    water_table_cm        shallowest water table depth, April-June (muaggatt.wtdepaprjunmin)
    flooding              dominant flooding frequency class (muaggatt.flodfreqdcd)
    ponding_pct           share of the map unit with ponding (muaggatt.pondfreqprs)
    aws_150cm_mm          available water storage to 150 cm

Resumable: map units already in --out are skipped. The service is anonymous.
"""

import argparse
import csv
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
NCCPI = "NCCPI - National Commodity Crop Productivity Index (Ver 3.0)"
SUBMODELS = {
    "nccpi_all": NCCPI,
    "nccpi_corn": "NCCPI - NCCPI Corn Submodel (I)",
    "nccpi_soy": "NCCPI - NCCPI Soybeans Submodel (I)",
    "nccpi_small_grains": "NCCPI - NCCPI Small Grains Submodel (II)",
}
FIELDS = [
    "mukey",
    *SUBMODELS,
    "bedrock_depth_cm",
    "restriction_depth_cm",
    "water_table_cm",
    "flooding",
    "ponding_pct",
    "aws_150cm_mm",
]


def sda(query: str, timeout: float = 120.0) -> list[dict]:
    body = json.dumps({"format": "JSON+COLUMNNAME", "query": query}).encode()
    request = urllib.request.Request(
        SDA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                table = json.load(response).get("Table") or []
            return [dict(zip(table[0], row, strict=True)) for row in table[1:]]
        except OSError:
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))
    return []


def fetch(keys: list[str]) -> list[dict]:
    inside = ",".join(f"'{int(k)}'" for k in keys)
    out = {k: {"mukey": k} for k in keys}
    for row in sda(f"""
        SELECT mukey, brockdepmin, wtdepaprjunmin, flodfreqdcd, pondfreqprs, aws0150wta
        FROM muaggatt WHERE mukey IN ({inside})"""):
        out[row["mukey"]].update(
            bedrock_depth_cm=row["brockdepmin"],
            water_table_cm=row["wtdepaprjunmin"],
            flooding=row["flodfreqdcd"],
            ponding_pct=row["pondfreqprs"],
            aws_150cm_mm=None
            if row["aws0150wta"] is None
            else round(float(row["aws0150wta"]) * 10, 1),
        )
    pivots = ", ".join(
        f"SUM(CASE WHEN ci.rulename = '{rule}' THEN ci.interphr * c.comppct_r END) / "
        f"NULLIF(SUM(CASE WHEN ci.rulename = '{rule}' THEN c.comppct_r END), 0) AS {name}"
        for name, rule in SUBMODELS.items()
    )
    for row in sda(f"""
        SELECT c.mukey, {pivots}
        FROM component c JOIN cointerp ci ON ci.cokey = c.cokey
        WHERE c.mukey IN ({inside}) AND c.majcompflag = 'Yes' AND ci.mrulename = '{NCCPI}'
        GROUP BY c.mukey"""):
        for name in SUBMODELS:
            if row[name] is not None:
                out[row["mukey"]][name] = round(float(row[name]), 3)
    for row in sda(f"""
        SELECT c.mukey, MIN(r.resdept_r) AS depth
        FROM component c JOIN corestrictions r ON r.cokey = c.cokey
        WHERE c.mukey IN ({inside}) AND c.majcompflag = 'Yes' GROUP BY c.mukey"""):
        out[row["mukey"]]["restriction_depth_cm"] = row["depth"]
    return list(out.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mukeys", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--batch", type=int, default=250)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    with args.mukeys.open(newline="") as handle:
        wanted = sorted(
            {r["mukey"] for r in csv.DictReader(handle) if r["mukey"].strip().isdigit()}
        )
    done = set()
    if args.out.exists():
        with args.out.open(newline="") as handle:
            done = {r["mukey"] for r in csv.DictReader(handle)}
    todo = [k for k in wanted if k not in done]
    batches = [todo[i : i + args.batch] for i in range(0, len(todo), args.batch)]
    print(
        f"{len(wanted):,} map units, {len(todo):,} to fetch in {len(batches)} batches", flush=True
    )
    with args.out.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if not done:
            writer.writeheader()
        with ThreadPoolExecutor(args.workers) as pool:
            for i, rows in enumerate(pool.map(fetch, batches), start=1):
                writer.writerows(rows)
                handle.flush()
                if i % 10 == 0 or i == len(batches):
                    print(f"  batches {i}/{len(batches)}", flush=True)


if __name__ == "__main__":
    main()
