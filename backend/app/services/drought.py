"""Current drought status of a field's county from the U.S. Drought Monitor.

The USDM publishes a weekly map; its data service reports, for each county, the share of the
county area in each drought category. Categories are cumulative: ``d2`` is the share of the area
in D2 (severe) or worse. Only U.S. counties are covered, so a point elsewhere has no status.
The county comes from the FCC census block lookup that ``soil_depletion.py`` also uses.
"""

import logging
from datetime import date, datetime, timedelta
from threading import Lock
from time import monotonic

import httpx

logger = logging.getLogger(__name__)

FCC_URL = "https://geo.fcc.gov/api/census/block/find"
USDM_URL = "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent"
CATEGORIES = ("d0", "d1", "d2", "d3", "d4")
NAMES = {
    "d0": "Abnormally dry",
    "d1": "Moderate drought",
    "d2": "Severe drought",
    "d3": "Extreme drought",
    "d4": "Exceptional drought",
}
WEEKS_BACK = 5
MIN_SHARE = 30.0  # percent of the county area a category must cover to count as "the" category
TTL_SECONDS = 6 * 3600  # the map changes once a week


class DroughtUnavailable(Exception):
    """The drought service could not be reached or returned something unusable."""


def dominant(row: dict) -> str | None:
    """The worst category covering at least MIN_SHARE percent of the county, if any."""
    found = [name for name in CATEGORIES if (row.get(name) or 0) >= MIN_SHARE]
    return found[-1] if found else None


class DroughtMonitor:
    def __init__(self, client: httpx.Client | None = None, clock=monotonic):
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(8, connect=3), headers={"User-Agent": "FieldShiftNASA/1.0"}
        )
        self.clock = clock
        self._lock = Lock()
        self._counties: dict[tuple[float, float], tuple[str, str]] = {}
        self._cache: dict[str, tuple[float, list[dict]]] = {}

    def close(self):
        self.client.close()

    def county(self, lat: float, lng: float) -> tuple[str, str] | None:
        """(county FIPS, county name) of a point, or None outside the United States."""
        key = (round(lat, 2), round(lng, 2))
        with self._lock:
            if key in self._counties:
                return self._counties[key]
        try:
            response = self.client.get(
                FCC_URL, params={"latitude": lat, "longitude": lng, "format": "json"}
            )
            response.raise_for_status()
            county = response.json().get("County") or {}
        except (httpx.HTTPError, ValueError) as error:
            raise DroughtUnavailable("County lookup failed") from error
        found = (county["FIPS"], county.get("name") or "") if county.get("FIPS") else None
        with self._lock:
            self._counties[key] = found
        return found

    def weeks(self, fips: str, today: date) -> list[dict]:
        """Weekly category shares for the county, oldest first."""
        with self._lock:
            cached = self._cache.get(fips)
            if cached and cached[0] > self.clock():
                return cached[1]
        start = today - timedelta(weeks=WEEKS_BACK)
        try:
            response = self.client.get(
                USDM_URL,
                params={
                    "aoi": fips,
                    "startdate": f"{start.month}/{start.day}/{start.year}",
                    "enddate": f"{today.month}/{today.day}/{today.year}",
                    "statisticsType": 1,  # cumulative: d2 includes D3 and D4
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            rows = response.json()
            weeks = sorted(
                (
                    {
                        "mapDate": datetime.fromisoformat(row["mapDate"]).date().isoformat(),
                        **{name: float(row[name]) for name in CATEGORIES},
                    }
                    for row in rows
                ),
                key=lambda week: week["mapDate"],
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise DroughtUnavailable("Drought Monitor request failed") from error
        with self._lock:
            self._cache[fips] = (self.clock() + TTL_SECONDS, weeks)
        return weeks

    def status(self, lat: float, lng: float, today: date) -> dict | None:
        """Latest weekly map for the county of the point plus the change over the last weeks.

        None when the point is not in a U.S. county or the Monitor has no map for it.
        """
        county = self.county(lat, lng)
        if county is None:
            return None
        weeks = self.weeks(county[0], today)
        if not weeks:
            return None
        latest, earliest = weeks[-1], weeks[0]
        current, before = dominant(latest), dominant(earliest)
        rank = {None: -1, **{name: index for index, name in enumerate(CATEGORIES)}}
        trend = "steady"
        if rank[current] > rank[before]:
            trend = "worsening"
        elif rank[current] < rank[before]:
            trend = "improving"
        return {
            "county": county[1],
            "fips": county[0],
            "mapDate": latest["mapDate"],
            "category": current,
            "shares": {name: latest[name] for name in CATEGORIES},
            "weeksCompared": len(weeks),
            "trend": trend,
        }
