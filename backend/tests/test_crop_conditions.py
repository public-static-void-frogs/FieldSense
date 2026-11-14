import unittest
from copy import deepcopy
from types import SimpleNamespace
from typing import get_args
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from support import create_field, field_input, isolated_app, register
from weather_fixture import provider_payload

from app.core.config import Settings
from app.schemas.fields import Crop
from app.schemas.weather import WeatherSeries
from app.services.crop_conditions import CropWeatherRuleEngine, assessment_context
from app.services.weather import WeatherService


class CropConditionsTests(unittest.TestCase):
    def setUp(self):
        self.field = dict(field_input(), id=str(uuid4()))
        self.preferences = SimpleNamespace(
            latitude=50.45,
            longitude=30.52,
            time_zone="Europe/Kyiv",
            units="metric",
            location="Kyiv",
        )
        self.calls = []

        def respond(request):
            self.calls.append(request)
            data = provider_payload(dict(request.url.params))
            count = len(data["daily"]["time"])
            data["daily"]["temperature_2m_max"] = [18] * count
            data["daily"]["temperature_2m_min"] = [12] * count
            return httpx.Response(200, json=data)

        self.service = WeatherService(
            Settings(), httpx.Client(transport=httpx.MockTransport(respond))
        )
        self.addCleanup(self.service.close)
        self.model = CropWeatherRuleEngine()

    def predict(self, series=None, field=None):
        series = series or self.service.forecast(self.preferences)
        return self.model.predict(series, assessment_context(series, field or self.field))

    def test_complete_result_is_valid_and_contains_reusable_inputs_and_model_provenance(self):
        result = WeatherSeries.model_validate(self.predict())
        self.assertEqual(result.cropAssessment.model.kind, "rule_engine")
        self.assertEqual(result.cropAssessment.context.crop, self.field["crop"])
        self.assertEqual(result.cropAssessment.context.soilCoverage, "complete")
        self.assertEqual(
            result.cropAssessment.context.soil.soilPh, self.field["properties"]["soil"]["soilPh"]
        )
        self.assertEqual(
            set(result.cropAssessment.bounds),
            {"temperature", "moisture", "rainfall", "humidity", "wind"},
        )
        self.assertEqual(result.records[0].cropAssessment.riskLevel, "good")
        self.assertEqual(result.records[0].cropAssessment.coverage, "complete")
        self.assertTrue(0 <= result.records[0].cropAssessment.suitabilityScore <= 100)

    def test_night_frost_and_metric_extremes_create_structured_alerts(self):
        series = self.service.forecast(self.preferences)
        series["records"][0].update(low=-5, wind=50, rainfall=40)
        result = self.predict(series)
        day = result["records"][0]["cropAssessment"]
        self.assertEqual(day["riskLevel"], "high")
        self.assertEqual(day["metrics"]["temperature"]["valueRiskLevel"], "good")
        self.assertEqual(day["metrics"]["temperature"]["lowRiskLevel"], "high")
        self.assertTrue(
            any(
                a["reading"] == "low"
                and a["code"] == "below_critical"
                and a["ruleId"] == "cold_stress"
                for a in day["alerts"]
            )
        )
        self.assertTrue(
            any(a["metric"] == "wind" and a["severity"] == "high" for a in day["alerts"])
        )
        self.assertEqual(series["records"][0].get("cropAssessment"), None)

    def test_crop_soil_and_weather_window_influence_bounds(self):
        series = self.service.forecast(self.preferences)
        first = self.predict(series)["cropAssessment"]["bounds"]
        other = deepcopy(self.field)
        other["crop"] = "Corn"
        other["properties"]["soil"].update(
            soilType="Sandy loam", waterCapacity=100, organicMatter=2
        )
        second = self.predict(series, other)["cropAssessment"]["bounds"]
        self.assertNotEqual(first["temperature"], second["temperature"])
        self.assertNotEqual(first["moisture"], second["moisture"])
        self.assertNotEqual(first["rainfall"], second["rainfall"])
        for day in series["records"]:
            day["temperature"] = 35
        warm = self.predict(series)["cropAssessment"]["bounds"]
        self.assertNotEqual(first["temperature"]["ideal"], warm["temperature"]["ideal"])

    def test_missing_and_partial_readings_never_imply_good_conditions(self):
        series = self.service.forecast(self.preferences)
        for key in ("temperature", "low", "rainfall", "humidity", "wind", "moisture"):
            series["records"][0][key] = None
        missing = self.predict(series)["records"][0]["cropAssessment"]
        self.assertIsNone(missing["suitabilityScore"])
        self.assertEqual(missing["coverage"], "unavailable")
        self.assertEqual(missing["riskLevel"], "unknown")
        self.assertEqual(missing["alerts"], [])
        series["records"][0]["temperature"] = 18
        partial = self.predict(series)["records"][0]["cropAssessment"]
        self.assertEqual(partial["coverage"], "partial")
        self.assertEqual(partial["riskLevel"], "unknown")
        self.assertEqual(partial["metrics"]["temperature"]["riskLevel"], "unknown")
        self.assertEqual(partial["metrics"]["temperature"]["valueRiskLevel"], "good")

    def test_equivalent_units_preserve_scores_risks_and_converted_limits(self):
        series = self.service.forecast(self.preferences)
        series["records"][0].update(temperature=16, low=-4, rainfall=20, wind=40)
        metric = self.predict(series)
        imperial = deepcopy(series)
        imperial["units"].update(temperature="°F", rainfall="in", wind="mph")
        for day in imperial["records"]:
            for key in ("temperature", "low"):
                day[key] = day[key] * 9 / 5 + 32
            day["rainfall"] /= 25.4
            day["wind"] /= 1.609344
        converted = self.predict(imperial)
        a, b = metric["records"][0]["cropAssessment"], converted["records"][0]["cropAssessment"]
        self.assertEqual(a["suitabilityScore"], b["suitabilityScore"])
        self.assertEqual(a["metrics"], b["metrics"])
        low = metric["cropAssessment"]["bounds"]["temperature"]["criticalLow"]
        self.assertAlmostEqual(
            converted["cropAssessment"]["bounds"]["temperature"]["criticalLow"],
            low * 9 / 5 + 32,
            delta=0.02,
        )
        self.assertEqual(converted["cropAssessment"]["bounds"]["rainfall"]["unit"], "in")

    def condition_series(self, **changes):
        series = self.service.forecast(self.preferences)
        for row in series["records"]:
            row.update(temperature=29, low=18, humidity=55, moisture=25, rainfall=1, wind=8)
            row.update(changes)
        return series

    def test_humidity_changes_temperature_risk_without_changing_temperature(self):
        normal = self.predict(self.condition_series())
        humid_series = self.condition_series(humidity=98)
        before = deepcopy(humid_series)
        humid = self.predict(humid_series)
        first = normal["cropAssessment"]["bounds"]["temperature"]
        second = humid["cropAssessment"]["bounds"]["temperature"]
        self.assertLess(second["criticalHigh"], first["criticalHigh"])
        self.assertLess(second["goodHigh"], first["goodHigh"])
        self.assertEqual(normal["records"][0]["temperature"], humid["records"][0]["temperature"])
        self.assertEqual(
            normal["records"][0]["cropAssessment"]["metrics"]["temperature"]["valueRiskLevel"],
            "caution",
        )
        self.assertEqual(
            humid["records"][0]["cropAssessment"]["metrics"]["temperature"]["valueRiskLevel"],
            "high",
        )
        alert = next(
            alert
            for alert in humid["records"][0]["cropAssessment"]["alerts"]
            if alert["metric"] == "temperature"
        )
        self.assertEqual(alert["code"], "above_critical")
        self.assertEqual(alert["ruleId"], "heat_stress")
        self.assertEqual(alert["boundary"], second["criticalHigh"])
        self.assertIn(
            dict(ruleId="humid_air", input="humidity", value=98, unit="%"), alert["drivers"]
        )
        self.assertNotIn(
            "temperature_adaptation", {driver["ruleId"] for driver in alert["drivers"]}
        )
        self.assertEqual(humid_series, before)
        self.assertEqual(humid, self.predict(humid_series))
        self.assertEqual(humid["cropAssessment"]["model"]["version"], "2.0.0")

    def test_soil_water_air_heat_and_wind_have_cross_metric_effects(self):
        baseline = self.predict(self.condition_series())["cropAssessment"]["bounds"]
        dry = self.predict(self.condition_series(moisture=1))["cropAssessment"]["bounds"]
        self.assertLess(dry["temperature"]["criticalHigh"], baseline["temperature"]["criticalHigh"])
        self.assertLess(dry["wind"]["criticalHigh"], baseline["wind"]["criticalHigh"])
        wet = self.predict(self.condition_series(moisture=60, rainfall=20))["cropAssessment"][
            "bounds"
        ]
        self.assertLess(wet["rainfall"]["criticalHigh"], baseline["rainfall"]["criticalHigh"])
        self.assertLess(wet["humidity"]["criticalHigh"], baseline["humidity"]["criticalHigh"])
        self.assertGreater(
            wet["temperature"]["criticalLow"], baseline["temperature"]["criticalLow"]
        )
        hot_windy = self.predict(self.condition_series(temperature=38, humidity=20, wind=50))[
            "cropAssessment"
        ]["bounds"]
        self.assertGreater(hot_windy["moisture"]["goodLow"], baseline["moisture"]["goodLow"])

    def test_drainage_and_ph_affect_limits_with_weather_and_crop_unchanged(self):
        series = self.condition_series()
        normal = self.predict(series)["cropAssessment"]["bounds"]
        other = deepcopy(self.field)
        other["properties"]["soil"].update(drainage="Poorly drained", soilPh=4.5)
        stressed = self.predict(series, other)["cropAssessment"]["bounds"]
        for metric in ("temperature", "rainfall", "moisture", "humidity"):
            with self.subTest(metric=metric):
                self.assertLess(stressed[metric]["criticalHigh"], normal[metric]["criticalHigh"])

    def test_extreme_combinations_keep_all_crop_and_soil_limits_ordered(self):
        for crop in get_args(Crop):
            for texture in ("Loam", "Sandy loam", "Clay"):
                for readings in (
                    dict(temperature=-10, humidity=100, moisture=60, rainfall=40, wind=70),
                    dict(temperature=45, humidity=5, moisture=1, rainfall=0, wind=70),
                    dict(temperature=45, humidity=100, moisture=1, rainfall=40, wind=70),
                    dict(
                        temperature=None,
                        low=None,
                        humidity=None,
                        moisture=None,
                        rainfall=None,
                        wind=None,
                    ),
                ):
                    with self.subTest(crop=crop, texture=texture, readings=readings):
                        field = deepcopy(self.field)
                        field["crop"] = crop
                        field["properties"]["soil"].update(
                            soilType=texture,
                            drainage="Poorly drained",
                            soilPh=4.5,
                            waterCapacity=100,
                            organicMatter=2,
                        )
                        result = self.predict(self.condition_series(**readings), field)
                        WeatherSeries.model_validate(result)
                        for bounds in result["cropAssessment"]["bounds"].values():
                            self.assertLessEqual(bounds["goodLow"], bounds["ideal"])
                            self.assertLessEqual(bounds["ideal"], bounds["goodHigh"])

    def test_missing_interaction_inputs_do_not_become_dry_or_windy_conditions(self):
        normal = self.predict(self.condition_series(temperature=20))["cropAssessment"]["bounds"]
        missing = self.predict(
            self.condition_series(
                temperature=20, humidity=None, moisture=None, rainfall=None, wind=None
            )
        )
        self.assertEqual(missing["cropAssessment"]["bounds"], normal)
        self.assertEqual(missing["records"][0]["cropAssessment"]["coverage"], "partial")
        self.assertEqual(missing["records"][0]["cropAssessment"]["riskLevel"], "unknown")

    def test_all_crop_profiles_use_distinct_temperature_and_water_ranges_without_field_soil(self):
        series = self.condition_series(moisture=60)
        bounds = []
        for crop in get_args(Crop):
            field = dict(self.field, crop=f" {crop.upper()} ", properties=None)
            result = WeatherSeries.model_validate(self.predict(series, field))
            self.assertEqual(result.cropAssessment.context.crop, crop)
            self.assertEqual(result.cropAssessment.context.soilCoverage, "unavailable")
            self.assertEqual(result.records[0].cropAssessment.coverage, "complete")
            bounds.append(result.records[0].cropAssessment.bounds)
        self.assertEqual(len({row["temperature"].criticalLow for row in bounds}), len(bounds))
        self.assertEqual(len({row["moisture"].goodLow for row in bounds}), len(bounds))
        self.assertEqual(len({row["rainfall"].criticalHigh for row in bounds}), len(bounds))
        self.assertIsNone(assessment_context(series, dict(self.field, crop="Rice")))

    def test_partial_field_soil_applies_only_available_adjustments(self):
        series = self.condition_series(rainfall=30)
        without_soil = self.predict(series, dict(self.field, properties=None))
        partial = self.predict(
            series, dict(self.field, properties={"soil": {"drainage": "Poorly drained"}})
        )
        baseline = without_soil["cropAssessment"]["bounds"]
        assessed = partial["cropAssessment"]
        self.assertEqual(assessed["context"]["soilCoverage"], "partial")
        self.assertIsNone(assessed["context"]["soil"]["soilType"])
        self.assertEqual(assessed["bounds"]["temperature"], baseline["temperature"])
        self.assertLess(
            assessed["bounds"]["rainfall"]["criticalHigh"], baseline["rainfall"]["criticalHigh"]
        )
        alert = next(
            alert
            for alert in partial["records"][0]["cropAssessment"]["alerts"]
            if alert["metric"] == "rainfall"
        )
        self.assertEqual(alert["ruleId"], "heavy_precipitation")
        self.assertEqual(
            alert["drivers"],
            [
                dict(
                    ruleId="poor_drainage",
                    input="drainage",
                    value="Poorly drained",
                    unit=None,
                )
            ],
        )

    def test_alert_severity_matches_the_published_boundary(self):
        series = self.condition_series(moisture=40, humidity=72)
        bounds = self.predict(series)["records"][0]["cropAssessment"]["bounds"]["rainfall"]
        series["records"][0]["rainfall"] = bounds["criticalHigh"]
        series["records"][1]["rainfall"] = round(bounds["criticalHigh"] - 0.01, 2)
        first, second = self.predict(series)["records"][:2]
        alert = next(
            alert for alert in first["cropAssessment"]["alerts"] if alert["metric"] == "rainfall"
        )
        self.assertEqual(alert["value"], alert["boundary"])
        self.assertEqual(alert["severity"], "high")
        self.assertEqual(second["cropAssessment"]["metrics"]["rainfall"]["riskLevel"], "caution")

    def test_scoped_routes_use_field_geometry_time_zone_and_validate_ids_before_weather(self):
        directory, app = isolated_app()
        self.addCleanup(directory.cleanup)
        self.addCleanup(app.state.engine.dispose)
        app.state.weather.close()
        app.state.weather = self.service
        with TestClient(app) as client:
            registered = register(client, latitude=50.45, longitude=30.52)
            self.assertEqual(registered.status_code, 201, registered.text)
            settings = client.get("/api/v1/users/me/settings").json()
            settings["timeZone"] = "Europe/Kyiv"
            self.assertEqual(
                client.put("/api/v1/users/me/settings", json=settings).status_code, 200
            )
            fid = create_field(client)["id"]
            response = client.get(f"/api/v1/weather/forecast?field_id={fid}")
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result["cropAssessment"]["context"]["fieldId"], fid)
            self.assertEqual(result["timeZone"], "Europe/Kyiv")
            self.assertEqual(result["latitude"], 42.045)
            self.assertEqual(result["longitude"], -93.745)
            self.assertEqual(client.get("/api/v1/weather/forecast?field_id=nope").status_code, 422)
            self.assertEqual(
                client.get(f"/api/v1/weather/forecast?field_id={uuid4()}").status_code, 404
            )
            self.assertEqual(len(self.calls), 1)
            response = client.get(
                f"/api/v1/weather/history?field_id={fid}&start_date=2025-07-01&end_date=2025-07-07"
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(
                response.json()["cropAssessment"]["context"]["climate"]["source"], "history_window"
            )
            self.assertIsNone(client.get("/api/v1/weather/forecast").json()["cropAssessment"])
            incomplete = create_field(client, name="Field without soil", properties=None)["id"]
            for endpoint in ("forecast", "history"):
                response = client.get(f"/api/v1/weather/{endpoint}?field_id={incomplete}")
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual((result["latitude"], result["longitude"]), (42.045, -93.745))
                self.assertTrue(result["records"])
                self.assertEqual(result["cropAssessment"]["context"]["soilCoverage"], "unavailable")
                self.assertTrue(
                    all(record["cropAssessment"]["bounds"] for record in result["records"])
                )

    def test_daily_limits_and_alerts_follow_that_days_inputs_not_window_averages(self):
        series = self.condition_series()
        series["records"][1]["humidity"] = 98
        result = self.predict(series)
        normal, humid = result["records"][:2]
        a, b = normal["cropAssessment"], humid["cropAssessment"]
        self.assertEqual(normal["temperature"], humid["temperature"])
        self.assertLess(
            b["bounds"]["temperature"]["criticalHigh"], a["bounds"]["temperature"]["criticalHigh"]
        )
        self.assertEqual(a["metrics"]["temperature"]["valueRiskLevel"], "caution")
        self.assertEqual(b["metrics"]["temperature"]["valueRiskLevel"], "high")
        alert = next(alert for alert in b["alerts"] if alert["metric"] == "temperature")
        self.assertEqual(alert["boundary"], b["bounds"]["temperature"]["criticalHigh"])
        self.assertEqual(set(b["bounds"]), set(result["cropAssessment"]["bounds"]))
        # Reordering the history or selecting a shorter window must not change daily limits.
        reverse = deepcopy(series)
        reverse["records"].reverse()
        for row in self.predict(reverse)["records"]:
            original = next(day for day in result["records"] if day["date"] == row["date"])
            self.assertEqual(row["cropAssessment"], original["cropAssessment"])
        single = {**series, "records": [series["records"][1]]}
        self.assertEqual(self.predict(single)["records"][0]["cropAssessment"], b)
        WeatherSeries.model_validate(result)
