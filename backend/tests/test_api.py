import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from support import create_field, field_input, isolated_app, register

from app.core.database import Base, database_engine
from app.main import create_app
from app.repositories.fields import FieldRecord, UserField
from app.repositories.users import User

BASE = "/api/v1"


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app = isolated_app()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.app.state.engine.dispose)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.user_id = register(self.client).json()["id"]
        self.other = TestClient(self.app)
        self.addCleanup(self.other.close)
        self.other_id = register(self.other, "other@example.com").json()["id"]

    def get(self, path, client=None):
        if path == "/maps/geojson":
            path += "?bbox=-93.76,42.03,-93.72,42.06&zoom=15"
        response = (client or self.client).get(BASE + path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_no_mock_data_is_exposed_or_loaded(self):
        self.assertFalse(hasattr(self.app.state, "repository"))
        for route in [
            "/fields",
            "/fields/catalog",
            "/notifications",
            "/planning/events",
        ]:
            self.assertEqual(self.get(route), [])
        team = self.get("/help/team")
        self.assertEqual([m["id"] for m in team], ["oleh", "kate", "polina", "volodymyr", "roman"])
        self.assertTrue(all(m["linkedin"].startswith("https://www.linkedin.com/in/") for m in team))
        sources = self.get("/help/sources")
        self.assertEqual(len(sources), 14)
        self.assertTrue(all(m["url"].startswith("https://") for m in sources))
        self.assertEqual(self.get("/planning/responses"), {})
        self.assertEqual(self.get("/maps/geojson")["features"], [])
        self.assertEqual(self.get("/overview/charts"), dict(trends=[], cropAreas=[]))
        self.assertEqual(
            self.get("/planning/context")["today"],
            datetime.now(ZoneInfo("Europe/Kyiv")).date().isoformat(),
        )
        self.assertEqual(self.client.get(BASE + "/parcels/6").status_code, 404)

    def test_manual_creation_persists_only_supplied_data_and_selects_for_creator(self):
        field = create_field(self.client, properties=None, name="  New field 🌾  ")
        self.assertEqual(UUID(field["id"]).version, 4)
        self.assertEqual(field["name"], field["crop"])
        for key in (
            "parcelId",
            "properties",
            "planted",
            "health",
            "moisture",
            "nitrogen",
            "status",
        ):
            self.assertIsNone(field[key], key)
        self.assertEqual(self.get("/fields"), [field])
        self.assertEqual(self.get("/fields/catalog"), [field])
        self.assertEqual(self.get("/fields", self.other), [])
        self.assertEqual(self.get("/fields/catalog", self.other), [field])
        with self.app.state.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(FieldRecord)), 1)
            self.assertIsNotNone(session.get(UserField, (self.user_id, field["id"])))
        for route in ("", "/properties", "/history", "/recommendation", "/strategy", "/events"):
            self.assertEqual(self.other.get(f"{BASE}/fields/{field['id']}{route}").status_code, 404)

    def test_crop_history_uses_selected_field_and_clips_classified_layer(self):
        import base64

        import httpx
        import numpy as np
        from rasterio.io import MemoryFile
        from rasterio.transform import from_bounds

        from app.services import crop_history

        response = self.client.post(
            BASE + "/fields/crop-areas",
            json={
                "areas": [
                    {
                        "crop": "Corn",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[-94, 42], [-93.99, 42], [-94, 42.01], [-94, 42]]],
                        },
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        field = response.json()[0]
        path = f"/fields/{field['id']}/crop-history"
        bounds, _ = crop_history.extent(field, 0)
        with MemoryFile() as data:
            with data.open(
                driver="GTiff",
                width=8,
                height=8,
                count=1,
                dtype="uint8",
                crs="EPSG:3857",
                transform=from_bounds(*bounds, 8, 8),
            ) as raster:
                classes = np.full((8, 8), 5, dtype="uint8")
                classes[:, 4:] = 1
                raster.write(classes, 1)
            tiff = data.read()
        upstream = {
            "identify": httpx.Response(
                200,
                json={
                    "catalogItems": {
                        "features": [
                            {"attributes": {"Name": "2023_30m_cdls"}},
                            {"attributes": {"Name": "2025_10m_cdls"}},
                        ]
                    },
                    "properties": {"Values": ["81", "5"]},
                },
            ),
            "exportImage": httpx.Response(200, content=tiff),
        }
        with patch.object(
            crop_history, "upstream", side_effect=lambda operation, _: upstream[operation]
        ) as mock:
            self.assertEqual(self.other.get(BASE + path).status_code, 404)
            self.assertEqual(self.other.get(BASE + path + "/layer/2025").status_code, 404)
            self.assertEqual(
                self.client.get(BASE + path + "?lon=-93.991&lat=42.009").status_code, 422
            )
            mock.assert_not_called()
            history = self.get(path)
            self.assertEqual(history["years"][0]["crop"]["label"], "Soybeans")
            self.assertIsNone(history["years"][2]["crop"])
            layer = self.get(path + "/layer/2025")
            by_code = {item["code"]: item for item in layer["classes"]}
            self.assertEqual(set(by_code), {1, 5})
            self.assertAlmostEqual(sum(item["share"] for item in by_code.values()), 1)
            self.assertGreater(by_code[5]["share"], by_code[1]["share"])
            self.assertEqual(by_code[5]["color"], history["years"][0]["crop"]["color"])
            with (
                MemoryFile(base64.b64decode(layer["image"].split(",")[1])) as data,
                data.open() as raster,
            ):
                self.assertEqual(set(np.unique(raster.read(4))), {0, 185})
        with patch.object(crop_history, "upstream", side_effect=httpx.ReadTimeout("USDA")):
            self.assertEqual(self.client.get(BASE + path + "/layer/2024").status_code, 502)

    def test_crop_areas_merge_idempotently_and_are_private(self):
        from shapely.geometry import shape

        def area(crop, west, east):
            south, north = 42.0, 42.01
            return {
                "crop": crop,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[west, south], [east, south], [east, north], [west, north], [west, south]]
                    ],
                },
            }

        endpoint = BASE + "/fields/crop-areas"
        first = area("Corn", -94, -93.99)
        overlap = area("Corn", -93.995, -93.985)
        separate = area("Corn", -93.95, -93.94)
        legacy = create_field(self.client, crop="Corn")
        response = self.client.post(endpoint, json={"areas": [first]})
        self.assertEqual(response.status_code, 200, response.text)
        original = response.json()[0]

        additions = [overlap, separate, area("Alfalfa", -93.8, -93.79)]
        response = self.client.post(endpoint, json={"areas": additions})
        self.assertEqual(response.status_code, 200, response.text)
        corn = next(field for field in response.json() if field["crop"] == "Corn")
        self.assertEqual(corn["id"], original["id"])
        self.assertEqual(len(shape(corn["boundary"]).geoms), 2)
        self.assertAlmostEqual(corn["area"] / original["area"], 2.5, places=3)

        retry = self.client.post(endpoint, json={"areas": additions})
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json(), response.json())
        self.assertEqual({field["crop"] for field in self.get("/fields")}, {"Corn", "Alfalfa"})
        self.assertEqual(len(self.get("/fields")), 2)
        self.assertEqual(self.get("/fields/catalog"), [legacy])
        self.assertEqual(self.get("/fields", self.other), [])
        self.assertEqual(self.other.put(f"{BASE}/fields/{corn['id']}/selection").status_code, 404)
        self.assertEqual(self.client.delete(f"{BASE}/fields/{corn['id']}").status_code, 200)
        self.assertEqual(self.client.get(f"{BASE}/fields/{corn['id']}").status_code, 404)

    def test_shared_selection_is_idempotent_and_removal_preserves_catalog_and_other_users(self):
        field = create_field(self.client, parcelId=1001)
        fid = field["id"]
        for _ in range(2):
            response = self.other.put(f"{BASE}/fields/{fid}/selection")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), field)
        self.assertEqual(self.get("/fields", self.other), [field])
        with self.app.state.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(UserField)), 2)
        self.assertEqual(self.client.delete(f"{BASE}/fields/{fid}").json(), fid)
        self.assertEqual(self.client.delete(f"{BASE}/fields/{fid}").status_code, 404)
        self.assertEqual(self.get("/fields"), [])
        self.assertEqual(self.get("/fields", self.other), [field])
        self.assertEqual(self.get("/fields/catalog"), [field])
        self.other.delete(f"{BASE}/fields/{fid}")
        self.assertEqual(self.get("/fields/catalog"), [field])
        self.assertEqual(self.client.put(f"{BASE}/fields/{fid}/selection").json(), field)

    def test_field_properties_and_unavailable_related_resources(self):
        field = create_field(
            self.client,
            planted="2026-04-01",
            health=70,
            moisture=50,
            nitrogen=30,
            status="Needs attention",
        )
        fid = field["id"]
        self.assertEqual(self.get(f"/fields/{fid}/properties"), field["properties"])
        self.assertEqual(self.get(f"/fields/{fid}/history"), dict(events=[], seasons=[]))
        # Events come only from the calendar service (see test_calendar_events.py).
        self.app.state.calendar = SimpleNamespace(for_field=lambda field, settings: [])
        self.assertEqual(self.get(f"/fields/{fid}/events"), [])
        self.assertEqual(self.client.get(f"{BASE}/fields/{fid}/recommendation").status_code, 404)
        for resource in ("strategy", "rotation"):  # built by the rule engine; see its own tests
            self.assertIn(
                self.client.get(f"{BASE}/fields/{fid}/{resource}").status_code, (200, 404)
            )
        self.assertEqual(
            self.client.put(
                f"{BASE}/fields/{fid}/strategy/response", json={"status": "accepted"}
            ).json(),
            {},  # nothing to respond to without events
        )
        self.assertEqual(self.get("/notifications"), [])
        self.assertEqual(self.get("/overview/charts")["trends"], [])

    def test_maps_and_overview_use_only_callers_selections(self):
        field = create_field(self.client, parcelId=1001)
        fid = field["id"]
        own = self.get("/maps/geojson")["features"][0]
        other = self.get("/maps/geojson", self.other)["features"][0]
        self.assertEqual(own["geometry"], field["geometry"])
        self.assertEqual(own["properties"]["fieldId"], fid)
        self.assertEqual(other["properties"]["catalogFieldId"], fid)
        self.assertIsNone(other["properties"].get("fieldId"))
        self.assertEqual(self.get("/parcels/1001")["area"], field["area"])
        self.assertEqual(self.get("/overview/charts")["cropAreas"][0]["area"], field["area"])
        self.assertEqual(self.get("/overview/charts", self.other)["cropAreas"], [])
        self.client.delete(f"{BASE}/fields/{fid}")
        self.assertIsNone(self.get("/maps/geojson")["features"][0]["properties"].get("fieldId"))
        self.assertEqual(self.get("/overview/charts")["cropAreas"], [])

    def test_restart_preserves_catalog_and_selections(self):
        field = create_field(self.client)
        second = create_app(self.app.state.config)
        self.addCleanup(second.state.engine.dispose)
        with TestClient(second) as client:
            client.cookies.update(self.client.cookies)
            self.assertEqual(self.get("/fields", client), [field])
            self.assertEqual(self.get("/fields/catalog", client), [field])
            client.delete(f"{BASE}/fields/{field['id']}")
        self.assertEqual(self.get("/fields"), [])
        self.assertEqual(self.get("/fields/catalog"), [field])

    def test_duplicate_parcel_is_atomic_across_users_and_processes(self):
        second = create_app(self.app.state.config)
        self.addCleanup(second.state.engine.dispose)
        with TestClient(second) as other_process:
            other_process.cookies.update(self.other.cookies)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(
                        lambda client: client.post(
                            BASE + "/fields", json=field_input(parcelId=9123)
                        ),
                        (self.client, other_process),
                    )
                )
            self.assertEqual(sorted(response.status_code for response in results), [201, 409])
        with self.app.state.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(FieldRecord)), 1)
            self.assertEqual(session.scalar(select(func.count()).select_from(UserField)), 1)
        # An omitted parcel ID does not prevent multiple manual fields.
        create_field(self.client)
        create_field(self.client)
        self.assertEqual(len(self.get("/fields/catalog")), 3)

    def test_concurrent_selection_cannot_duplicate_relation(self):
        fid = create_field(self.client)["id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(lambda _: self.other.put(f"{BASE}/fields/{fid}/selection"), range(2))
            )
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(len(self.get("/fields", self.other)), 1)

    def test_foreign_keys_and_deletion_cascade(self):
        fid = create_field(self.client)["id"]
        self.other.put(f"{BASE}/fields/{fid}/selection")
        with self.app.state.sessions() as session:
            session.add(UserField(user_id=self.user_id, field_id=str(uuid4())))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()
            self.assertIsNone(session.get(UserField, (self.user_id, fid)))
            self.assertIsNotNone(session.get(FieldRecord, fid))
            self.assertIsNotNone(session.get(UserField, (self.other_id, fid)))
            session.execute(delete(FieldRecord).where(FieldRecord.id == fid))
            session.commit()
            self.assertIsNone(session.get(UserField, (self.other_id, fid)))

    def test_invalid_input_unknown_fields_and_missing_soil(self):
        for values in [
            dict(name=" "),
            dict(name="x" * 61),
            dict(crop="Unknown"),
            dict(parcelId=True),
            dict(parcelId=0),
            dict(area=0),
            dict(area=-1),
            dict(health=101),
            dict(moisture=-1),
            dict(planted="not-a-date"),
            dict(geometry={"type": "Point", "coordinates": []}),
            dict(geometry={"type": "Point", "coordinates": [181, 0]}),
            dict(geometry={"type": "Point", "coordinates": [0, -91]}),
            dict(geometry={"type": "Point", "coordinates": [1, 2, 3]}),
            dict(geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}),
            dict(geometry={"type": "MultiPolygon", "coordinates": []}),
            dict(geometry={"type": "Polygon", "coordinates": [[[200, 0]] * 4]}),
            dict(userId=self.other_id),
        ]:
            response = self.client.post(BASE + "/fields", json=field_input(**values))
            self.assertEqual(response.status_code, 422, response.text)
        for fid, status in [("nope", 422), (str(uuid4()), 404)]:
            self.assertEqual(self.client.get(f"{BASE}/fields/{fid}").status_code, status)
            self.assertEqual(self.client.put(f"{BASE}/fields/{fid}/selection").status_code, status)

    def test_authentication_and_openapi_contract(self):
        with TestClient(self.app) as anonymous:
            for path in ("/fields", "/fields/catalog", "/maps/summary"):
                self.assertEqual(anonymous.get(BASE + path).status_code, 200)
            fid = str(uuid4())
            self.assertEqual(anonymous.put(f"{BASE}/fields/{fid}/selection").status_code, 403)
        spec = self.get_openapi()
        self.assertIn(BASE + "/fields/catalog", spec["paths"])
        self.assertIn(BASE + "/fields/{field_id}/selection", spec["paths"])
        self.assertEqual(
            spec["components"]["schemas"]["Field"]["properties"]["id"]["format"], "uuid"
        )

    def get_openapi(self):
        return self.client.get("/openapi.json").json()

    def test_alembic_upgrade_preserves_accounts_and_matches_models(self):
        url = f"sqlite:///{Path(self.directory.name) / 'migration.db'}"
        config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        with patch.dict("os.environ", {"DATABASE_URL": url}):
            command.upgrade(config, "0002_location_coordinates")
            legacy = create_app(
                type(self.app.state.config)(
                    database_url=url,
                    jwt_secret=self.app.state.config.jwt_secret,
                    jwt_issuer=self.app.state.config.jwt_issuer,
                )
            )
            with TestClient(legacy) as client:
                self.assertEqual(register(client).status_code, 201)
            command.upgrade(config, "0004_spatial_field_catalog")
            previous_id = str(uuid4())
            previous = database_engine(url)
            with previous.begin() as connection:
                user_id = connection.scalar(text("SELECT id FROM users"))
                connection.execute(
                    text(
                        "INSERT INTO fields (id, name, crop, area, attributes, created_at, boundary_kind) "
                        "VALUES (:id, 'Old rectangle', 'Corn', 1, '{}', CURRENT_TIMESTAMP, 'estimated_bounds')"
                    ),
                    {"id": previous_id},
                )
                connection.execute(
                    text(
                        "INSERT INTO user_fields (user_id, field_id, selected_at) "
                        "VALUES (:uid, :fid, CURRENT_TIMESTAMP)"
                    ),
                    {"uid": user_id, "fid": previous_id},
                )
            previous.dispose()
            command.upgrade(config, "head")
            engine = database_engine(url)
            try:
                with engine.connect() as connection:
                    self.assertEqual(
                        compare_metadata(MigrationContext.configure(connection), Base.metadata), []
                    )
                    self.assertEqual(connection.scalar(select(func.count()).select_from(User)), 1)
                    self.assertEqual(
                        connection.scalar(select(func.count()).select_from(FieldRecord)), 0
                    )
                    self.assertEqual(
                        connection.scalar(text("SELECT field_id FROM pending_field_selections")),
                        previous_id,
                    )
                with self.assertRaisesRegex(RuntimeError, "cannot be restored"):
                    command.downgrade(config, "0002_location_coordinates")
                command.upgrade(config, "head")
            finally:
                engine.dispose()
