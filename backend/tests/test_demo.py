import base64
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from support import create_field, field_input, isolated_app, register

from app.repositories.users import User
from app.services.section_analysis import AnalysisUnavailable

BASE = "/api/v1"


class DemoTests(unittest.TestCase):
    def setUp(self):
        directory, self.app = isolated_app(gemini_enabled=False)
        self.addCleanup(directory.cleanup)
        self.addCleanup(self.app.state.engine.dispose)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def get(self, path):
        response = self.client.get(BASE + path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_anonymous_demo_access_is_read_only_and_isolated(self):
        account = self.get("/auth/me")
        self.assertIs(account["isDemo"], True)
        response = self.client.get(BASE + "/auth/me")
        self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(self.get("/fields"), [])
        self.assertEqual(self.get("/planning/events"), [])
        field_id = "00000000-0000-4000-8000-000000000001"
        event_id = "00000000-0000-4000-8000-000000000002"

        writes = [
            ("POST", "/fields", field_input()),
            ("POST", "/fields/crop-areas", {"areas": []}),
            ("PUT", f"/fields/{field_id}/selection", None),
            ("DELETE", f"/fields/{field_id}", None),
            ("PUT", "/auth/me", {"fullName": "Changed", "email": "change@example.com"}),
            ("PUT", "/users/me/settings", self.get("/users/me/settings")),
            ("PUT", f"/fields/{field_id}/strategy/response", {"status": "accepted"}),
            ("PUT", f"/fields/{field_id}/events/{event_id}/response", {"status": "accepted"}),
        ]
        for method, path, body in writes:
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.request(method, BASE + path, json=body).status_code, 403
                )

        with TestClient(self.app) as another_demo, TestClient(self.app) as regular:
            self.assertEqual(register(regular).status_code, 201)
            self.assertEqual(regular.get(BASE + "/fields").json(), [])
            private_field = create_field(regular)
            self.assertEqual(self.get("/fields"), [])
            self.assertEqual(self.get("/maps/summary")["total"], 1)
            features = self.get("/maps/geojson?bbox=-94,42,-93,43&zoom=14")["features"]
            self.assertEqual([feature["id"] for feature in features], [private_field["id"]])
            self.assertEqual(
                self.client.get(BASE + f"/fields/{private_field['id']}").status_code, 404
            )
            self.assertEqual(regular.get(BASE + f"/fields/{field_id}").status_code, 404)
            self.assertEqual(self.client.post(BASE + "/auth/logout").status_code, 200)
            self.assertEqual(self.get("/auth/me"), account)
            self.assertEqual(another_demo.get(BASE + "/auth/me").json(), account)
        with self.app.state.sessions() as database:
            self.assertEqual(
                [user.email for user in database.scalars(select(User))], ["farmer@example.com"]
            )

    def test_demo_manual_selection_invokes_the_standard_analyzer(self):
        # A georeferenced image header is enough to reach the analyzer boundary.
        png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + b"\0\0\0\x01" * 2 + b"\0" * 9
        point = {"id": "selected-field", "coordinates": [-93.5, 42.5]}
        bounds = [-94, 42, -93, 43]
        ring = [[-94, 42], [-93, 42], [-93, 43], [-94, 43], [-94, 42]]
        body = {
            "image": {
                "dataUrl": "data:image/png;base64," + base64.b64encode(png).decode(),
                "width": 1,
                "height": 1,
                "bounds": bounds,
                "crs": "EPSG:3857",
            },
            "points": [point],
            "region": {"type": "Polygon", "coordinates": [ring]},
        }
        with patch.object(
            self.app.state.section_analyzer,
            "analyze",
            side_effect=AnalysisUnavailable("Test model"),
        ) as analyze:
            response = self.client.post(BASE + "/maps/sections/analyze", json=body)
        self.assertEqual(response.status_code, 503, response.text)
        analyze.assert_called_once()
        self.assertEqual(analyze.call_args.args[0].points[0].id, point["id"])
        self.assertEqual(self.get("/fields"), [])
