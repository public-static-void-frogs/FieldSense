"""Fetch `field["soil"]` from USDA NRCS Soil Data Access (SSURGO) for a point.

Values are SSURGO map-unit estimates for the dominant component and its surface horizon, not a
soil test of the field; `drainage_class` is the natural, undrained condition (tile drainage is
not in SSURGO). The service is anonymous; cache results by coordinate or mukey.
"""

import json
import urllib.request

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
SOURCE = "USDA NRCS SSURGO via Soil Data Access (map-unit estimate)"
QUERY = """
SELECT mu.mukey, mu.muname, mu.iacornsr, ma.aws0100wta,
 c.slope_r, c.drainagecl, c.hydgrp, c.nirrcapcl, c.nirrcapscl, c.tfact,
 h.sandtotal_r, h.claytotal_r, h.om_r, h.ph1to1h2o_r, h.caco3_r, h.kwfact
FROM mapunit mu JOIN muaggatt ma ON ma.mukey = mu.mukey
JOIN component c ON c.mukey = mu.mukey AND c.cokey = (
  SELECT TOP 1 c2.cokey FROM component c2 WHERE c2.mukey = mu.mukey
  ORDER BY c2.comppct_r DESC, c2.cokey)
JOIN chorizon h ON h.cokey = c.cokey AND h.hzdept_r = 0
WHERE mu.mukey IN (
  SELECT DISTINCT mukey FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({lon} {lat})'))
"""
COLUMNS = {  # SDA column -> (soil key, converter)
    "mukey": ("mukey", str),
    "muname": ("map_unit", str),
    "iacornsr": ("csr2", float),
    "aws0100wta": ("aws_100cm_mm", lambda v: round(float(v) * 10, 1)),  # cm -> mm
    "slope_r": ("slope_pct", float),
    "drainagecl": ("drainage_class", str),
    "hydgrp": ("hydgrp", str),
    "nirrcapcl": ("nirr_class", int),
    "nirrcapscl": ("nirr_subclass", str),
    "tfact": ("tfact", float),
    "sandtotal_r": ("sand_pct", float),
    "claytotal_r": ("clay_pct", float),
    "om_r": ("om_pct", float),
    "ph1to1h2o_r": ("ph", float),
    "caco3_r": ("caco3_pct", float),
    "kwfact": ("kw", float),
}


def parse_soil(payload: dict) -> dict | None:
    """Turn an SDA JSON+COLUMNNAME response into a `field["soil"]` mapping."""
    table = payload.get("Table") or []
    if len(table) < 2:
        return None
    row = dict(zip(table[0], table[1], strict=True))
    soil = {"source": SOURCE}
    for column, (key, convert) in COLUMNS.items():
        value = row.get(column)
        if value not in (None, ""):
            soil[key] = convert(value)
    return soil


def fetch_soil(lat: float, lon: float, timeout: float = 30.0) -> dict | None:
    """Soil properties at a point, or None when SSURGO has no map unit there."""
    body = {"format": "JSON+COLUMNNAME", "query": QUERY.format(lon=float(lon), lat=float(lat))}
    request = urllib.request.Request(
        SDA_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return parse_soil(json.load(response))
