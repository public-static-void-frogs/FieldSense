import time
import unittest
from threading import Event
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from support import create_field, isolated_app, register

from app.services import crop_history, soil_depletion


class FieldInsightTests(unittest.TestCase):
    def setUp(self):
        directory, self.app = isolated_app()
        self.addCleanup(directory.cleanup)
        self.addCleanup(self.app.state.engine.dispose)
        self.addCleanup(self.app.state.soil_assessments.close)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.assertEqual(register(self.client).status_code, 201)
        self.other = TestClient(self.app)
        self.addCleanup(self.other.close)
        self.assertEqual(register(self.other, "other@example.com").status_code, 201)

    def test_m3_uses_saved_coordinates_and_distinguishes_outside_coverage(self):
        field = create_field(
            self.client, geometry={"type": "Point", "coordinates": [-93.62, 41.98]}
        )
        path = f"/api/v1/fields/{field['id']}/m3-insights"
        self.assertEqual(self.other.get(path).status_code, 404)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["query"], {"lat": 41.98, "lng": -93.62})
        self.assertEqual(result["match"]["level"], "field")
        match = result["match"]
        self.assertGreater(match["reference_awc_mm"], 0)
        self.assertIsNotNone(result["windows"]["now"]["corn:sow"]["date_q50"])
        self.assertIn("ssp245", result["risk"]["future"])
        self.assertIsNone(result["fallow_zero"])

        outside = create_field(
            self.client, geometry={"type": "Point", "coordinates": [30.52, 50.45]}
        )
        response = self.client.get(f"/api/v1/fields/{outside['id']}/m3-insights")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"]["code"], "outside_coverage")

    def test_soil_computation_is_deduplicated_and_uses_only_available_weights(self):
        field = create_field(self.client)
        path = f"/api/v1/fields/{field['id']}/soil-depletion"
        entered = Event()
        release = Event()

        def identify(lon, lat, hour):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test did not release the worker")
            return [
                crop_history.CropYear(year=year, crop=crop_history.crop_class(1))
                for year in (2022, 2023, 2024, 2025)
            ]

        with (
            patch.object(crop_history, "identify", side_effect=identify) as history,
            patch.object(
                soil_depletion, "soil_part", return_value=(0.5, {"om_pct_0_30cm": 3}, None)
            ),
            patch.object(soil_depletion, "_search", side_effect=httpx.ConnectError("unavailable")),
        ):
            self.assertEqual(self.other.get(path).status_code, 404)
            self.assertEqual(self.client.get(path, params={"part": 1}).status_code, 422)
            try:
                self.assertEqual(self.client.get(path).json()["status"], "pending")
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.client.get(path).json()["status"], "pending")
            finally:
                release.set()

            for _ in range(100):
                result = self.client.get(path).json()
                if result["status"] == "ready":
                    break
                time.sleep(0.02)
            self.assertEqual(result["status"], "ready")
            assessment = result["assessment"]
            self.assertEqual(result["coordinates"], field["geometry"]["coordinates"])
            self.assertEqual(assessment["coverage"], 0.55)
            self.assertEqual(assessment["score"], 81.8)
            self.assertEqual(assessment["drivers"], ["rotation", "soil"])
            self.assertIsNone(assessment["components"]["greenness"])
            self.assertIn("greenness_unavailable", assessment["notes"])
            history.assert_called_once()

    def test_rotation_weights_demand_and_breaks_runs_at_gaps(self):
        corn, metrics = soil_depletion.rotation(dict.fromkeys(range(2022, 2026), "Corn"))
        self.assertAlmostEqual(corn, 1)
        self.assertEqual(metrics["rotation_marks"][-1]["mark"], "heavy_repeat")
        alfalfa, _ = soil_depletion.rotation(dict.fromkeys(range(2022, 2026), "Alfalfa"))
        self.assertAlmostEqual(alfalfa, 0.07)
        _, gaps = soil_depletion.rotation({2022: "Corn", 2024: "Corn", 2025: "Corn"})
        self.assertEqual(gaps["years_same_crop"], 2)
        score, nonag = soil_depletion.rotation({2024: "Corn", 2025: "Open Water"})
        self.assertIsNone(score)
        self.assertEqual(nonag["unrated_crops"], [])
