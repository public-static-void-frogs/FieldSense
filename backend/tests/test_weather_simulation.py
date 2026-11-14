"""Real application -> real HTTP -> local Postman simulation; opt-in, never live weather."""

import os
import unittest

import httpx
from fastapi.testclient import TestClient
from support import create_field, isolated_app, register

from app.services.weather import WeatherService

SIMULATION = os.getenv("WEATHER_SIMULATION_URL")


@unittest.skipUnless(SIMULATION, "Set WEATHER_SIMULATION_URL to the local Postman member URL")
class WeatherSimulationTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app = isolated_app()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.app.state.engine.dispose)
        self.app.state.weather.close()
        self.config = self.app.state.config
        self.config.weather_forecast_url = SIMULATION + "/v1/forecast"
        self.config.weather_archive_url = SIMULATION + "/v1/archive"
        self.config.weather_timeout_seconds = 0.2
        self.app.state.weather = WeatherService(self.config)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.app.state.weather.close)
        httpx.get(SIMULATION + "/__control", params={"mode": "success"})
        self.assertEqual(
            register(self.client, latitude=50.4501, longitude=30.5234).status_code, 201
        )
        self.field = create_field(self.client)

    def test_current_forecast_history_and_shared_cache_over_http(self):
        current = self.client.get("/api/v1/weather/current")
        forecast = self.client.get("/api/v1/weather/forecast")
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(forecast.status_code, 200, forecast.text)
        self.assertEqual(len(forecast.json()["records"]), 14)
        self.assertEqual(httpx.get(SIMULATION + "/__control").json()["requests"], 1)
        history = self.client.get(
            "/api/v1/weather/history?start_date=2025-07-01&end_date=2025-07-07"
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(len(history.json()["records"]), 7)
        self.assertEqual(history.json()["records"][0]["moisture"], 25)
        self.assertEqual(current.json()["windDirection"], 90)

    def test_failures_missing_values_and_timeout_over_http(self):
        for mode in ("rate_limit", "error", "malformed", "slow"):
            with self.subTest(mode=mode):
                httpx.get(SIMULATION + "/__control", params={"mode": mode})
                response = self.client.get("/api/v1/weather/forecast")
                self.assertEqual(response.status_code, 503, response.text)
                self.assertNotIn("records", response.json())
        httpx.get(SIMULATION + "/__control", params={"mode": "missing"})
        response = self.client.get("/api/v1/weather/forecast")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["records"][0]["moisture"])
        self.assertIsNone(response.json()["records"][0]["rainfall"])

    def test_field_crop_assessment_and_missing_inputs_over_http(self):
        field = self.field
        response = self.client.get(f"/api/v1/weather/forecast?field_id={field['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["cropAssessment"]["context"]["fieldId"], field["id"])
        self.assertEqual(body["cropAssessment"]["model"]["kind"], "rule_engine")
        self.assertEqual(
            body["records"][0]["cropAssessment"]["metrics"]["temperature"]["lowRiskLevel"], "high"
        )
        self.assertTrue(
            any(
                alert["reading"] == "low"
                for alert in body["records"][0]["cropAssessment"]["alerts"]
            )
        )
        httpx.get(SIMULATION + "/__control", params={"mode": "missing"})
        self.app.state.weather._cache.clear()
        response = self.client.get(f"/api/v1/weather/forecast?field_id={field['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        day = response.json()["records"][0]["cropAssessment"]
        self.assertEqual(day["coverage"], "unavailable")
        self.assertIsNone(day["suitabilityScore"])
        self.assertEqual(day["metrics"]["moisture"]["riskLevel"], "unknown")
        self.assertFalse(any(alert["metric"] == "moisture" for alert in day["alerts"]))

    def test_map_saved_crop_area_receives_assessment_without_soil_over_http(self):
        saved = self.client.post(
            "/api/v1/fields/crop-areas",
            json={
                "areas": [
                    {
                        "crop": "Alfalfa",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[-94, 42], [-93.99, 42], [-94, 42.01], [-94, 42]]],
                        },
                    }
                ]
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        area = saved.json()[0]
        longitude, latitude = area["geometry"]["coordinates"]
        for endpoint in ("forecast", "history"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(f"/api/v1/weather/{endpoint}?field_id={area['id']}")
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual((body["longitude"], body["latitude"]), (longitude, latitude))
                context = body["cropAssessment"]["context"]
                self.assertEqual(context["crop"], "Alfalfa")
                self.assertEqual(context["soilCoverage"], "unavailable")
                day = body["records"][0]["cropAssessment"]
                self.assertEqual(day["coverage"], "complete")
                self.assertEqual(
                    set(day["bounds"]), {"temperature", "rainfall", "moisture", "humidity", "wind"}
                )

    def test_humidity_changes_heat_limits_through_the_authenticated_route(self):
        field_id = self.field["id"]
        outcomes = []
        for mode in ("warm_normal", "warm_humid"):
            httpx.get(SIMULATION + "/__control", params={"mode": mode})
            self.app.state.weather._cache.clear()
            response = self.client.get(f"/api/v1/weather/forecast?field_id={field_id}")
            self.assertEqual(response.status_code, 200, response.text)
            outcomes.append(response.json())
            self.assertEqual(httpx.get(SIMULATION + "/__control").json()["requests"], 1)
        normal, humid = outcomes
        self.assertEqual(normal["records"][0]["temperature"], humid["records"][0]["temperature"])
        self.assertEqual(humid["records"][0]["humidity"], 98)
        self.assertLess(
            humid["cropAssessment"]["bounds"]["temperature"]["criticalHigh"],
            normal["cropAssessment"]["bounds"]["temperature"]["criticalHigh"],
        )
        self.assertEqual(
            normal["records"][0]["cropAssessment"]["metrics"]["temperature"]["valueRiskLevel"],
            "caution",
        )
        humid_day = humid["records"][0]["cropAssessment"]
        self.assertEqual(humid_day["metrics"]["temperature"]["valueRiskLevel"], "high")
        heat_alert = next(
            alert for alert in humid_day["alerts"] if alert["ruleId"] == "heat_stress"
        )
        self.assertIn(
            dict(ruleId="humid_air", input="humidity", value=98, unit="%"), heat_alert["drivers"]
        )

    def test_one_response_has_daily_zones_and_matching_alerts_over_http(self):
        httpx.get(SIMULATION + "/__control", params={"mode": "humidity_wave"})
        field_id = self.field["id"]
        for path in (
            f"/api/v1/weather/forecast?field_id={field_id}",
            f"/api/v1/weather/history?days=7&field_id={field_id}",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["cropAssessment"]["model"]["version"], "2.0.0")
            limits = []
            for row in body["records"]:
                self.assertEqual(row["temperature"], 29)
                day = row["cropAssessment"]
                limit = day["bounds"]["temperature"]["criticalHigh"]
                limits.append(limit)
                for alert in day["alerts"]:
                    metric_bounds = day["bounds"][alert["metric"]]
                    key = {
                        "above_critical": "criticalHigh",
                        "below_critical": "criticalLow",
                        "above_good": "goodHigh",
                        "below_good": "goodLow",
                    }[alert["code"]]
                    self.assertEqual(alert["boundary"], metric_bounds[key])
            self.assertGreater(len(set(limits)), 1)
