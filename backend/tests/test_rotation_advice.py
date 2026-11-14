import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from support import create_field, isolated_app, register

from app.repositories.fields import FieldRecord, UserField
from app.services.rotation_advice import RotationAdvice

BASE = "/api/v1"


class RotationAdviceTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app = isolated_app()
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.user_id = register(self.client).json()["id"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def advice(self, field_id, **params):
        return self.client.get(f"{BASE}/fields/{field_id}/rotation-advice", params=params)

    def catalog_field(self, **values):
        """An imported CSB field with CDL history, selected by the signed-in user."""
        with self.app.state.sessions() as session:
            row = FieldRecord(
                area=40.0,
                longitude=-93.6,
                latitude=42.0,
                source_id="191825000000001",
                state_fips="19",
                county_fips="015",
                county="Boone",
                location_kind="interior_point",
                attributes={
                    "sourceProperties": {
                        "CDL2021": 1, "CDL2022": 5, "CDL2023": 1, "CDL2024": 1, "CDL2025": 1,
                    }
                },
                **values,
            )  # fmt: skip
            session.add(row)
            session.flush()
            session.add(UserField(user_id=self.user_id, field_id=row.id))
            session.commit()
            return row.id

    def test_declared_crop_is_assessed_by_default(self):
        field = create_field(self.client)
        result = self.advice(field["id"])
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertEqual(body["intendedCrop"], "winter_wheat")
        self.assertEqual(body["intendedCropSource"], "field_crop")
        self.assertEqual(body["historySource"]["kind"], "declared")
        self.assertFalse(body["historySource"]["satelliteEstimate"])
        self.assertEqual(body["units"], "metric")
        self.assertEqual(body["areaHa"], field["area"])
        ranks = [c["rank"] for c in body["candidates"]]
        self.assertEqual(sorted(ranks), list(range(1, len(ranks) + 1)))
        self.assertEqual(
            {c["crop"] for c in body["candidates"]}, {o["id"] for o in body["cropOptions"]}
        )
        self.assertEqual(sum(c["isIntended"] for c in body["candidates"]), 1)
        self.assertIn("no_csb_id", {gap["code"] for gap in body["dataGaps"]})

    def test_satellite_history_drives_the_default_crop_and_rules(self):
        body = self.advice(self.catalog_field()).json()
        self.assertEqual(body["region"], "IA")
        self.assertEqual((body["intendedCrop"], body["intendedCropSource"]), ("corn", "history"))
        self.assertEqual(body["historySource"]["kind"], "cdl")
        self.assertTrue(body["historySource"]["satelliteEstimate"])
        self.assertEqual([year["year"] for year in body["history"]], [2021, 2022, 2023, 2024, 2025])
        corn = next(c for c in body["candidates"] if c["isIntended"])
        self.assertTrue(corn["risks"], "corn after three corn years carries rotation risks")
        self.assertIn("yield", corn)
        for finding in corn["risks"]:
            self.assertEqual(finding["kind"], "risk")
            self.assertIn("type", finding["trigger"])

    def test_requested_crop_priorities_and_units(self):
        field_id = self.catalog_field()
        plain = self.advice(field_id, crop="soybeans").json()
        self.assertEqual(
            (plain["intendedCrop"], plain["intendedCropSource"]), ("soybeans", "requested")
        )
        weighted = self.advice(field_id, crop="soybeans", priorities=["income", "soil"]).json()
        self.assertEqual(weighted["priorities"], ["income", "soil"])
        self.assertNotEqual(
            [c["score"] for c in plain["candidates"]], [c["score"] for c in weighted["candidates"]]
        )
        self.client.put(
            f"{BASE}/users/me/settings",
            json={**self.client.get(f"{BASE}/users/me/settings").json(), "units": "imperial"},
        )
        self.assertEqual(self.advice(field_id).json()["units"], "imperial")

    def test_invalid_requests(self):
        field_id = self.catalog_field()
        self.assertEqual(self.advice(field_id, crop="bananas").status_code, 422)
        self.assertEqual(self.advice(field_id, priorities=["fame"]).status_code, 422)
        other = TestClient(self.app)
        with other:
            register(other, email="other@example.com")
            self.assertEqual(
                other.get(f"{BASE}/fields/{field_id}/rotation-advice").status_code, 404
            )

    def test_history_and_soil_come_from_the_data_root(self):
        with tempfile.TemporaryDirectory() as root:
            import duckdb

            duckdb.connect().execute(
                "COPY (SELECT '191825000000009' AS CSBID, 5::SMALLINT AS CDL2024, "
                f"1::SMALLINT AS CDL2025) TO '{Path(root) / 'cdl_history_all.parquet'}' "
                "(FORMAT PARQUET)"
            )
            soil = {"source": "test", "slope_pct": 9.0, "drainage_class": "Well drained"}
            (Path(root) / "fields.jsonl").write_text(
                json.dumps({"sourceId": "191825000000009", "soil": soil}) + "\n"
            )
            service = RotationAdvice(root, soil_lookup=False)
            record = service.engine_field(
                dict(
                    id="f", crop=None, area=10.0, sourceId="191825000000009", stateFips="19",
                    countyFips="015", sourceYear=2025, sourceProperties={"CSBACRES": 24.7},
                    geometry=dict(type="Point", coordinates=[-93.6, 42.0]),
                )
            )  # fmt: skip
        self.assertEqual(record["countyFips"], "19015")
        self.assertEqual(record["sourceProperties"]["CDL2024"], 5)
        self.assertEqual(record["sourceProperties"]["CDL2025"], 1)
        self.assertEqual(record["soil"], soil)
        self.assertNotIn("crop", record)


def write_climate_record(root: Path, years: int = 12):
    """A one-node weekly weather record at 41.9 N, 93.5 W: warm from week 15 to week 46."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    warm = range(15, 47)
    rows = [
        dict(
            ix=125, lat=41.9, lon=-93.5, year=2014 + i,
            tmax_max=[28.0] * 53,
            tmin_min=[10.0 if w in warm else -5.0 for w in range(53)],
            pr_mm=[20.0] * 53,
            gdd0=[105.0 if w in warm else 0.0 for w in range(53)],
            tmax_ge35_days=[2 if w == 28 and i < 4 else 0 for w in range(53)],
            tmax_ge30_days=[0] * 53,
            pr_ge25_days=[0] * 53,
        )
        for i in range(years)
    ]  # fmt: skip
    folder = root / "climate_record" / "iy=30"
    folder.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows), folder / "data_0.parquet")
    grid = dict(lat0=49.4, lon0=-124.75, lat_step=-0.25, lon_step=0.25, week0_doy=0, weeks=53,
                source="test grid")  # fmt: skip
    (root / "climate_record" / "grid.json").write_text(json.dumps(grid))


class WeatherRecordTests(unittest.TestCase):
    def test_advice_counts_hazards_over_the_record_and_fills_the_off_season(self):
        with tempfile.TemporaryDirectory() as root:
            write_climate_record(Path(root))
            service = RotationAdvice(root, soil_lookup=False)
            field = dict(
                id="f", crop=None, area=10.0, sourceId="191825000000001", stateFips="19",
                countyFips="015", sourceYear=2025,
                sourceProperties={f"CDL{year}": 1 for year in range(2021, 2026)},
                geometry=dict(type="Point", coordinates=[-93.6, 42.0]),
            )  # fmt: skip
            result = service.advise(field, "corn", [], "metric")
        record = result["weatherRecord"]
        self.assertEqual(
            (record["seasons"], record["firstYear"], record["lastYear"]), (12, 2014, 2025)
        )
        self.assertLess(record["distanceKm"], 30)
        corn = next(c for c in result["candidates"] if c["crop"] == "corn")
        heat = next(r for r in corn["risks"] if r["ruleId"] == "heat_at_flowering")
        self.assertEqual(heat["trigger"]["seasonsTotal"], 12)
        self.assertEqual(heat["trigger"]["record"], "weather_record")
        slot = result["offSeason"]
        self.assertEqual((slot["status"], slot["afterCrop"]), ("ok", "corn"))
        self.assertEqual(
            {o["id"]: o["level"] for o in slot["options"]},
            {"cereal_rye": "reliable", "oats": "unlikely", "winter_wheat": "reliable"},
        )

    def test_without_a_record_the_blocks_are_empty(self):
        directory, app = isolated_app()
        self.addCleanup(directory.cleanup)
        with TestClient(app) as client:
            register(client)
            field = create_field(client)
            body = client.get(f"{BASE}/fields/{field['id']}/rotation-advice").json()
        self.assertIsNone(body["weatherRecord"])
        self.assertIn("status", body["offSeason"])
        self.assertEqual(body["offSeason"]["options"], [])


if __name__ == "__main__":
    unittest.main()
