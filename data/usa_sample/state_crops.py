"""Which catalog crops are actually grown in each state: rule_engine/data/state_crops.csv.

Input: state_cdl_stats.parquet (STATEFIPS, cdl, fields, acres, year), counted over every field
of the national Crop Sequence Boundaries 2018-2025 for seasons 2021-2025. A catalog crop becomes
a candidate in a state when it holds at least --min-share of the state's CSB acres (mean of the
five seasons). CDL labels are satellite estimates, not farmer declarations.

Also prints the CDL codes the catalog does not know, by national acre share, so the next crops
to add are visible.

    python data/usa_sample/state_crops.py --stats data/local/usa_sample/state_cdl_stats.parquet
"""

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from rule_engine.catalog import NON_CANDIDATE_GROUPS, load_catalog
from rule_engine.regions import STATE_FIPS

OUT = REPO / "rule_engine" / "data" / "state_crops.csv"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--stats", required=True)
    parser.add_argument("--min-share", type=float, default=0.005)
    args = parser.parse_args()
    catalog = load_catalog()
    stats = pd.read_parquet(args.stats).dropna(subset=["cdl"])
    stats["cdl"] = stats["cdl"].astype(int)
    stats["region"] = stats["STATEFIPS"].astype(str).str.zfill(2).map(STATE_FIPS)
    stats["crop"] = stats["cdl"].map(
        lambda code: getattr(catalog.by_cdl(code), "id", None)
    )
    total = stats.groupby("region")["acres"].sum()
    by_crop = (
        stats.dropna(subset=["crop"])
        .groupby(["region", "crop"])["acres"]
        .sum()
        .reset_index()
    )
    by_crop["acre_share"] = by_crop["acres"] / by_crop["region"].map(total)
    candidate = by_crop["crop"].map(
        lambda c: catalog.crops[c].group.id not in NON_CANDIDATE_GROUPS
    )
    keep = by_crop[candidate & (by_crop["acre_share"] >= args.min_share)].sort_values(
        ["region", "acre_share"], ascending=[True, False]
    )
    with OUT.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["region", "crop", "acre_share", "source", "as_of"])
        for row in keep.itertuples():
            writer.writerow([
                row.region, row.crop, round(row.acre_share, 4),
                ("USDA NASS Crop Sequence Boundaries 2018-2025, CDL labels 2021-2025 "
                "(share of the state's CSB acres; satellite estimate)"),
                date.today().isoformat(),
            ])  # fmt: skip
    print(f"{OUT.name}: {len(keep)} rows, {keep['region'].nunique()} states")
    print(
        keep.groupby("crop")["region"]
        .nunique()
        .sort_values(ascending=False)
        .to_string()
    )

    national = stats.groupby(["cdl", "crop"], dropna=False)["acres"].sum().reset_index()
    national["share"] = national["acres"] / national["acres"].sum()
    known = national.dropna(subset=["crop"])["share"].sum()
    print(
        f"\ncatalog covers {known:.1%} of national CSB acre-years; largest unknown CDL codes:"
    )
    unknown = (
        national[national["crop"].isna()].sort_values("share", ascending=False).head(15)
    )
    print(unknown[["cdl", "share"]].to_string(index=False))


if __name__ == "__main__":
    main()
