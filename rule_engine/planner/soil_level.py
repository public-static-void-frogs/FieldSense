"""The field's yield level from its soil productivity index, when the farmer gave no yields.

A county yield is the level of the county's cropland. A field on better or poorer soil than that
cropland yields more or less. The measure is the NRCS National Commodity Crop Productivity Index
(NCCPI 3.0, 0 to 1), which SSURGO publishes per map unit with a corn and a soybean submodel.

    ratio = 1 + SLOPE[crop] * (field index - county mean index), kept within 1 +/- MAX_SHIFT

SLOPE is our own estimate, not a published one: across about 1,300 (corn) and 1,150 (soybeans)
counties, the 2015-2024 mean county yield relative to the state mean, regressed on the county
mean index relative to the state mean (sampled CSB fields, at least 5 per county). All states:
0.44 (90 % interval 0.37-0.52) for corn, 0.48 (0.41-0.55) for soybeans. Without the heavily
irrigated states the slopes are larger (0.70 and 0.58); the lower ones are used. The index alone
explains 10-12 % of the within-state yield differences, more than the other eight soil values
together (5-10 %). Depth to a restrictive layer adds a little; water table, flooding and ponding
frequency add nothing and are not used.

The slope is measured between counties and applied within one, which is an assumption: the
result is reported as unverified. County means come from data/county_nccpi.csv
(scripts/build_county_nccpi.py).
"""

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data"
INDEX = {"corn": "nccpi_corn", "soybeans": "nccpi_soy"}
SLOPE = {"corn": 0.44, "soybeans": 0.48}
MAX_SHIFT = 0.15


@dataclass(frozen=True)
class SoilLevel:
    index: str
    field: float
    county: float
    county_fields: int
    ratio: float


@lru_cache(maxsize=1)
def county_means() -> dict[str, dict]:
    path = DATA / "county_nccpi.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        return {row["county_fips"]: row for row in csv.DictReader(handle)}


def soil_level(crop: str, soil: dict | None, county_fips: str | None) -> SoilLevel | None:
    """None when the crop has no slope, the field no index or the county no mean."""
    index = INDEX.get(crop)
    county = county_means().get(str(county_fips or "").zfill(5))
    if index is None or not soil or county is None:
        return None
    here, mean = soil.get(index), county.get(index)
    if here is None or mean in (None, ""):
        return None
    shift = SLOPE[crop] * (float(here) - float(mean))
    ratio = 1.0 + max(-MAX_SHIFT, min(MAX_SHIFT, shift))
    return SoilLevel(index, float(here), float(mean), int(county["fields"]), ratio)
