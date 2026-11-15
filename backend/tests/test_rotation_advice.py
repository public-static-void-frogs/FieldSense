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

    missing_id = "00000000-0000-0000-0000-000000000000"

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
            self.catalog_field_id = row.id
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

    def test_plan_ranks_the_crops_it_can_price(self):
        body = self.advice(self.catalog_field(), seasons=2).json()
        plan = body["plan"]
        self.assertEqual(plan["status"], "ok")
        self.assertEqual(plan["seasons"], 2)
        self.assertEqual(plan["firstSeason"], 2026)
        ranked = plan["crops"]
        self.assertEqual([c["rank"] for c in ranked], list(range(1, len(ranked) + 1)))
        self.assertTrue(all(len(c["steps"]) == 2 for c in ranked))
        self.assertLessEqual(sum(c["tier"] == "top" for c in ranked), 3)
        first = ranked[0]["steps"][0]
        self.assertAlmostEqual(
            first["netUsdPerAcre"], first["revenueUsdPerAcre"] - first["costUsdPerAcre"], places=1
        )
        sim = ranked[1]["simulation"]["firstSeason"]
        self.assertIsNone(ranked[0]["simulation"]["firstSeason"]["beatsTopProbability"])
        self.assertTrue(0.0 <= sim["beatsTopProbability"] <= 1.0)
        self.assertEqual(sim["years"], len(sim["outcomes"]))
        self.assertAlmostEqual(sum(o["probability"] for o in sim["outcomes"]), 1.0, places=2)
        self.assertLessEqual(sim["worst"]["netUsdPerAcre"], sim["p10UsdPerAcre"])
        self.assertLessEqual(sim["p90UsdPerAcre"], sim["best"]["netUsdPerAcre"])
        # a step's worst and best year are cash, the same figures as the first-season forecast
        for crop in ranked:
            step, season = crop["steps"][0], crop["simulation"]["firstSeason"]
            self.assertAlmostEqual(
                step["worstYearUsdPerAcre"], season["worst"]["netUsdPerAcre"], delta=0.05
            )
            self.assertAlmostEqual(
                step["bestYearUsdPerAcre"], season["best"]["netUsdPerAcre"], delta=0.05
            )
        # the candidates follow the plan; crops without a budget, price or yield come last
        priced = [c["crop"] for c in ranked]
        candidates = body["candidates"]
        self.assertEqual([c["crop"] for c in candidates[: len(priced)]], priced)
        self.assertEqual([c["rank"] for c in candidates], list(range(1, len(candidates) + 1)))
        rest = candidates[len(priced) :]
        self.assertTrue(rest)
        self.assertTrue(all(c["tier"] == "not_modelled" and c["notModelledCode"] for c in rest))
        self.assertEqual(
            {c["crop"] for c in rest},
            {g["crop"] for g in plan["notModelled"]} & set(c["crop"] for c in candidates),
        )
        self.assertEqual(self.advice(self.catalog_field_id, seasons=9).status_code, 422)

    def test_season_results_set_the_history_and_the_yield_level(self):
        field_id = self.catalog_field()
        url = f"{BASE}/fields/{field_id}/season-results"
        self.assertEqual(self.client.get(url).json(), {"results": []})
        twice = [{"year": 2024, "crop": "corn"}, {"year": 2024, "crop": "oats"}]
        self.assertEqual(self.client.put(url, json={"results": twice}).status_code, 422)
        unknown = [{"year": 2024, "crop": "unobtainium"}]
        self.assertEqual(self.client.put(url, json={"results": unknown}).status_code, 422)
        before = self.advice(field_id).json()
        corn = next(c for c in before["plan"]["crops"] if c["crop"] == "corn")
        expected = corn["simulation"]["firstSeason"]["yieldPerAcre"]["meanPerAcre"]
        self.assertEqual(before["plan"]["ownYields"], [])
        results = [
            {"year": 2026, "crop": "oats"},
            {"year": 2025, "crop": "corn", "yieldPerAcre": 2 * expected},
        ]
        saved = self.client.put(url, json={"results": results})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual([r["year"] for r in saved.json()["results"]], [2025, 2026])
        after = self.advice(field_id).json()
        # the farmer's seasons replace the satellite labels and move the plan one year on
        self.assertEqual(after["historySource"]["declaredSeasons"], 2)
        self.assertEqual(after["historySource"]["lastYear"], 2026)
        self.assertEqual(after["plan"]["firstSeason"], 2027)
        # one own year of four: the level moves a quarter of the way (the rest stay at 1.0)
        level = after["plan"]["ownYields"][0]
        self.assertEqual(level["crop"], "corn")
        self.assertEqual(len(level["points"]), 1)
        self.assertGreater(level["ratio"], 1.0)
        point = level["points"][0]
        own = point["yieldPerAcre"] / point["referenceYieldPerAcre"]
        self.assertAlmostEqual(level["ratio"], (own + 3) / 4, places=2)
        self.assertEqual(self.client.put(url, json={"results": []}).status_code, 200)
        self.assertEqual(self.advice(field_id).json()["plan"]["ownYields"], [])

    def test_economics_calculator_defaults_and_overrides(self):
        field_id = self.catalog_field()
        url = f"{BASE}/fields/{field_id}/economics"
        view = self.client.get(url).json()
        self.assertIsNone(view["inputs"])
        defaults = {c["crop"]: c for c in view["defaults"]["crops"]}
        self.assertGreater(defaults["corn"]["priceUsd"], 0)
        self.assertAlmostEqual(
            sum(defaults["corn"]["costItems"].values()), defaults["corn"]["costUsdPerAcre"], 1
        )
        self.assertGreater(view["defaults"]["landRent"]["usdPerAcre"], 0)
        twice = {"crops": [{"crop": "corn", "priceUsd": 4}, {"crop": "corn", "priceUsd": 5}]}
        self.assertEqual(self.client.put(url, json=twice).status_code, 422)
        unknown = {"crops": [{"crop": "unobtainium", "priceUsd": 4}]}
        self.assertEqual(self.client.put(url, json=unknown).status_code, 422)

        def corn(body):
            crop = next(c for c in body["plan"]["crops"] if c["crop"] == "corn")
            return crop["steps"][0], body["plan"]["economics"]

        before, used = corn(self.advice(field_id).json())
        self.assertEqual(used["landRentSource"], "not_charged")
        price = 2 * defaults["corn"]["priceUsd"]
        body = {
            "landRentUsdPerAcre": 250,
            "crops": [{"crop": "corn", "priceUsd": price, "costUsdPerAcre": 500}],
        }
        self.assertEqual(self.client.put(url, json=body).status_code, 200)
        self.assertEqual(self.client.get(url).json()["inputs"], body)
        after, used = corn(self.advice(field_id).json())
        entry = next(c for c in used["crops"] if c["crop"] == "corn")
        self.assertEqual((entry["priceSource"], entry["costSource"]), ("farmer", "farmer"))
        self.assertEqual(entry["priceUsd"], price)
        self.assertEqual(used["landRentUsdPerAcre"], 250)
        # twice the price doubles the sales; the cost is the farmer's plus the rent
        self.assertAlmostEqual(after["revenueUsdPerAcre"], 2 * before["revenueUsdPerAcre"], -1)
        self.assertAlmostEqual(
            after["costUsdPerAcre"] - before["costUsdPerAcre"],
            500 + 250 - defaults["corn"]["costUsdPerAcre"],
            places=1,
        )
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertIsNone(self.client.get(url).json()["inputs"])
        self.assertEqual(
            self.client.get(f"{BASE}/fields/{self.missing_id}/economics").status_code, 404
        )

    def test_soil_survey_is_stored_per_account_and_overrides_the_estimate(self):
        field_id = self.catalog_field()
        url = f"{BASE}/fields/{field_id}/soil-survey"
        self.assertIsNone(self.client.get(url).json())
        self.assertEqual(self.client.put(url, json={"sampledOn": "2026-04-02"}).status_code, 422)
        self.assertEqual(self.client.put(url, json={"ph": 1}).status_code, 422)
        before = self.advice(field_id, crop="alfalfa").json()
        self.assertEqual(before["soilInputs"], [])
        saved = self.client.put(url, json={"ph": 5.2, "organicMatterPct": 3.1, "phosphorusPpm": 12})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.get(url).json()["ph"], 5.2)
        after = self.advice(field_id, crop="alfalfa").json()
        inputs = {i["id"]: i for i in after["soilInputs"]}
        self.assertEqual(
            inputs["ph"], {"id": "ph", "value": 5.2, "source": "survey", "usedIn": ["rules"]}
        )
        self.assertEqual(inputs["organicMatterPct"]["usedIn"], ["soil_carbon"])
        self.assertEqual(inputs["phosphorusPpm"]["usedIn"], ["fertilizer_cost"])
        # 12 ppm Bray P1 is Low: corn gets 85 lb P2O5 instead of 67, at 0.72 USD/lb
        effect = after["plan"]["soilTest"][0]
        self.assertEqual((effect["nutrient"], effect["category"]), ("phosphorus", "low"))
        corn = next(c for c in effect["crops"] if c["crop"] == "corn")
        self.assertEqual(corn["costChangeUsdPerAcre"], 12.96)

        def cost(body):
            return next(c for c in body["plan"]["economics"]["crops"] if c["crop"] == "corn")

        self.assertAlmostEqual(
            cost(after)["costUsdPerAcre"] - cost(before)["costUsdPerAcre"], 12.96, places=2
        )
        self.assertEqual(before["plan"]["soilTest"], [])

        def rules(body):
            return {
                r["ruleId"]
                for c in body["candidates"]
                if c["crop"] == "alfalfa"
                for r in c["risks"]
            }

        self.assertTrue(rules(after) - rules(before))  # the acid soil test raises a risk

        def gaps(body):
            return {g["code"] for g in body["plan"]["gaps"]}

        self.assertIn("soil_organic_matter_unknown", gaps(before))
        self.assertNotIn("soil_organic_matter_unknown", gaps(after))
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertIsNone(self.client.get(url).json())
        self.assertEqual(
            self.client.get(f"{BASE}/fields/{self.missing_id}/soil-survey").status_code, 404
        )


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
