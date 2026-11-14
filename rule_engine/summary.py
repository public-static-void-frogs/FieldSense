"""Read weekly-binned season summaries per field and the long weather record per grid node.

Field summaries are built by scripts/build_season_summary.py, the weather record by
scripts/build_climate_record.py.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

WEEK0_DOY = 91
WEEKS = 31
SCALAR_KEYS = (
    "centroid_lon",
    "centroid_lat",
    "area_acres",
    "yield_corn_bu_ac",
    "yield_corn_lag1_bu_ac",
    "yield_corn_prev3_bu_ac",
    "yield_soy_bu_ac",
    "yield_soy_lag1_bu_ac",
    "yield_soy_prev3_bu_ac",
    "rma_lag1_total_usd",
    "rma_lag1_drought_share",
    "rma_lag1_excess_moisture_share",
    "rma_lag1_heat_share",
    "rma_lag1_freeze_share",
    "rma_lag1_hail_share",
)


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


@dataclass(frozen=True)
class SeasonSummary:
    csbid: str
    county_fips: str
    year: int
    cdl_prev1: int | None
    cdl_prev2: int | None
    scalars: dict[str, float | None]
    weekly: dict[str, list]
    week0_doy: int = WEEK0_DOY  # day of year on which weekly bin 0 starts

    def window(
        self, metric: str, start_doy: int, end_doy: int, aggregate: Literal["sum", "min", "max"]
    ) -> float | None:
        """Aggregate a weekly metric over the weeks overlapping [start_doy, end_doy].

        Returns None when the metric is unknown or no overlapping week has data.
        """
        series = self.weekly.get(metric)
        if series is None:
            return None
        first = max(0, (start_doy - self.week0_doy) // 7)
        last = min(len(series) - 1, (end_doy - self.week0_doy) // 7)
        values = [_clean(v) for v in series[first : last + 1]]
        values = [v for v in values if v is not None]
        if not values:
            return None
        return {"sum": sum, "min": min, "max": max}[aggregate](values)


class SeasonSummaryStore:
    """Per-field access to summary parquets laid out as <root>/<year>/<county_fips>.parquet."""

    def __init__(self, root: Path | str | None):
        self.root = Path(root) if root else None

    def available(self) -> bool:
        return self.root is not None and self.root.exists()

    def seasons(self, csbid: str, county_fips: str) -> list[SeasonSummary]:
        if not self.available():
            return []
        files = sorted(self.root.glob(f"*/{county_fips}.parquet"))
        if not files:
            return []
        import duckdb

        paths = ", ".join(f"'{f}'" for f in files)
        con = duckdb.connect()
        rows = con.execute(
            f"SELECT * FROM read_parquet([{paths}]) WHERE csbid = ? ORDER BY year", [csbid]
        )
        columns = [d[0] for d in rows.description]
        out = []
        for record in rows.fetchall():
            row = dict(zip(columns, record))
            out.append(
                SeasonSummary(
                    csbid=row["csbid"],
                    county_fips=str(row["county_fips"]),
                    year=int(row["year"]),
                    cdl_prev1=_clean(row.get("cdl_prev1")),
                    cdl_prev2=_clean(row.get("cdl_prev2")),
                    scalars={k: _clean(row.get(k)) for k in SCALAR_KEYS},
                    weekly={k: list(v) for k, v in row.items() if isinstance(v, list)},
                )
            )
        return out


EARTH_RADIUS_KM = 6371.0


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class ClimateRecord:
    """The weather-only seasons of the grid node nearest to a point, oldest first."""

    seasons: tuple[SeasonSummary, ...]
    latitude: float
    longitude: float
    distance_km: float
    source: str

    @property
    def metrics(self) -> frozenset[str]:
        return frozenset(self.seasons[0].weekly) if self.seasons else frozenset()

    def describe(self) -> dict:
        return {
            "source": self.source,
            "seasons": len(self.seasons),
            "firstYear": self.seasons[0].year,
            "lastYear": self.seasons[-1].year,
            "nodeLatitude": self.latitude,
            "nodeLongitude": self.longitude,
            "distanceKm": round(self.distance_km, 1),
        }


class ClimateRecordStore:
    """Weekly weather per grid node for many years, laid out as <root>/iy=<row>/*.parquet.

    It holds weather only (no soil moisture, Drought Monitor, yields or crop labels) and covers
    the whole year, so it also answers questions about autumn and winter.
    """

    MAX_DISTANCE_KM = 30.0  # a node further away than this does not describe the field

    def __init__(self, root: Path | str | None):
        self.root = Path(root) if root else None
        self._grid: dict | None = None

    def available(self) -> bool:
        return self.root is not None and (self.root / "grid.json").exists()

    @property
    def grid(self) -> dict:
        if self._grid is None:
            self._grid = json.loads((self.root / "grid.json").read_text())
        return self._grid

    def record(self, latitude: float | None, longitude: float | None) -> ClimateRecord | None:
        if latitude is None or longitude is None or not self.available():
            return None
        grid = self.grid
        iy = round((latitude - grid["lat0"]) / grid["lat_step"])
        ix = round((longitude - grid["lon0"]) / grid["lon_step"])
        best = None
        # the nearest node first; on a coast it may be water, then the nearest neighbour is used
        for row in range(iy - 1, iy + 2):
            files = sorted((self.root / f"iy={row}").glob("*.parquet"))
            if not files:
                continue
            import duckdb

            paths = ", ".join(f"'{f}'" for f in files)
            rows = duckdb.connect().execute(
                f"SELECT * FROM read_parquet([{paths}]) WHERE ix BETWEEN ? AND ? ORDER BY year",
                [ix - 1, ix + 1],
            )
            columns = [d[0] for d in rows.description]
            nodes: dict[tuple[float, float], list[dict]] = {}
            for values in rows.fetchall():
                found = dict(zip(columns, values))
                nodes.setdefault((found["lat"], found["lon"]), []).append(found)
            for (lat, lon), years in nodes.items():
                distance = _distance_km(latitude, longitude, lat, lon)
                if best is None or distance < best[0]:
                    best = (distance, lat, lon, years)
        if best is None or best[0] > self.MAX_DISTANCE_KM:
            return None
        distance, lat, lon, years = best
        cell = f"{lat:+.2f}_{lon:+.2f}"
        seasons = tuple(
            SeasonSummary(
                csbid=cell,
                county_fips="",
                year=int(row["year"]),
                cdl_prev1=None,
                cdl_prev2=None,
                scalars={},
                weekly={k: list(v) for k, v in row.items() if isinstance(v, (list, tuple))},
                week0_doy=int(grid["week0_doy"]),
            )
            for row in years
        )
        return ClimateRecord(seasons, lat, lon, distance, grid["source"])
