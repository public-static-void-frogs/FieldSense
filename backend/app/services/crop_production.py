"""How much crop a field or a region produced in a past year, from USDA NASS data.

USDA publishes yields only as county (and state) averages, so a field's production is its area
times the county-average yield of that year: an expected value, not a measurement. For a region
NASS publishes county and state production directly. The crop of a field comes from the Cropland
Data Layer at its point unless the caller names one.
"""

import logging
import math

from app.services.nass import (
    CROPS,
    HA_TO_ACRE,
    Nass,
    NassUnavailable,
    mass,
    normalize_crop,
)

logger = logging.getLogger(__name__)

CODE_TO_CROP = {spec.cdl: name for name, spec in CROPS.items() if spec.cdl}
MAX_SNAP_M = 500.0


def _crop_near(nass: Nass, year: int, lat: float, lng: float, snap_m: float):
    """Nearest supported-crop pixel within snap_m, sampled on rings of 30, 60, 120 ... m."""
    radius = 30.0
    while radius <= snap_m + 1e-9:
        for step in range(8):
            angle = math.radians(45 * step)
            near_lat = lat + radius * math.cos(angle) / 110540.0
            near_lng = lng + radius * math.sin(angle) / (
                111320.0 * max(math.cos(math.radians(lat)), 0.1)
            )
            try:
                found = nass.cdl_class(year, near_lat, near_lng)
            except NassUnavailable:
                continue
            if found and found[0] in CODE_TO_CROP:
                return found, radius
        radius *= 2
    return None


def _yield_for(nass: Nass, crop: str, year: int, county: dict) -> tuple[float, str]:
    """The county yield, or the state yield when the county value is withheld or missing."""
    key = (county["state"], county["county"])
    found = nass.stat(crop, "yield", year, "COUNTY", county["state"], county["county"])
    if key in found:
        return found[key][0], "county"
    state = nass.stat(crop, "yield", year, "STATE", county["state"])
    if (county["state"], "") in state:
        return state[(county["state"], "")][0], "state"
    raise NassUnavailable(
        f"NASS has no {crop} yield for {year} in county {county['fips']} or its state "
        "(the year may not be published yet, or the crop is not grown there)"
    )


def field_production(
    nass: Nass,
    year: int,
    lat: float,
    lng: float,
    crop: str | None = None,
    area_ha: float | None = None,
    snap_m: float = 0.0,
) -> dict:
    """Expected production of one field in a past year (county-average yield x area)."""
    county = nass.county(lat, lng)
    if county is None:
        raise NassUnavailable("The field is not in a U.S. county; NASS data covers the U.S. only")
    notes = []
    if crop:
        name, source = normalize_crop(crop), "user"
    else:
        found = nass.cdl_class(year, lat, lng)
        if not found:
            raise NassUnavailable("The crop at the field point could not be read; name the crop")
        if found[0] in CODE_TO_CROP:
            name, source = CODE_TO_CROP[found[0]], f"CropScape CDL {year} ({found[1]})"
        else:
            near = _crop_near(nass, year, lat, lng, min(snap_m, MAX_SNAP_M)) if snap_m > 0 else None
            if near is None:
                raise NassUnavailable(
                    f"The CDL class of {year} at the field point ({found[1]}) is not a supported "
                    f"crop ({', '.join(CROPS)}); name the crop"
                )
            (code, category), distance = near
            name = CODE_TO_CROP[code]
            source = f"CropScape CDL {year} ({category}) at {distance:.0f} m from the point"
            notes.append("The point is not a crop pixel; the crop was read nearby, so confirm it")
    acres = (area_ha if area_ha else 1 / HA_TO_ACRE) * HA_TO_ACRE
    yield_value, level = _yield_for(nass, name, year, county)
    spec = CROPS[name]
    if level == "state":
        notes.append("County yield withheld or missing, so the state yield was used")
    notes += [
        "Expected value from the county-average yield of the year; a single field can be "
        "well above or below it (the spread is not quantified)",
        "Yield is per harvested acre; abandoned, silage or cover area lowers real production",
    ]
    return {
        "year": year,
        "crop": name,
        "cropSource": source,
        "county": county["name"],
        "countyFips": county["fips"],
        "areaHa": round(acres / HA_TO_ACRE, 3),
        "areaAcres": round(acres, 3),
        "areaDefaulted": not area_ha,
        "yieldUsed": {
            "value": round(yield_value, 2),
            "unit": f"{spec.unit}/acre",
            "level": level,
            "source": "NASS survey yield",
        },
        "production": mass(yield_value * acres, name),
        "productionPerHa": mass(yield_value * HA_TO_ACRE, name),
        "notes": notes,
    }


def region_production(
    nass: Nass,
    year: int,
    counties: list[str] | None = None,
    state: str | None = None,
    crops: list[str] | None = None,
) -> dict:
    """NASS production totals of counties or a state for a past year, per crop."""
    if not counties and not state:
        raise ValueError("Give county FIPS codes or a state FIPS code")
    wanted: dict[str, set[str] | None] = {}
    for fips in counties or []:
        fips = str(fips).zfill(5)
        wanted.setdefault(fips[:2], set()).add(fips[2:])
    if state:
        wanted[str(state).zfill(2)] = None
    names = [normalize_crop(c) for c in crops] if crops else list(CROPS)
    results = []
    for crop in names:
        rows, reported_state = [], {}
        for state_fips, codes in wanted.items():
            yields = nass.stat(crop, "yield", year, "COUNTY", state_fips)
            produced = nass.stat(crop, "prod", year, "COUNTY", state_fips)
            acres = nass.stat(crop, "area", year, "COUNTY", state_fips)
            state_yield = nass.stat(crop, "yield", year, "STATE", state_fips).get((state_fips, ""))
            if codes is None:
                total = nass.stat(crop, "prod", year, "STATE", state_fips).get((state_fips, ""))
                if total:
                    reported_state[state_fips] = total[0]
            for key in sorted(set(yields) | set(produced) | set(acres)):
                if codes is not None and key[1] not in codes:
                    continue
                y = (yields.get(key) or (None,))[0]
                p = (produced.get(key) or (None,))[0]
                a = (acres.get(key) or (None,))[0]
                if y is None and state_yield:
                    y = state_yield[0]
                if p is not None:
                    rows.append((p, "reported", a))
                elif a is not None and y is not None:
                    rows.append((a * y, "acres x yield", a))
                else:
                    rows.append((None, "none", a))
        if not rows:
            results.append({"crop": crop, "note": "No NASS data for this year in the region"})
            continue

        def total(items):
            values = [v for v in items if v is not None]
            return sum(values) if values else None

        results.append(
            {
                "crop": crop,
                "counties": len(rows),
                "countiesByBasis": {
                    basis: sum(1 for row in rows if row[1] == basis)
                    for basis in ("reported", "acres x yield", "none")
                },
                "totalReported": mass(total(r[0] for r in rows if r[1] == "reported"), crop),
                "totalBest": mass(total(r[0] for r in rows), crop),
                "stateReportedByNass": {s: mass(v, crop) for s, v in reported_state.items()}
                or None,
                "harvestedAcres": total(r[2] for r in rows),
            }
        )
    return {
        "year": year,
        "states": sorted(wanted),
        "crops": results,
        "notes": [
            "totalBest is the NASS reported production plus acres harvested x yield where NASS "
            "withheld the production; see countiesByBasis",
            "A missing value means no data, never zero",
        ],
    }
