"""Which sampled field stands in for a field that has no season summaries of its own.

The national sample holds one field per gridMET weather cell (1/24 degree, about 4 km) and
county. Weather, drought and county yield of a season summary are the same for every field of
that cell and county, so any other field there can read the sampled field's summaries. Its crop
history and soil stay its own.

The index is <data root>/summary_index.parquet with CSBID, county_fips (5 digits), ix, iy.
"""

from dataclasses import dataclass
from math import cos, floor, hypot, radians
from pathlib import Path

WEST, NORTH, PER_DEGREE = -124.7875, 49.4208, 24  # gridMET grid: edge of cell 0 and cells/degree
CELL_KM = 111.2 / PER_DEGREE
MAX_NEARBY_KM = 40.0  # farther than this the weather is not the field's weather


@dataclass(frozen=True)
class SummaryTwin:
    csbid: str
    county_fips: str
    source: str  # own | weather_cell | nearby_cell
    distance_km: float  # between cell centres; 0 in the same cell


def cell(longitude: float, latitude: float) -> tuple[int, int]:
    return floor((longitude - WEST) * PER_DEGREE), floor((NORTH - latitude) * PER_DEGREE)


class CellIndex:
    """Lookup of the sampled field of a weather cell. Loaded once; about 360,000 rows."""

    def __init__(self, path: Path | str | None):
        self.path = Path(path) if path else None
        self._own: dict[str, str] | None = None
        self._by_county: dict[str, list[tuple[int, int, str]]] = {}

    def available(self) -> bool:
        return self.path is not None and self.path.exists()

    def _load(self) -> None:
        import duckdb

        self._own = {}
        rows = duckdb.connect().execute(
            "SELECT CSBID, county_fips, ix, iy FROM read_parquet(?)", [str(self.path)]
        )
        for csbid, county, ix, iy in rows.fetchall():
            self._own[csbid] = county
            self._by_county.setdefault(county, []).append((ix, iy, csbid))

    def twin(
        self,
        csbid: str | None,
        county_fips: str | None,
        longitude: float | None,
        latitude: float | None,
    ) -> SummaryTwin | None:
        """The field whose summaries to read, or None when the sample has nothing close enough."""
        if not self.available():
            return None
        if self._own is None:
            self._load()
        if csbid and csbid in self._own:
            return SummaryTwin(csbid, self._own[csbid], "own", 0.0)
        if county_fips is None or longitude is None or latitude is None:
            return None
        ix, iy = cell(longitude, latitude)
        east_west = cos(radians(latitude))
        best = None
        for jx, jy, other in self._by_county.get(county_fips, ()):
            distance = hypot((jx - ix) * east_west, jy - iy) * CELL_KM
            if best is None or (distance, other) < best:
                best = (distance, other)
        if best is None or best[0] > MAX_NEARBY_KM:
            return None
        distance, other = best
        source = "weather_cell" if distance == 0 else "nearby_cell"
        return SummaryTwin(other, county_fips, source, round(distance, 1))
