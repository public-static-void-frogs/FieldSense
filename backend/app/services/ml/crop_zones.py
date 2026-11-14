"""Dissolve classified masks into connected crop zones in image pixel space."""

from collections import defaultdict
from uuid import uuid4

import numpy as np
from shapely import Polygon, box, get_parts, transform
from shapely.geometry import shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from app.services.ml.geometry import GEOD, TO_MERCATOR

GAP_RADIUS_PX = 6
EDGE_TOLERANCE_PX = 4


def merge_crop_zones(fields, projection):
    def to_pixel(longitude, latitude, z=None):
        x, y = TO_MERCATOR.transform(longitude, latitude)
        return (
            (np.asarray(x) - projection.west)
            / (projection.east - projection.west)
            * projection.width
            - 0.5,
            (projection.north - np.asarray(y))
            / (projection.north - projection.south)
            * projection.height
            - 0.5,
        )

    by_crop = defaultdict(list)
    for field in fields:
        by_crop[field["crop"]].append(
            transform(shape(field["geometry"]), to_pixel, interleaved=False)
        )

    zones = []
    extent = box(-0.5, -0.5, projection.width - 0.5, projection.height - 0.5)
    for crop, masks in by_crop.items():
        dissolved = unary_union(masks)
        # Close narrow gaps without losing small original masks to erosion.
        closed = dissolved.buffer(GAP_RADIUS_PX).buffer(-GAP_RADIUS_PX)
        merged = dissolved.union(closed).intersection(extent)
        for part in get_parts(merged):
            if part.geom_type != "Polygon" or part.is_empty:
                continue
            holes = [ring for ring in part.interiors if Polygon(ring).area > GAP_RADIUS_PX**2]
            clean = Polygon(part.exterior, holes).simplify(
                EDGE_TOLERANCE_PX, preserve_topology=True
            )
            geographic = orient(
                transform(clean, projection.geographic, interleaved=False), sign=1.0
            )
            area = abs(GEOD.geometry_area_perimeter(geographic)[0]) / 10_000
            if area <= 0:
                continue
            center = geographic.representative_point()
            zones.append(
                dict(
                    id=uuid4(),
                    crop=crop,
                    geometry=dict(
                        type="Polygon",
                        coordinates=[list(geographic.exterior.coords)]
                        + [list(ring.coords) for ring in geographic.interiors],
                    ),
                    center=[center.x, center.y],
                    areaHa=area,
                )
            )
    return zones
