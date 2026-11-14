"""Real SAM2 masks and Web Mercator pixels to geographic field polygons."""

import cv2
import numpy as np
from pyproj import Geod, Transformer
from shapely.geometry import Point, Polygon
from shapely.ops import transform

TO_MERCATOR = Transformer.from_crs(4326, 3857, always_xy=True)
TO_GEOGRAPHIC = Transformer.from_crs(3857, 4326, always_xy=True)
GEOD = Geod(ellps="WGS84")


class ImageProjection:
    def __init__(self, image):
        west, south, east, north = image.bounds
        self.west, self.south = TO_MERCATOR.transform(west, south)
        self.east, self.north = TO_MERCATOR.transform(east, north)
        self.width, self.height = image.width, image.height

    def pixel(self, coordinate):
        x, y = TO_MERCATOR.transform(*coordinate)
        return [
            max(0, min(self.width - 1, (x - self.west) / (self.east - self.west) * self.width)),
            max(
                0, min(self.height - 1, (self.north - y) / (self.north - self.south) * self.height)
            ),
        ]

    def geographic(self, x, y, z=None):
        # OpenCV contours describe pixel centers.
        return TO_GEOGRAPHIC.transform(
            self.west + (np.asarray(x) + 0.5) / self.width * (self.east - self.west),
            self.north - (np.asarray(y) + 0.5) / self.height * (self.north - self.south),
        )


def field_geometry(mask, pixel, projection):
    binary = np.asarray(mask, dtype=np.uint8)
    x, y = (int(round(value)) for value in pixel)
    _, labels = cv2.connectedComponents(binary)
    component = labels[y, x]
    if component == 0:
        return None
    selected = (labels == component).astype(np.uint8)
    contours, hierarchy = cv2.findContours(selected, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return None
    outer = max(
        (i for i, h in enumerate(hierarchy[0]) if h[3] == -1),
        key=lambda i: cv2.contourArea(contours[i]),
    )
    shell = contours[outer][:, 0, :]
    holes = [
        c[:, 0, :] for i, c in enumerate(contours) if hierarchy[0][i][3] == outer and len(c) >= 3
    ]
    if len(shell) < 3:
        return None
    polygon = Polygon(shell, holes).buffer(0)
    if polygon.geom_type == "MultiPolygon":
        candidates = [p for p in polygon.geoms if p.covers(Point(*pixel))]
        if not candidates:
            return None
        polygon = max(candidates, key=lambda p: p.area)
    tolerance = 0.75
    polygon = polygon.simplify(tolerance, preserve_topology=True)
    while len(polygon.exterior.coords) > 1024 and tolerance < 32:
        tolerance *= 2
        polygon = polygon.simplify(tolerance, preserve_topology=True)
    if polygon.is_empty or polygon.area <= 0 or len(polygon.exterior.coords) > 1024:
        return None
    geographic = transform(projection.geographic, polygon)
    area = abs(GEOD.geometry_area_perimeter(geographic)[0]) / 10_000
    center = geographic.representative_point()
    return dict(
        geometry=dict(
            type="Polygon",
            coordinates=[list(geographic.exterior.coords)]
            + [list(r.coords) for r in geographic.interiors],
        ),
        center=[center.x, center.y],
        areaHa=area,
        touchesImageEdge=bool(
            selected[0].any() or selected[-1].any() or selected[:, 0].any() or selected[:, -1].any()
        ),
    )
