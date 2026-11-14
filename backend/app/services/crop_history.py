"""Read annual USDA crop classes for a location and render the same classes on a map."""

import base64
import colorsys
import datetime as dt
import json
import math
import re
import time
from functools import lru_cache

import httpx
import numpy as np
from fastapi import HTTPException
from pyproj import Transformer
from rasterio.errors import RasterioError
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from shapely import from_wkb, transform
from shapely.geometry import Point, shape

from app.schemas.crop_history import CropClass, CropHistory, CropLayer, CropLayerClass, CropYear
from app.services.cdl_classes import CDL

FIRST_YEAR = 2008
LAST_YEAR = 2025
SOURCE = "https://pdi.scinet.usda.gov/image/rest/services/CDL_WM/ImageServer"
TO_MAP = Transformer.from_crs(4326, 3857, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(3857, 4326, always_xy=True).transform
NO_DATA = {0, 81}
COLORS = {
    1: "#e8bd55",
    5: "#70c26b",
    24: "#dc8d63",
    36: "#ba8dd2",
    61: "#b3a394",
    176: "#4cab9b",
    111: "#5ba7da",
}


def crop_class(code):
    color = COLORS.get(code)
    if color is None:
        rgb = colorsys.hls_to_rgb((code * 0.618034) % 1, 0.66, 0.62)
        color = "#" + "".join(f"{round(channel * 255):02x}" for channel in rgb)
    return CropClass(code=code, label=CDL.get(code, f"USDA class {code}"), color=color)


def extent(field, part):
    boundary = field["boundary"]
    if boundary:
        polygons = shape(boundary).geoms
        if part >= len(polygons):
            raise HTTPException(422, "Saved parcel does not exist")
        polygon = transform(polygons[part], TO_MAP, interleaved=False)
        return polygon.bounds, polygon
    if part != 0:
        raise HTTPException(422, "Saved parcel does not exist")
    x, y = TO_MAP(*field["geometry"]["coordinates"])
    # Keep the window roughly 500 ground meters across.
    radius = 250 / max(math.cos(math.radians(field["geometry"]["coordinates"][1])), 0.1)
    return (x - radius, y - radius, x + radius, y + radius), None


def time_range(first, last):
    def millis(year):
        return int(dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)

    return f"{millis(first)},{millis(last + 1) - 1}"


def upstream(operation, params):
    response = httpx.get(f"{SOURCE}/{operation}", params=params, timeout=8)
    response.raise_for_status()
    return response


def history(field, part, coordinates):
    bounds, polygon = extent(field, part)
    if coordinates is None:
        if polygon is None:
            coordinates = tuple(field["geometry"]["coordinates"])
        else:
            center = polygon.representative_point()
            coordinates = TO_WGS84(center.x, center.y)
    x, y = TO_MAP(*coordinates)
    west, south, east, north = bounds
    if not (west <= x <= east and south <= y <= north) or (
        polygon is not None and not polygon.covers(Point(x, y))
    ):
        raise HTTPException(422, "Choose a point inside the displayed area")

    try:
        rows = identify(*coordinates, int(time.time() // 3600))
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
        raise HTTPException(502, "USDA crop history is temporarily unavailable") from error
    return CropHistory(coordinates=coordinates, years=rows)


@lru_cache(maxsize=512)
def identify(lon, lat, _hour):
    response = upstream(
        "identify",
        {
            "f": "json",
            "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
            "geometryType": "esriGeometryPoint",
            "time": time_range(FIRST_YEAR, LAST_YEAR),
            "returnGeometry": "false",
            "returnCatalogItems": "true",
            "returnPixelValues": "true",
            "maxItemCount": LAST_YEAR - FIRST_YEAR + 1,
        },
    ).json()
    if "error" in response:
        raise ValueError("USDA identify failed")
    features = (response.get("catalogItems") or {}).get("features", [])
    values = (response.get("properties") or {}).get("Values", [])
    if len(features) != len(values):
        raise ValueError("USDA returned mismatched years and values")
    by_year = {}
    for feature, value in zip(features, values):
        year = re.match(r"^(\d{4})_", feature["attributes"]["Name"])
        if year is None or not str(value).isdigit():
            continue
        code = int(value)
        if code not in NO_DATA:
            by_year[int(year[1])] = crop_class(code)
    return [
        CropYear(year=year, crop=by_year.get(year)) for year in range(LAST_YEAR, FIRST_YEAR - 1, -1)
    ]


def layer(field, part, year):
    bounds, polygon = extent(field, part)
    try:
        return render(
            year, bounds, polygon.wkb if polygon is not None else None, int(time.time() // 3600)
        )
    except (httpx.HTTPError, RasterioError, ValueError, TypeError) as error:
        raise HTTPException(502, "USDA crop map is temporarily unavailable") from error


@lru_cache(maxsize=96)
def render(year, bounds, polygon_wkb, _hour):
    west, south, east, north = bounds
    scale = max((east - west) / 640, (north - south) / 640, 8)
    response = upstream(
        "exportImage",
        {
            "f": "image",
            "bbox": ",".join(map(str, bounds)),
            "bboxSR": 3857,
            "imageSR": 3857,
            "size": f"{max(1, math.ceil((east - west) / scale))},{max(1, math.ceil((north - south) / scale))}",
            "adjustAspectRatio": "false",
            "format": "tiff",
            "pixelType": "U8",
            "time": time_range(year, year),
            "interpolation": "RSP_NearestNeighbor",
            "renderingRule": '{"rasterFunction":"None"}',
        },
    )
    with MemoryFile(response.content) as source, source.open() as raster:
        if raster.count != 1 or raster.crs is None or raster.crs.to_epsg() != 3857:
            raise ValueError("Expected a single band of crop codes in Web Mercator")
        classes = raster.read(1, masked=True).filled(0)
        if polygon_wkb is not None:
            inside = geometry_mask(
                [from_wkb(polygon_wkb)], classes.shape, raster.transform, invert=True
            )
            classes[~inside] = 0
        west, south, east, north = raster.bounds
    west, south = TO_WGS84(west, south)
    east, north = TO_WGS84(east, north)
    codes, counts = np.unique(classes, return_counts=True)
    valid = [(int(code), int(count)) for code, count in zip(codes, counts) if code not in NO_DATA]
    total = sum(count for _, count in valid)
    legend = [
        CropLayerClass(**crop_class(code).model_dump(), share=count / total)
        for code, count in valid
    ]
    image = None
    if legend:
        pixels = np.zeros((4, *classes.shape), dtype=np.uint8)
        for crop in legend:
            rgb = [int(crop.color[i : i + 2], 16) for i in (1, 3, 5)]
            pixels[:, classes == crop.code] = np.array([*rgb, 185])[:, None]
        with MemoryFile() as output:
            with output.open(
                driver="PNG",
                height=classes.shape[0],
                width=classes.shape[1],
                count=4,
                dtype="uint8",
            ) as raster:
                raster.write(pixels)
            image = "data:image/png;base64," + base64.b64encode(output.read()).decode("ascii")
    return CropLayer(bounds=(west, south, east, north), image=image, classes=legend)
