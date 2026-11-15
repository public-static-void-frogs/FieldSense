"""County mean of the NCCPI soil productivity index over the sampled CSB fields.

The sample is a draw of cropland fields, so the mean is the level of the county's cropland, the
level a county yield belongs to. Counties with fewer than MIN_FIELDS fields are left out.

    python rule_engine/planner/scripts/build_county_nccpi.py \
        --fields <sample>/soil_fields.csv --extra <sample>/cache/soil/mukey_extra.csv

`--fields` is a CSV with county_fips and mukey per field, or the sample's fields.jsonl. An
optional `weight` column counts a field that many times: the national sample keeps one field per
weather cell and county, so each is weighted by the CSB fields of its cell. Without it, thinly
farmed cells count as much as the dense cropland the county yield comes from.
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "county_nccpi.csv"
INDEXES = ("nccpi_corn", "nccpi_soy", "nccpi_small_grains", "nccpi_all")
MIN_FIELDS = 5


def field_rows(path: Path):
    if path.suffix == ".jsonl":
        with path.open() as handle:
            for line in handle:
                field = json.loads(line)
                mukey = (field.get("soil") or {}).get("mukey")
                if mukey:
                    yield field["countyFips"], str(mukey), 1.0
        return
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("mukey"):
                yield row["county_fips"].zfill(5), row["mukey"], float(row.get("weight") or 1)


def weighted_mean(rows: list[tuple[dict, float]], key: str) -> float | str:
    pairs = [(float(row[key]), weight) for row, weight in rows if row[key]]
    total = sum(weight for _, weight in pairs)
    return round(sum(v * w for v, w in pairs) / total, 3) if total else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fields", required=True, type=Path)
    parser.add_argument("--extra", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    with args.extra.open(newline="") as handle:
        extra = {row["mukey"]: row for row in csv.DictReader(handle)}
    counties: dict[str, list[tuple[dict, float]]] = defaultdict(list)
    for county, mukey, weight in field_rows(args.fields):
        row = extra.get(mukey)
        if row and row["nccpi_all"]:
            counties[county].append((row, weight))
    with args.out.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["county_fips", "fields", *INDEXES])
        for county in sorted(counties):
            rows = counties[county]
            if len(rows) < MIN_FIELDS:
                continue
            means = [weighted_mean(rows, k) for k in INDEXES]
            writer.writerow([county, len(rows), *means])
    print(f"{args.out}: {sum(len(v) >= MIN_FIELDS for v in counties.values()):,} counties")


if __name__ == "__main__":
    main()
