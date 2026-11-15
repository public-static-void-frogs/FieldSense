"""Regional production costs from the USDA ERS commodity costs and returns tables.

    python rule_engine/planner/scripts/build_regional_costs.py --ers <folder with the ERS csv files>

The files are the "recent" cost-and-returns tables per commodity (corn.csv, soybeans.csv,
wheat.csv, sorghum.csv, oats.csv, barley.csv, cotton.csv, rice.csv, peanuts.csv) from
https://www.ers.usda.gov/data-products/commodity-costs-and-returns. Writes
rule_engine/planner/data/costs_regional.csv: for each crop and ERS farm resource region, the
latest year's "Total, costs listed" less "Opportunity cost of land", in USD per planted acre.
That is the same cost concept as the ISU budgets in costs.csv (machinery and labour included,
land excluded). ERS reports wheat as one commodity; the same row serves winter, spring and durum
wheat. A class's row is verified where the ERS survey's own class mix ("percent of acres") gives
that class at least MIN_CLASS_SHARE of the region's wheat acres; elsewhere (and where ERS gives no
mix) it is an extrapolation. Within a region the classes cost about the same: the NDSU 2025 North
Central ND budgets differ by 6 % between durum and hard red spring wheat (282.60 and 266.52 USD
per acre, land excluded), less than the ERS-to-extension gap, so no class factor is applied.

Also writes data/costs_regional_history.csv: every year (1996 on for most crops), with the cost
split into the groups a farmer budgets by, and the opportunity cost of land in its own column.
The calculator defaults and the backtest read it.
"""

import argparse
import csv
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "costs_regional.csv"
FILES = {
    "corn": ("corn",),
    "soybeans": ("soybeans",),
    "wheat": ("winter_wheat", "spring_wheat", "durum_wheat"),
    "sorghum": ("sorghum",),
    "oats": ("oats",),
    "barley": ("barley",),
    "cotton": ("cotton",),
    "rice": ("rice",),
    "peanuts": ("peanuts",),
}
URL = "https://www.ers.usda.gov/data-products/commodity-costs-and-returns"
WHEAT_CLASS = {"winter_wheat": "Winter wheat", "spring_wheat": "Spring wheat",
               "durum_wheat": "Durum wheat"}  # fmt: skip
MIN_CLASS_SHARE = 5.0  # percent of the region's wheat acres in the ERS survey
HISTORY = OUT.with_name("costs_regional_history.csv")
# budget group -> ERS items; what is left of the operating costs goes to other_operating
GROUPS = {
    "seed": ("Seed",),
    "fertilizer": ("Fertilizer",),
    "chemicals": ("Chemicals",),
    "labor": ("Hired labor", "Opportunity cost of unpaid labor"),
    "machinery": ("Capital recovery of machinery and equipment",),
    "overhead": ("Taxes and insurance", "General farm overhead"),
}
OPERATING = ("seed", "fertilizer", "chemicals")
COLUMNS = ("seed", "fertilizer", "chemicals", "other_operating", "labor", "machinery", "overhead")


def history_rows(crops: tuple[str, ...], rows: list[dict]) -> list[list]:
    """One row per crop, region and year: the cost groups, land, and the total without land."""
    found: dict[tuple[str, int], dict[str, float]] = {}
    for r in rows:
        if r["Year"].isdigit() and r["Units"] == "dollars per planted acre":
            found.setdefault((r["Region"], int(r["Year"])), {})[r["Item"].strip()] = float(
                r["Value"]
            )
    out = []
    for (region, year), items in sorted(found.items()):
        if "Total, costs listed" not in items or "Total, operating costs" not in items:
            continue
        group = {name: sum(items.get(i, 0.0) for i in parts) for name, parts in GROUPS.items()}
        group["other_operating"] = items["Total, operating costs"] - sum(
            group[name] for name in OPERATING
        )
        land = items.get("Opportunity cost of land", 0.0)
        total = items["Total, costs listed"] - land
        for crop in crops:
            out.append(
                [crop, region, year]
                + [f"{group[name]:.2f}" for name in COLUMNS]
                + [f"{land:.2f}", f"{total:.2f}"]
            )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ers", required=True)
    args = parser.parse_args()
    out, history = [], []
    for name, crops in FILES.items():
        with (Path(args.ers) / f"{name}.csv").open(newline="", encoding="latin1") as handle:
            rows = list(csv.DictReader(handle))
        history += history_rows(crops, rows)
        year = max(int(r["Year"]) for r in rows if r["Year"].isdigit())
        found: dict[str, dict[str, float]] = {}
        shares: dict[str, dict[str, float]] = {}
        for r in rows:
            if r["Year"] == str(year) and r["Units"] == "dollars per planted acre":
                found.setdefault(r["Region"], {})[r["Item"].strip()] = float(r["Value"])
            elif r["Year"] == str(year) and r["Units"] == "percent of acres":
                shares.setdefault(r["Region"], {})[r["Item"].strip()] = float(r["Value"])
        for region, items in sorted(found.items()):
            total, land = items["Total, costs listed"], items["Opportunity cost of land"]
            for crop in crops:
                source = (
                    f"USDA ERS Commodity Costs and Returns, {name}, {region}, {year}: "
                    f"total costs listed {total:.2f} less opportunity cost of land {land:.2f}"
                )
                verified = "true"
                if crop in WHEAT_CLASS:  # one ERS wheat table stands in for all three classes
                    share = shares.get(region, {}).get(WHEAT_CLASS[crop])
                    verified = "true" if share is not None and share >= MIN_CLASS_SHARE else "false"
                    mix = "no class mix reported" if share is None else f"{share:g} % of acres"
                    source += f"; {WHEAT_CLASS[crop].lower()} in the ERS sample: {mix}"
                out.append([crop, region, f"{total - land:.2f}", year, verified, source, URL])
    with OUT.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["crop", "region", "usd_per_acre", "year", "verified", "source", "url"])
        writer.writerows(out)
    print(f"wrote {OUT}: {len(out)} rows")
    with HISTORY.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["crop", "region", "year", *COLUMNS, "land", "usd_per_acre"])
        writer.writerows(history)
    print(f"wrote {HISTORY}: {len(history)} rows")


if __name__ == "__main__":
    main()
