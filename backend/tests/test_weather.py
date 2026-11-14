import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event
from types import SimpleNamespace

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from support import isolated_app, register
from weather_fixture import provider_payload

from app.core.config import Settings
from app.services.weather import WeatherService


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.preferences = SimpleNamespace(
            latitude=50.4501,
            longitude=30.5234,
            time_zone="Europe/Kyiv",
            units="metric",
            location="Kyiv",
        )
        self.handler = lambda request: httpx.Response(
            200, json=provider_payload(dict(request.url.params))
        )

        def transport(request):
            self.calls.append(request)
            return self.handler(request)

        self.client = httpx.Client(transport=httpx.MockTransport(transport))
        self.service = WeatherService(Settings(), self.client)
        self.addCleanup(self.service.close)

    def test_current_and_forecast_share_cache_and_preserve_provider_values(self):
        current = self.service.current(self.preferences)
        forecast = self.service.forecast(self.preferences)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(current["windDirection"], 90)
        self.assertEqual(current["temperature"], 12)
        self.assertEqual(forecast["records"][0]["moisture"], 23)
        self.assertEqual(len(forecast["records"]), 14)
        forecast["records"][0]["moisture"] = 999
        self.assertEqual(self.service.forecast(self.preferences)["records"][0]["moisture"], 23)

    def test_historical_dates_units_and_location_are_in_request_and_cache_identity(self):
        history = self.service.history(
            self.preferences, start=date(2025, 7, 1), end=date(2025, 7, 7)
        )
        self.assertEqual(history["records"][0]["date"], "2025-07-07")
        self.assertEqual(history["records"][-1]["date"], "2025-07-01")
        self.assertEqual(history["soilDepth"], "0–7 cm")
        self.assertEqual(history["records"][0]["moisture"], 25)
        self.preferences.units = "imperial"
        self.service.forecast(self.preferences)
        query = self.calls[-1].url.params
        self.assertEqual(query["temperature_unit"], "fahrenheit")
        self.assertEqual(query["wind_speed_unit"], "mph")
        self.assertEqual(query["precipitation_unit"], "inch")
        self.preferences.longitude = 20
        self.service.forecast(self.preferences)
        self.assertEqual(len(self.calls), 3)

    def test_missing_readings_remain_null_not_zero(self):
        def missing(request):
            data = provider_payload(dict(request.url.params))
            data["daily"]["precipitation_sum"] = [None] * 14
            data["hourly"]["soil_moisture_0_to_1cm"] = [None] * (14 * 24)
            return httpx.Response(200, json=data)

        self.handler = missing
        result = self.service.forecast(self.preferences)
        self.assertIsNone(result["records"][0]["moisture"])
        self.assertIsNone(result["records"][0]["rainfall"])

    def test_invalid_location_and_dates_do_not_call_upstream(self):
        for start, end in [
            (date(2025, 7, 7), date(2025, 7, 1)),
            (date(1939, 1, 1), date(1939, 1, 2)),
            (date(2024, 1, 1), date(2025, 1, 1)),
            (date(2025, 1, 1), None),
        ]:
            with self.assertRaises(HTTPException) as caught:
                self.service.history(self.preferences, start=start, end=end)
            self.assertEqual(caught.exception.status_code, 422)
        self.preferences.latitude = None
        with self.assertRaises(HTTPException):
            self.service.current(self.preferences)
        self.assertEqual(self.calls, [])

    def test_upstream_errors_are_explicit_and_not_cached(self):
        for status in [429, 500, 503]:
            self.handler = lambda request: httpx.Response(status, json={"error": True})
            with self.assertRaises(HTTPException) as caught:
                self.service.forecast(self.preferences)
            self.assertEqual(caught.exception.status_code, 503)
        self.handler = lambda request: httpx.Response(200, json={"daily": {}})
        with self.assertRaises(HTTPException):
            self.service.forecast(self.preferences)
        self.handler = lambda request: httpx.Response(
            200, json=provider_payload(dict(request.url.params))
        )
        self.assertEqual(len(self.service.forecast(self.preferences)["records"]), 14)
        self.assertEqual(len(self.calls), 5)

    def test_cache_expires_and_concurrent_consumers_share_one_request(self):
        now = [0]
        self.service.clock = lambda: now[0]
        entered, release = Event(), Event()

        def delayed(request):
            entered.set()
            release.wait(2)
            return httpx.Response(200, json=provider_payload(dict(request.url.params)))

        self.handler = delayed
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.service.forecast, self.preferences)
            self.assertTrue(entered.wait(1))
            second = pool.submit(self.service.current, self.preferences)
            release.set()
            first.result()
            second.result()
        self.assertEqual(len(self.calls), 1)
        now[0] = 601
        self.service.forecast(self.preferences)
        self.assertEqual(len(self.calls), 2)

    def test_authenticated_routes_use_account_settings_and_return_metadata(self):
        directory, app = isolated_app()
        self.addCleanup(directory.cleanup)
        self.addCleanup(app.state.engine.dispose)
        app.state.weather.close()
        app.state.weather = self.service
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/v1/weather/forecast").status_code, 401)
            register(client)
            self.assertEqual(client.get("/api/v1/weather/current").status_code, 422)
            settings = client.get("/api/v1/users/me/settings").json()
            settings.update(
                latitude=50.4501, longitude=30.5234, location="Kyiv", timeZone="Europe/Kyiv"
            )
            self.assertEqual(
                client.put("/api/v1/users/me/settings", json=settings).status_code, 200
            )
            forecast = client.get("/api/v1/weather/forecast")
            self.assertEqual(forecast.status_code, 200, forecast.text)
            self.assertEqual(forecast.json()["source"], "Open-Meteo")
            self.assertEqual(forecast.json()["latitude"], 50.4501)
            client.get("/api/v1/weather/current")
            self.assertEqual(len(self.calls), 1)
            self.assertEqual(
                client.get(
                    "/api/v1/weather/history?start_date=2025-07-01&end_date=2025-07-07"
                ).status_code,
                200,
            )
            self.assertEqual(
                client.get("/api/v1/weather/history?start_date=2025-07-01").status_code, 422
            )
