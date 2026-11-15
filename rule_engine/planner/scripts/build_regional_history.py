"""Regional yield series, the fallback for a state that publishes no yield of its own.

    python rule_engine/planner/scripts/build_regional_history.py

NASS publishes no state yield for some crops in some states: corn for grain in the New England
states and Nevada (they report silage only), and Iowa sorghum, Delaware and Maryland sorghum, Utah
oats and others stopped years ago. The planner then reads the yield level of the state's USDA ERS
farm resource region (data/ers_regions.csv), and of the United States when the region has none.

For each crop, year and ERS region the value is the unweighted mean of the NASS state yields of
the region's states that published that year. A state belongs to the region that holds the most
of its counties. A year needs at least MIN_STATES states, and the unit and NASS series description
must be those of the crop's first row. Reads data/nass_long_history.csv, writes
data/nass_regional_history.csv with `geography` "ERS:<region>" and the number of states averaged
in `n_states`.
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from rule_engine.regions import STATE_FIPS  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
MIN_STATES = 2
COLUMNS = ["kind", "crop", "geography", "year", "value", "unit", "nass_short_desc", "n_states"]


def state_regions(county_rows) -> dict[str, str]:
    """{state letters: the ERS region holding most of its counties}."""
    count: dict[str, Counter] = defaultdict(Counter)
    for row in county_rows:
        state = STATE_FIPS.get(row["county_fips"][:2])
        if state:
            count[state][row["region"]] += 1
    return {state: regions.most_common(1)[0][0] for state, regions in count.items()}


def regional_rows(history_rows, regions: dict[str, str], kind: str = "yield") -> list[list]:
    """Rows of the regional mean series of `kind`, from the state rows of the long history."""
    values: dict[tuple, dict[str, float]] = defaultdict(dict)
    series: dict[str, tuple[str, str]] = {}  # crop -> (unit, NASS description)
    for row in history_rows:
        state = row["geography"]
        if row["kind"] != kind or state not in regions:
            continue
        name = (row["unit"], row["nass_short_desc"])
        if series.setdefault(row["crop"], name) != name:
            continue
        values[(row["crop"], regions[state], int(row["year"]))][state] = float(row["value"])
    out = []
    for (crop, region, year), states in sorted(values.items()):
        if len(states) < MIN_STATES:
            continue
        unit, desc = series[crop]
        mean = sum(states.values()) / len(states)
        out.append([kind, crop, f"ERS:{region}", year, round(mean, 4), unit, desc, len(states)])
    return out


def main() -> None:
    with (DATA / "ers_regions.csv").open(newline="") as handle:
        regions = state_regions(csv.DictReader(handle))
    with (DATA / "nass_long_history.csv").open(newline="") as handle:
        rows = regional_rows(csv.DictReader(handle), regions)
    out = DATA / "nass_regional_history.csv"
    with out.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    print(f"wrote {out}: {len(rows)} rows, {len({(r[1], r[2]) for r in rows})} crop-region series")


if __name__ == "__main__":
    main()
