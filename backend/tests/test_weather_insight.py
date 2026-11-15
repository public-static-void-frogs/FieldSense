import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from support import create_field, isolated_app, register
from weather_fixture import provider_payload

from app.services.weather import WeatherService


class WeatherInsightTests(unittest.TestCase):
    def test_stream_uses_selected_field_forecast_and_crop_alerts(self):
        folder, app = isolated_app()
        self.addCleanup(folder.cleanup)
        self.addCleanup(app.state.engine.dispose)
        app.state.weather.close()
        config = app.state.config
        config.gemini_enabled = True
        config.gemini_api_key = "test-key"
        app.state.weather = WeatherService(
            config,
            httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200, json=provider_payload(dict(request.url.params))
                    )
                )
            ),
        )
        self.addCleanup(app.state.weather.close)
        client = TestClient(app)
        self.addCleanup(client.close)
        path = "/api/v1/weather/forecast/insight"
        self.assertEqual(client.post(path, params={"day": "2026-11-10"}).status_code, 503)
        self.assertEqual(register(client).status_code, 201)
        field = create_field(client, crop="Corn", properties=None)
        forecast = client.get("/api/v1/weather/forecast", params={"field_id": field["id"]}).json()
        records = forecast["records"]

        def gemini(request):
            self.assertEqual(request.url.params["alt"], "sse")
            self.assertEqual(request.headers["x-goog-api-key"], "test-key")
            body = json.loads(request.content)
            context = json.loads(body["contents"][0]["parts"][0]["text"])
            self.assertEqual(context["locale"], "uk-UA")
            self.assertEqual(context["crop"], "Corn")
            self.assertEqual(
                [day["date"] for day in context["days"]], [row["date"] for row in records[1:4]]
            )
            self.assertTrue(
                any(alert["severity"] == "high" for alert in context["days"][0]["alerts"])
            )
            self.assertNotIn("latitude", context)
            events = [
                {"candidates": [{"content": {"parts": [{"text": "Увага. "}]}}]},
                {
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "Можливий холод."}]},
                            "finishReason": "STOP",
                        }
                    ]
                },
            ]
            return httpx.Response(
                200, text="".join(f"data: {json.dumps(event)}\n\n" for event in events)
            )

        params = {"day": records[1]["date"], "field_id": field["id"], "locale": "uk-UA"}
        with patch(
            "app.services.llm.httpx.AsyncClient",
            return_value=httpx.AsyncClient(
                transport=httpx.MockTransport(gemini),
            ),
        ):
            response = client.post(path, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.headers["content-type"].startswith("application/x-ndjson"))
        self.assertEqual(
            [json.loads(line) for line in response.iter_lines()],
            [
                {"delta": "Увага. "},
                {"delta": "Можливий холод."},
                {"done": True},
            ],
        )
        self.assertEqual(client.post(path, params={**params, "day": "2025-01-01"}).status_code, 404)
