"""Focused geometry, endpoint failure checks."""

import asyncio
import importlib.util
import json
import unittest
from datetime import date, timedelta
from threading import Event
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from support import isolated_app

HAS_GEOMETRY = all(importlib.util.find_spec(name) for name in ("cv2", "numpy", "shapely", "pyproj"))


@unittest.skipUnless(
    all(importlib.util.find_spec(name) for name in ("numpy", "rasterio", "requests")),
    "Install requirements-ml.txt for greenness checks",
)
class GreennessSequenceTests(unittest.TestCase):
    def test_catalog_applied_offset_takes_precedence_over_band_metadata(self):
        from app.services.ml.greenness import _scale_offset

        asset = {"raster:bands": [{"scale": 0.0001, "offset": -0.1}]}
        self.assertEqual(
            _scale_offset(asset, {"earthsearch:boa_offset_applied": True}), (0.0001, 0.0)
        )
        self.assertEqual(
            _scale_offset(asset, {"earthsearch:boa_offset_applied": False}), (0.0001, -0.1)
        )

    def test_nearby_points_share_one_window_per_asset(self):
        from concurrent.futures import ThreadPoolExecutor
        from contextlib import nullcontext

        import numpy as np
        from rasterio.transform import from_origin

        from app.services.ml.greenness import ASSETS, _scene_vectors

        values = dict(zip(ASSETS.values(), (500, 1000, 4000, 2000, 4)))
        assets = {
            band: {"href": f"https://sentinel-cogs.s3.us-west-2.amazonaws.com/{band}"}
            for band in values
        }
        item = {"assets": assets, "properties": {}}
        points = [(0, 0), (0.0002, 0)]
        transform = from_origin(-500, 500, 20, 20)

        def open_asset(url):
            return nullcontext(
                SimpleNamespace(
                    value=values[url.rsplit("/", 1)[1]], transform=transform, crs="EPSG:3857"
                )
            )

        def read_window(dataset, bounds, shape, resampling):
            return np.full(shape, dataset.value, dtype="uint16")

        with (
            patch("rasterio.open", side_effect=open_asset) as opened,
            patch("app.services.ml.greenness._read_window", side_effect=read_window) as reads,
            ThreadPoolExecutor(max_workers=4) as workers,
        ):
            results = _scene_vectors(item, points, lambda: None, workers)
            self.assertEqual(set(results), set(points))
            self.assertEqual(opened.call_count, 5)
            self.assertEqual(reads.call_count, 5)
            for vector in results.values():
                self.assertAlmostEqual(float(vector[0]), 0.6, places=5)

    def test_latest_clear_dates_are_unique_and_oldest_first(self):
        import numpy as np

        from app.services.ml.greenness import greenness_sequences

        start = date(2026, 7, 1)
        nearby = (-93.1, 42.1)
        cloudy = (-93.2, 42.2)

        def scene(day):
            return {
                "properties": {"datetime": str(start + timedelta(days=day))},
                "bbox": [-94, 42, -93, 43],
                "day": day,
            }

        items = [scene(day) for day in range(18)] + [scene(16)]

        def read_vectors(item, points, *args):
            day = item["day"]
            return {
                point: np.array([day, day + 1, day + 2], dtype="float32")
                for point in points
                if day != 17 and (point != cloudy or day < 2)
            }

        with (
            patch("app.services.ml.greenness._search", return_value=items) as search,
            patch("app.services.ml.greenness._scene_vectors", side_effect=read_vectors),
        ):
            progress = []
            results = greenness_sequences(
                [nearby, cloudy],
                monotonic() + 10,
                lambda: None,
                lambda point, steps: progress.append((point, steps)),
            )
            search.assert_called_once()
            dates, sequence = results[nearby]
            self.assertEqual(dates, [str(start + timedelta(days=day)) for day in range(1, 17)])
            self.assertEqual(sequence.shape, (16, 3))
            self.assertEqual(sequence[:, 0].tolist(), list(range(1, 17)))
            self.assertIn("Only 2 of 16", results[cloudy])
            for point in (nearby, cloudy):
                self.assertEqual(sum(steps for coord, steps in progress if coord == point), 16)


@unittest.skipUnless(HAS_GEOMETRY, "Install requirements-ml.txt for mask geometry checks")
class MaskGeometryTests(unittest.TestCase):
    def test_crop_zones_dissolve_overlaps_and_bridge_only_nearby_same_crop(self):
        from shapely.geometry import Point, shape

        from app.services.ml.crop_zones import merge_crop_zones
        from app.services.ml.geometry import ImageProjection

        image = SimpleNamespace(bounds=(-94, 42, -93.99, 42.01), width=200, height=200)
        projection = ImageProjection(image)

        def mask(crop, left, top, right, bottom):
            ring = [(left, top), (right, top), (right, bottom), (left, bottom), (left, top)]
            return {
                "crop": crop,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[projection.geographic(*point) for point in ring]],
                },
            }

        zones = merge_crop_zones(
            [
                mask("Corn", 10, 10, 55, 70),
                mask("Corn", 15, 15, 45, 65),
                mask("Corn", 59, 10, 100, 70),
                mask("Corn", 135, 10, 180, 70),
                mask("Soybeans", 10, 80, 55, 120),
            ],
            projection,
        )
        corn = [zone for zone in zones if zone["crop"] == "Corn"]
        self.assertEqual(len(corn), 2)
        self.assertEqual(len(zones), 3)
        bridge = Point(*projection.geographic(57, 40))
        self.assertTrue(any(shape(zone["geometry"]).covers(bridge) for zone in corn))
        for zone in zones:
            polygon = shape(zone["geometry"])
            self.assertTrue(polygon.is_valid)
            self.assertTrue(polygon.contains(Point(*zone["center"])))
            self.assertEqual(len(polygon.exterior.coords), 5)

    def test_real_mask_component_preserves_holes_and_excludes_other_objects(self):
        import numpy as np
        from shapely.geometry import shape

        from app.services.ml.geometry import ImageProjection, field_geometry

        image = SimpleNamespace(bounds=(-94, 42, -93.99, 42.01), width=100, height=100)
        projection = ImageProjection(image)
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[10:70, 10:70] = 1
        mask[30:45, 30:45] = 0
        mask[80:95, 80:95] = 1
        result = field_geometry(mask, [20, 20], projection)
        self.assertEqual(len(result["geometry"]["coordinates"]), 2)
        self.assertLess(shape(result["geometry"]).bounds[2], -93.992)
        self.assertGreater(result["areaHa"], 0)
        self.assertFalse(result["touchesImageEdge"])
        self.assertIsNone(field_geometry(mask, [0, 0], projection))

    def test_mercator_latitude_is_not_linearly_interpolated(self):
        from app.services.ml.geometry import ImageProjection

        projection = ImageProjection(SimpleNamespace(bounds=(-1, 10, 1, 70), width=101, height=101))
        lon, lat = projection.geographic(50, 50)
        self.assertAlmostEqual(lon, 0)
        self.assertGreater(lat, 47)
        self.assertLess(lat, 48)
        pixel = projection.pixel((lon, lat))
        self.assertAlmostEqual(pixel[0], 50.5)
        self.assertAlmostEqual(pixel[1], 50.5)


class AnalysisEndpointTests(unittest.TestCase):
    def test_busy_model_returns_503_without_loading_or_fabricating_results(self):
        from app.schemas.section_analysis import SectionAnalysisRequest
        from app.services.section_analysis import AnalysisUnavailable, SectionAnalyzer

        analyzer = SectionAnalyzer()
        analyzer.lock.acquire()
        try:
            with self.assertRaises(AnalysisUnavailable):
                analyzer.analyze(None)
            self.assertFalse(analyzer.loaded)
        finally:
            analyzer.lock.release()
        # Contract rejects empty selections before any model operation.
        self.assertIn(
            "minItems", SectionAnalysisRequest.model_json_schema()["properties"]["points"]
        )

    def test_analyze_endpoint_requires_authentication(self):
        directory, app = isolated_app()
        try:
            with TestClient(app) as client:
                response = client.post("/api/v1/maps/sections/analyze", json={})
                self.assertEqual(response.status_code, 401)
        finally:
            directory.cleanup()


class AnalysisStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_progress_arrives_before_result(self):
        from uuid import uuid4

        from app.api.section_analysis import analysis_events

        release = Event()

        def analyze(payload, cancelled, report):
            report({"stage": "satellite", "completed": 1, "total": 16})
            if not release.wait(5):
                raise AssertionError("Progress was buffered until analysis finished")
            return {
                "requestId": uuid4(),
                "fields": [],
                "skippedPoints": [],
                "provenance": {
                    "segmentationInputs": "submitted_map_image_and_points",
                    "cropInputs": "sentinel-2-l2a",
                    "syntheticCropInputs": False,
                    "sequenceShape": [16, 3],
                    "channels": ["NDVI", "EVI", "NDWI"],
                    "cropLabelSource": "unmapped_class_indices",
                    "classLabels": [],
                    "device": "cpu",
                },
            }

        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(section_analyzer=SimpleNamespace(analyze=analyze))
            )
        )
        stream = analysis_events(None, request)
        try:
            first = json.loads(await asyncio.wait_for(anext(stream), timeout=3))
            self.assertEqual(
                first, {"type": "progress", "stage": "satellite", "completed": 1, "total": 16}
            )
            release.set()
            self.assertEqual(json.loads(await anext(stream))["type"], "result")
            with self.assertRaises(StopAsyncIteration):
                await anext(stream)
        finally:
            release.set()
            await stream.aclose()
