"""USDA NASS Quick Stats access shared by the crop production and crop revenue services.

Quick Stats publishes survey yields, production, acres and prices as county, state and national
series. A free API key is needed (``NASS_API_KEY``). County lookups use the FCC census block API
and the crop at a point comes from the NASS CropScape service. Only U.S. locations are covered.
"""

import logging
import re
import time
from dataclasses import dataclass
from threading import Lock

import httpx

logger = logging.getLogger(__name__)

NASS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
FCC_URL = "https://geo.fcc.gov/api/census/block/find"
CROPSCAPE_URL = "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLValue"
HA_TO_ACRE = 2.471054
LB_TO_KG = 0.45359237


class NassUnavailable(Exception):
    """NASS data cannot be used: no key, a failed request or no matching series."""


@dataclass(frozen=True)
class Crop:
    cdl: int | None  # CropScape class code
    commodity: str
    unit: str  # native production unit: "bu" or "tons"
    lb_per_bu: float | None
    yield_desc: str
    prod_desc: str
    area_desc: str
    price_desc: str
    price_unit: str
    factor: float  # yield unit x price unit -> dollars
    days_to_harvest: int
    sale_months: tuple[int, ...]


def _grain(cdl, commodity, lb, label, days, months, **extra):
    return Crop(
        cdl=cdl,
        commodity=commodity,
        unit="bu",
        lb_per_bu=lb,
        yield_desc=f"{label} - YIELD, MEASURED IN BU / ACRE",
        prod_desc=f"{label} - PRODUCTION, MEASURED IN BU",
        area_desc=f"{label} - ACRES HARVESTED",
        price_desc=f"{label} - PRICE RECEIVED, MEASURED IN $ / BU",
        price_unit="$/bu",
        factor=1.0,
        days_to_harvest=days,
        sale_months=months,
        **extra,
    )


def _hay(cdl, label, price_desc_label):
    return Crop(
        cdl=cdl,
        commodity="HAY",
        unit="tons",
        lb_per_bu=None,
        yield_desc=f"{label} - YIELD, MEASURED IN TONS / ACRE",
        prod_desc=f"{label} - PRODUCTION, MEASURED IN TONS",
        area_desc=f"{label} - ACRES HARVESTED",
        price_desc=f"{price_desc_label} - PRICE RECEIVED, MEASURED IN $ / TON",
        price_unit="$/ton",
        factor=1.0,
        days_to_harvest=120,
        sale_months=(6, 7, 8, 9),
    )


SPRING_WHEAT = "WHEAT, SPRING, (EXCL DURUM)"
CROPS: dict[str, Crop] = {
    "corn": _grain(1, "CORN", 56.0, "CORN, GRAIN", 150, (10, 11, 12)),
    "soybeans": _grain(5, "SOYBEANS", 60.0, "SOYBEANS", 135, (10, 11, 12)),
    "winter wheat": _grain(24, "WHEAT", 60.0, "WHEAT, WINTER", 270, (7, 8, 9)),
    "spring wheat": _grain(23, "WHEAT", 60.0, SPRING_WHEAT, 120, (8, 9, 10)),
    "oats": _grain(28, "OATS", 32.0, "OATS", 105, (7, 8, 9)),
    "barley": _grain(21, "BARLEY", 48.0, "BARLEY", 105, (7, 8, 9)),
    "rye": _grain(27, "RYE", 56.0, "RYE", 270, (7, 8, 9)),
    # sorghum yield is in bushels but its price is in $ per cwt (56 lb per bushel)
    "sorghum": Crop(
        cdl=4,
        commodity="SORGHUM",
        unit="bu",
        lb_per_bu=56.0,
        yield_desc="SORGHUM, GRAIN - YIELD, MEASURED IN BU / ACRE",
        prod_desc="SORGHUM, GRAIN - PRODUCTION, MEASURED IN BU",
        area_desc="SORGHUM, GRAIN - ACRES HARVESTED",
        price_desc="SORGHUM, GRAIN - PRICE RECEIVED, MEASURED IN $ / CWT",
        price_unit="$/cwt",
        factor=0.56,
        days_to_harvest=140,
        sale_months=(10, 11, 12),
    ),
    "alfalfa hay": _hay(36, "HAY, ALFALFA", "HAY, ALFALFA"),
    "other hay": _hay(37, "HAY, (EXCL ALFALFA)", "HAY, (EXCL ALFALFA)"),
}
ALIASES = {
    "maize": "corn",
    "corn grain": "corn",
    "soy": "soybeans",
    "soybean": "soybeans",
    "soya": "soybeans",
    "wheat": "winter wheat",
    "oat": "oats",
    "milo": "sorghum",
    "alfalfa": "alfalfa hay",
    "hay": "alfalfa hay",
    "grass hay": "other hay",
}


def normalize_crop(name) -> str:
    key = str(name).strip().lower()
    key = ALIASES.get(key, key)
    if key not in CROPS:
        raise ValueError(f"Unknown crop {name!r}; supported: {', '.join(CROPS)}")
    return key


def number(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None  # "(D)" withheld, "(NA)", ""


def mass(amount: float | None, crop: str) -> dict | None:
    """Native amount (bu or tons) as amount, short tons and metric tonnes."""
    if amount is None:
        return None
    spec = CROPS[crop]
    pounds = amount * spec.lb_per_bu if spec.unit == "bu" else amount * 2000.0
    return {
        "amount": round(amount, 1),
        "unit": spec.unit,
        "shortTons": round(pounds / 2000.0, 2),
        "tonnes": round(pounds * LB_TO_KG / 1000.0, 2),
    }


class Nass:
    """Quick Stats, FCC and CropScape requests with a small per-process cache."""

    def __init__(self, api_key: str = "", client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30, connect=5), headers={"User-Agent": "FieldShiftNASA/1.0"}
        )
        self._lock = Lock()
        self._counties: dict[tuple[float, float], dict | None] = {}
        self._queries: dict[tuple, list[dict]] = {}

    def close(self):
        self.client.close()

    def require_key(self):
        if not self.api_key:
            raise NassUnavailable("NASS_API_KEY is not configured on the server")

    def query(self, **params) -> list[dict]:
        """Quick Stats rows. HTTP 400 means no record matches, which is an empty list."""
        self.require_key()
        cache_key = tuple(sorted(params.items()))
        with self._lock:
            if cache_key in self._queries:
                return self._queries[cache_key]
        error = ""
        for attempt in range(2):
            try:
                response = self.client.get(
                    NASS_URL, params={"key": self.api_key, "format": "JSON", **params}
                )
            except httpx.HTTPError as caught:
                error = type(caught).__name__
                time.sleep(1 + attempt)
                continue
            if response.status_code == 200:
                try:
                    rows = response.json().get("data", [])
                except ValueError:
                    rows = []
                with self._lock:
                    self._queries[cache_key] = rows
                return rows
            if response.status_code == 400:
                return []
            error = f"HTTP {response.status_code}"
            if response.status_code in (401, 403, 413):
                break
            time.sleep(1 + attempt)
        raise NassUnavailable(f"NASS Quick Stats request failed ({error})")

    def stat(self, crop: str, what: str, year, level: str, state: str, county=None) -> dict:
        """One statistic of one crop and year: {(state, county or ''): (value, county name)}.

        ``what`` is yield, prod or area.
        """
        spec = CROPS[crop]
        params = {
            "source_desc": "SURVEY",
            "commodity_desc": spec.commodity,
            "short_desc": getattr(spec, f"{what}_desc"),
            "year": year,
            "agg_level_desc": level,
            "state_fips_code": state,
        }
        if county:
            params["county_code"] = county
        found = {}
        for row in self.query(**params):
            if str(row.get("reference_period_desc", "YEAR")).upper() != "YEAR":
                continue
            value = number(row.get("Value"))
            if value is None:
                continue
            code = str(row.get("county_code") or "").zfill(3) if level == "COUNTY" else ""
            found[(str(row.get("state_fips_code", state)).zfill(2), code)] = (
                value,
                row.get("county_name"),
            )
        return found

    def county(self, lat: float, lng: float) -> dict | None:
        """{state, county, fips, name, stateCode} of a point, or None outside the U.S."""
        key = (round(lat, 3), round(lng, 3))
        with self._lock:
            if key in self._counties:
                return self._counties[key]
        try:
            response = self.client.get(
                FCC_URL, params={"latitude": lat, "longitude": lng, "format": "json"}
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise NassUnavailable("County lookup failed") from error
        fips = (body.get("County") or {}).get("FIPS")
        found = (
            {
                "state": fips[:2],
                "county": fips[2:],
                "fips": fips,
                "name": body["County"].get("name"),
                "stateCode": (body.get("State") or {}).get("code"),
            }
            if fips
            else None
        )
        with self._lock:
            self._counties[key] = found
        return found

    def cdl_class(self, year: int, lat: float, lng: float) -> tuple[int, str] | None:
        """CropScape class at a point in a year: (code, category), or None when unreadable."""
        from pyproj import Transformer

        x, y = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform(lng, lat)
        try:
            response = self.client.get(
                CROPSCAPE_URL, params={"year": year, "x": f"{x:.1f}", "y": f"{y:.1f}"}
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise NassUnavailable("CropScape request failed") from error
        value = re.search(r"\bvalue\b\W{0,4}(\d+)", response.text, re.I)
        category = re.search(r"\bcategory\b\W{0,4}\"?([^\",}<]*)", response.text, re.I)
        if not value:
            return None
        return int(value.group(1)), category.group(1).strip() if category else ""
