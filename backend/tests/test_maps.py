import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import insert
from support import create_field, isolated_app, register

from app.repositories.fields import FieldRecord
from app.repositories.maps import MapDataset
from app.services.maps import MAX_FEATURES, cluster_feature, rebuild_cells
from scripts.import_field_points import COLUMNS, source_record

BASE = "/api/v1"


class MapTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app = isolated_app()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.app.state.engine.dispose)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        register(self.client)

    def viewport(self, bounds="-93.76,42.03,-93.72,42.06", zoom=15):
        response = self.client.get(BASE + "/maps/geojson", params=dict(bbox=bounds, zoom=zoom))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_bounds_and_zoom_are_required_and_validated(self):
        self.assertEqual(self.client.get(BASE + "/maps/geojson").status_code, 422)
        for bounds in [
            "1,2,3",
            "1,2,3,4,5",
            "nan,0,1,1",
            "-181,0,1,1",
            "0,0,0,1",
            "0,0,1,91",
            "1,1,0,0",
            "west,south,east,north",
        ]:
            self.assertEqual(
                self.client.get(
                    BASE + "/maps/geojson", params=dict(bbox=bounds, zoom=12)
                ).status_code,
                422,
            )
        for zoom in [-1, 21, "nan"]:
            self.assertEqual(
                self.client.get(
                    BASE + "/maps/geojson", params=dict(bbox="0,0,1,1", zoom=zoom)
                ).status_code,
                422,
            )

    def test_only_intersecting_fields_are_loaded_and_selection_is_private(self):
        field = create_field(self.client)
        create_field(
            self.client,
            geometry={"type": "Point", "coordinates": [30, 50]},
        )
        result = self.viewport()
        self.assertEqual(result["mode"], "fields")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["features"][0]["id"], field["id"])
        self.assertEqual(result["features"][0]["properties"]["fieldId"], field["id"])
        with TestClient(self.app) as other:
            register(other, "maps-other@example.com")
            other_result = other.get(
                BASE + "/maps/geojson?bbox=-93.76,42.03,-93.72,42.06&zoom=15"
            ).json()
            self.assertNotIn("fieldId", other_result["features"][0]["properties"])
        self.assertEqual(self.viewport("0,0,1,1")["features"], [])

    def test_low_zoom_groups_all_fields_without_polygon_payloads(self):
        create_field(self.client)
        create_field(self.client)
        result = self.viewport("-180,-85,180,85", 2)
        self.assertEqual(result["mode"], "clusters")
        self.assertEqual(result["total"], 2)
        self.assertEqual(sum(f["properties"]["count"] for f in result["features"]), 2)
        self.assertTrue(all(f["geometry"]["type"] == "Point" for f in result["features"]))
        self.assertLessEqual(len(result["features"]), MAX_FEATURES)
        self.assertEqual(self.viewport("-180,-85,180,85", 19)["mode"], "clusters")

    def test_dense_views_group_instead_of_truncating_or_overloading_client(self):
        rows = [
            dict(
                id=str(uuid4()),
                name=f"Field {i}",
                crop=None,
                area=1,
                attributes={},
                location_kind="interior_point",
                longitude=-93.7395,
                latitude=42.0405,
            )
            for i in range(MAX_FEATURES + 1)
        ]
        with self.app.state.engine.begin() as connection:
            connection.execute(insert(FieldRecord), rows)
            rebuild_cells(connection)
        result = self.viewport()
        self.assertEqual(result["mode"], "clusters")
        self.assertEqual(result["total"], MAX_FEATURES + 1)
        self.assertEqual(
            sum(f["properties"]["count"] for f in result["features"]), MAX_FEATURES + 1
        )
        self.assertLessEqual(len(result["features"]), MAX_FEATURES)

    def test_source_import_preserves_identity_area_quality_and_unknown_measurements(self):
        feature = dict(
            type="Feature",
            geometry=dict(type="Point", coordinates=[-103.248, 35.854]),
            properties=dict(
                CSBID="351825000000001",
                CSBACRES=8.014266533798391,
                STATEFIPS="35",
                CNTYFIPS="059",
                CNTY="Union",
                centroid_lon=-103.249,
                centroid_lat=35.853,
                point_method="polylabel",
                inner_radius_m=37.18,
            ),
        )
        now = datetime.now(timezone.utc)
        record = source_record(feature, now, "35", "059")
        self.assertEqual(record[0], source_record(feature, now, "35", "059")[0])
        values = dict(zip(COLUMNS, record))
        values["attributes"] = json.loads(values["attributes"])
        row = FieldRecord(**values)
        with self.app.state.sessions() as session:
            session.add(row)
            session.commit()
        fid = record[0]
        field = self.client.get(BASE + f"/fields/catalog/{fid}").json()
        self.assertEqual(field["locationKind"], "interior_point")
        self.assertEqual(field["sourceId"], feature["properties"]["CSBID"])
        self.assertAlmostEqual(field["area"], feature["properties"]["CSBACRES"] * 0.40468564224)
        self.assertEqual(field["sourceProperties"], feature["properties"])
        self.assertIsNone(field["crop"])
        self.assertIsNone(field["health"])
        self.assertEqual(field["geometry"], feature["geometry"])
        self.assertEqual(self.client.put(BASE + f"/fields/{fid}/selection").status_code, 200)
        self.assertEqual(self.client.get(BASE + "/overview/charts").status_code, 200)
        self.assertEqual(
            self.client.get(BASE + "/overview/charts").json()["cropAreas"][0]["name"],
            "Not supplied",
        )
        self.assertEqual(self.client.get(BASE + f"/fields/{fid}/properties").status_code, 404)

    def test_manual_additions_update_imported_summary_and_every_aggregate_level(self):
        with self.app.state.sessions() as session:
            session.add(
                MapDataset(
                    id="csb-2025",
                    metadata_={
                        "status": "ready",
                        "total": 0,
                        "bounds": [0, 0, 0, 0],
                        "source": "USDA NASS CSB 2025",
                        "locationKind": "interior_point",
                        "importedAt": None,
                    },
                )
            )
            session.commit()
        create_field(self.client)
        result = self.client.get(BASE + "/maps/summary").json()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["bounds"], [-93.745, 0, 0, 42.045])
        self.assertEqual(self.viewport("-180,-90,180,90", 2)["total"], 1)

    def test_importing_catalog_rejects_map_reads_and_manual_writes(self):
        with self.app.state.sessions() as session:
            session.add(MapDataset(id="csb-2025", metadata_={"status": "importing"}))
            session.commit()
        response = self.client.get(BASE + "/maps/geojson?bbox=-94,42,-93,43&zoom=15")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["Retry-After"], "30")
        from support import field_input

        self.assertEqual(self.client.post(BASE + "/fields", json=field_input()).status_code, 503)

    def test_pole_and_dateline_points_belong_to_valid_aggregate_cells(self):
        create_field(self.client, geometry={"type": "Point", "coordinates": [180, 90]})
        with self.app.state.engine.begin() as connection:
            rebuild_cells(connection)
        result = self.viewport("179,89,180,90", 2)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["features"][0]["properties"]["count"], 1)

    def test_catalog_is_paginated_and_summary_is_small(self):
        create_field(self.client)
        create_field(self.client)
        response = self.client.get(BASE + "/fields/catalog?limit=1")
        self.assertEqual(len(response.json()), 1)
        second = self.client.get(BASE + "/fields/catalog?limit=1&offset=1").json()
        self.assertNotEqual(response.json()[0]["id"], second[0]["id"])
        self.assertEqual(self.client.get(BASE + "/fields/catalog?limit=501").status_code, 422)
        summary = self.client.get(BASE + "/maps/summary").json()
        self.assertEqual(summary["total"], 2)
        self.assertIn("defaultCenter", summary)

    def test_partial_edge_groups_keep_a_visible_zoom_target(self):
        cell = SimpleNamespace(
            level=6,
            x=10,
            y=20,
            count=100,
            area=200,
            min_lon=-99.0,
            min_lat=40.0,
            max_lon=-98.0,
            max_lat=41.0,
        )
        view = (-98.1, 40.9, -98.0, 41.0)
        feature = cluster_feature(cell, view)
        longitude, latitude = feature["geometry"]["coordinates"]
        self.assertTrue(view[0] <= longitude <= view[2])
        self.assertTrue(view[1] <= latitude <= view[3])
        self.assertEqual(feature["properties"]["bounds"], [-99.0, 40.0, -98.0, 41.0])
