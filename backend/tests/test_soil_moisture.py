import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from support import create_field, isolated_app, register

from app.services import soil_moisture
from app.services.weather import WeatherService


class SoilMoistureTests(unittest.TestCase):
    def setUp(self):
        directory, app = isolated_app()
        self.addCleanup(directory.cleanup)
        self.addCleanup(app.state.engine.dispose)
        self.addCleanup(app.state.soil_assessments.close)
        app.state.weather.close()
        self.calls = []
        self.failure = False

        def provider(request):
            self.calls.append(request)
            params = request.url.params
            if self.failure:
                return httpx.Response(503)
            if "parameters" in params:
                return httpx.Response(
                    200,
                    json={
                        "properties": {
                            "parameter": {
                                "GWETTOP": {"20250601": 0.4, "20250602": -999},
                                "GWETROOT": {"20250601": 0.6},
                                "GWETPROF": {"20250601": 0.8},
                            }
                        }
                    },
                )
            if "start_date" in params:
                day = params["end_date"]
                time = [f"{day}T00:00", f"{day}T01:00"]
                values = {key: [0.2, 0.4] for key in params["hourly"].split(",")}
            else:
                time = ["2025-06-15T00:00", "2025-06-15T01:00", "2025-06-15T02:00"]
                values = {key: [0.25, 0.35, 0.8] for key in params["hourly"].split(",")}
                values["soil_moisture_0_to_1cm"][1] = 0.1
            return httpx.Response(
                200, json={"latitude": 42, "longitude": -94, "hourly": {"time": time, **values}}
            )

        upstream = httpx.Client(transport=httpx.MockTransport(provider))
        self.weather = app.state.weather = WeatherService(app.state.config, client=upstream)
        self.addCleanup(self.weather.close)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.assertEqual(register(self.client).status_code, 201)
        field = create_field(self.client, geometry={"type": "Point", "coordinates": [-94, 42]})
        self.path = f"/api/v1/fields/{field['id']}/soil-moisture"

    def test_latest_elapsed_hour_and_thickness_weighted_average(self):
        now = datetime(2025, 6, 15, 1, 30, tzinfo=timezone.utc)
        snapshot = soil_moisture.current(self.weather, (-94, 42), now)
        self.assertEqual(snapshot.time_utc.hour, 1)
        self.assertEqual(snapshot.profile_mean, 0.3469)
        self.assertIsNone(soil_moisture.profile({"a": 0.2, "b": None}, {"a": 1, "b": 1}))

    def test_history_sources_keep_units_and_intervals_distinct(self):
        params = {"start": "2025-06-01", "end": "2025-06-02"}
        response = self.client.get(self.path + "/history", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        daily = response.json()
        self.assertEqual(daily["series"][0]["values"]["profile_mean"], 0.3)
        self.assertEqual(daily["stats"]["soil_moisture_100_to_255cm"]["n"], 1)
        self.assertEqual(self.calls[-1].url.params["models"], "era5_land")
        hourly = self.client.get(
            self.path + "/history", params={**params, "frequency": "hourly"}
        ).json()
        self.assertEqual(hourly["stats"]["profile_mean"]["n"], 2)
        self.assertEqual(hourly["stats"]["profile_mean"]["p10"], 0.22)
        power = self.client.get(self.path + "/history", params={**params, "source": "power"}).json()
        self.assertEqual(power["unit"], "fraction_of_saturation")
        self.assertNotIn("profile_mean", power["stats"])
        self.assertEqual(len(power["series"]), 1)

    def test_seasonal_comparison_uses_prior_years_and_marks_missing_inputs(self):
        now = datetime(2025, 6, 15, 1, 30, tzinfo=timezone.utc)
        snapshot = soil_moisture.current(self.weather, (-94, 42), now)
        original = soil_moisture.history

        def history(*args):
            if args[3].year == 2022:
                raise soil_moisture.HTTPException(503)
            return original(*args)

        with patch.object(soil_moisture, "history", side_effect=history):
            result = soil_moisture.compare_to_history(self.weather, (-94, 42), snapshot, years=4)
        self.assertEqual(result.unavailable_years, [2022])
        self.assertEqual(sorted(result.years), [2021, 2023, 2024])
        self.assertEqual(result.anomaly, 0.0469)
        self.assertEqual(result.percentile, 100)
        end_dates = [request.url.params["end_date"] for request in self.calls[1:]]
        self.assertIn(date(2024, 6, 15).isoformat(), end_dates)

    def test_routes_authentication_validation_and_provider_error(self):
        other = TestClient(self.client.app)
        self.addCleanup(other.close)
        self.assertEqual(other.get(self.path).status_code, 404)
        self.assertEqual(self.client.get(self.path, params={"part": 1}).status_code, 422)
        params = {"start": "2025-01-01", "end": "2025-03-01", "frequency": "hourly"}
        self.assertEqual(self.client.get(self.path + "/history", params=params).status_code, 422)
        self.assertFalse(self.calls)
        self.failure = True
        self.assertEqual(self.client.get(self.path).status_code, 503)
