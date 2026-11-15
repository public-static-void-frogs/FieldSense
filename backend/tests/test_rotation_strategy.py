import unittest
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from support import create_field, isolated_app, register
from test_calendar_events import FIELD, advice, candidate, doy

from app.services.planning import fingerprint
from app.services.rotation_strategy import AdviceCache, build_plan, build_strategy

TODAY = date(2026, 11, 15)


def follow_advice():
    stages = {"planted": doy(4, 25), "flowering": doy(7, 15), "harvested": doy(9, 25)}
    return {"candidates": [candidate("corn", 1, False, 3.0, stages), candidate("oats", 2)]}


class PlanTests(unittest.TestCase):
    def test_plan_names_the_next_and_following_crop_with_dates(self):
        plan = build_plan(FIELD, advice(), follow_advice(), TODAY)
        self.assertEqual((plan["currentCrop"], plan["nextCrop"]), ("Corn", "Soybeans"))
        self.assertEqual(plan["followingCrop"], "Corn")
        self.assertEqual(plan["sowingDate"], "2027-05-01")
        self.assertEqual(plan["windowEnd"], "2027-05-15")  # the late end of the modelled window
        self.assertEqual(plan["followingDate"], "2028-04-25")
        self.assertIn("risk score of 5", plan["reasons"][0])
        self.assertIn("staying with Corn scores 12", plan["reasons"][0])
        self.assertTrue(any("Benefit: Breaks disease cycle" in r for r in plan["reasons"]))
        self.assertIn("is added to the crop history", " ".join(plan["reasons"]))
        self.assertIn("2027-05-01", plan["dateExplanation"])
        self.assertIn("not a forecast", plan["dateExplanation"])
        self.assertEqual(plan["confidence"], 100)  # 7 of 7 points between best and worst
        self.assertEqual(plan["inputs"][0]["label"], "Crop history")

    def test_following_crop_falls_back_to_another_group_without_history_to_extend(self):
        plan = build_plan(FIELD, advice(), None, TODAY)
        self.assertEqual(plan["followingCrop"], "Corn")  # soybeans -> best other group
        self.assertIn("different crop group", " ".join(plan["reasons"]))
        self.assertEqual(plan["followingDate"], "2028-05-01")  # no calendar: one year later

    def test_window_defaults_when_the_model_has_none(self):
        plan = build_plan(FIELD, advice(seasonTiming=None), follow_advice(), TODAY)
        self.assertEqual(plan["windowEnd"], "2027-05-15")  # sowing day plus 14 days
        self.assertIn("regional crop calendar", plan["dateExplanation"])

    def test_no_plan_without_candidates_or_a_sowing_date(self):
        self.assertIsNone(build_plan(FIELD, {"candidates": []}, None, TODAY))
        bare = advice(candidates=[candidate("soybeans", 1, True)])
        self.assertIsNone(build_plan(FIELD, bare, None, TODAY))


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.strategy = build_strategy(FIELD, advice(), follow_advice(), TODAY)

    def test_steps_pair_each_event_with_a_checkpoint(self):
        steps = self.strategy["steps"]
        self.assertEqual(
            [s["event"]["id"] for s in steps], [e["id"] for e in self.strategy["events"]]
        )
        by_title = {s["event"]["title"]: s["checkpoint"] for s in steps}
        self.assertIn("soil results", by_title["Soil check before sowing Soybeans"])
        self.assertIn("sowing date", by_title["Sow Soybeans"])

    def test_fit_rescales_the_engine_scores_between_candidates(self):
        (comparison,) = self.strategy["comparison"]
        self.assertEqual((comparison["current"], comparison["projected"]), (0, 100))
        stages = [(p["stage"], p["date"]) for p in self.strategy["forecast"]]
        self.assertEqual(
            stages,
            [("Today", "2026-11-15"), ("Sowing", "2027-05-01"),
             ("Flowering", "2027-07-20"), ("Harvest", "2027-10-05")],
        )  # fmt: skip
        first, last = self.strategy["forecast"][0], self.strategy["forecast"][-1]
        self.assertEqual((first["health"], last["health"]), (0, 100))
        self.assertEqual((first["progress"], last["progress"]), (0, 1))
        self.assertEqual(last["healthImprovement"], [0, 100])

    def test_contingencies_and_technical_basis_reflect_the_data(self):
        conditions = [c["condition"] for c in self.strategy["contingencies"]]
        self.assertIn("The soil is too wet or cold on the typical sowing date", conditions)
        self.assertIn(
            "A heatwave is forecast near flowering", conditions
        )  # vulnerable at flowering
        self.assertEqual(self.strategy["technicals"][2]["value"], "2027-05-01")


class StubRotation:
    def __init__(self):
        self.calls = []

    def advise(self, field, crop, priorities, units, after=None):
        self.calls.append((crop, tuple(priorities), units, after))
        return follow_advice() if after else advice()


class AdviceCacheTests(unittest.TestCase):
    field = {**FIELD, "geometry": {"coordinates": [-93.6, 42.0]}}

    def test_only_the_plain_call_is_cached_and_after_is_a_separate_entry(self):
        now = [0.0]
        stub = StubRotation()
        cache = AdviceCache(stub, clock=lambda: now[0])
        cache.advise(self.field, None, [], "metric")
        cache.advise(self.field, None, [], "metric")
        cache.advise(self.field, None, [], "metric", after="soybeans")
        cache.advise(self.field, "corn", [], "metric")
        cache.advise(self.field, "corn", [], "metric")
        self.assertEqual(
            stub.calls,
            [(None, (), "metric", None), (None, (), "metric", "soybeans"),
             ("corn", (), "metric", None), ("corn", (), "metric", None)],
        )  # fmt: skip
        now[0] = 7 * 3600
        cache.advise(self.field, None, [], "metric")
        self.assertEqual(len(stub.calls), 5)  # expired


class StrategyEndpointTests(unittest.TestCase):
    def setUp(self):
        directory, self.app = isolated_app()
        self.addCleanup(directory.cleanup)
        self.addCleanup(self.app.state.engine.dispose)
        self.app.state.advice.rotation = StubRotation()
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.assertEqual(register(self.client).status_code, 201)
        self.other = TestClient(self.app)
        self.addCleanup(self.other.close)
        self.assertEqual(register(self.other, "other@example.com").status_code, 201)
        self.field = create_field(self.client)
        self.base = f"/api/v1/fields/{self.field['id']}"

    def test_rotation_and_strategy_follow_the_response_contract(self):
        rotation = self.client.get(f"{self.base}/rotation")
        self.assertEqual(rotation.status_code, 200, rotation.text)
        plan = rotation.json()
        self.assertEqual((plan["nextCrop"], plan["followingCrop"]), ("Soybeans", "Corn"))
        self.assertNotIn("_best", plan)
        strategy = self.client.get(f"{self.base}/strategy")
        self.assertEqual(strategy.status_code, 200, strategy.text)
        body = strategy.json()
        self.assertEqual(body["plan"], plan)
        self.assertEqual(len(body["steps"]), len(body["events"]))
        self.assertTrue(all(e["fieldId"] == self.field["id"] for e in body["events"]))
        self.assertEqual(self.other.get(f"{self.base}/rotation").status_code, 404)
        self.assertEqual(self.other.get(f"{self.base}/strategy").status_code, 404)

    def test_missing_advice_is_not_found(self):
        class Broken:
            def advise(self, *args, **kwargs):
                raise RuntimeError("no data")

        self.app.state.advice.rotation = Broken()
        self.assertEqual(self.client.get(f"{self.base}/rotation").status_code, 404)
        self.assertEqual(self.client.get(f"{self.base}/strategy").status_code, 404)

    def test_responses_are_saved_per_account_and_match_the_event_fingerprint(self):
        events = self.client.get(f"{self.base}/events").json()
        self.assertTrue(events)
        self.assertEqual(self.client.get("/api/v1/planning/responses").json(), {})
        saved = self.client.put(f"{self.base}/strategy/response", json={"status": "accepted"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(set(saved.json()), {e["id"] for e in events})
        for event in events:
            response = saved.json()[event["id"]]
            self.assertEqual(response["status"], "accepted")
            self.assertEqual(response["fingerprint"], fingerprint(event))
        self.assertEqual(self.client.get("/api/v1/planning/responses").json(), saved.json())
        self.assertEqual(self.other.get("/api/v1/planning/responses").json(), {})
        self.assertEqual(
            self.other.put(
                f"{self.base}/strategy/response", json={"status": "declined"}
            ).status_code,
            404,
        )

        declined = self.client.put(f"{self.base}/strategy/response", json={"status": "declined"})
        self.assertEqual({r["status"] for r in declined.json().values()}, {"declined"})
        cleared = self.client.put(f"{self.base}/strategy/response", json={"status": "proposed"})
        self.assertEqual(cleared.json(), {})
        invalid = self.client.put(f"{self.base}/strategy/response", json={"status": "later"})
        self.assertEqual(invalid.status_code, 422)

    def test_one_event_can_be_decided_and_bulk_can_keep_decisions(self):
        events = self.client.get(f"{self.base}/events").json()
        self.assertGreater(len(events), 1)
        first, rest = events[0], events[1:]
        url = f"{self.base}/events/{first['id']}/response"
        saved = self.client.put(url, json={"status": "declined"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(set(saved.json()), {first["id"]})
        self.assertEqual(saved.json()[first["id"]]["fingerprint"], fingerprint(first))
        bulk = self.client.put(
            f"{self.base}/strategy/response", json={"status": "accepted", "onlyProposed": True}
        )
        self.assertEqual(bulk.json()[first["id"]]["status"], "declined")
        self.assertEqual({bulk.json()[e["id"]]["status"] for e in rest}, {"accepted"})
        overwritten = self.client.put(f"{self.base}/strategy/response", json={"status": "accepted"})
        self.assertEqual({r["status"] for r in overwritten.json().values()}, {"accepted"})
        cleared = self.client.put(url, json={"status": "proposed"})
        self.assertNotIn(first["id"], cleared.json())
        self.assertEqual(set(cleared.json()), {e["id"] for e in rest})
        missing = f"{self.base}/events/00000000-0000-4000-8000-000000000000/response"
        self.assertEqual(self.client.put(missing, json={"status": "accepted"}).status_code, 404)
        self.assertEqual(self.other.put(url, json={"status": "accepted"}).status_code, 404)
        self.assertEqual(self.client.put(url, json={"status": "later"}).status_code, 422)

    def test_accepting_the_strategy_adds_all_schedule_events_and_preserves_other_decisions(self):
        events = self.client.get(f"{self.base}/strategy").json()["events"]
        calendar = self.app.state.calendar
        calendar_events = self.client.get(f"{self.base}/events").json()
        event_ids = [event["id"] for event in events]
        self.assertTrue(set(event_ids) <= {event["id"] for event in calendar_events})
        other_id = str(uuid4())
        other_event = {**events[0], "id": other_id, "title": "Weather alert"}
        url = f"{self.base}/strategy/response"
        with patch.object(calendar, "for_field", return_value=[*calendar_events, other_event]):
            for event_id in (other_id, event_ids[0]):
                response = self.client.put(
                    f"{self.base}/events/{event_id}/response", json={"status": "declined"}
                )
                self.assertEqual(response.status_code, 200, response.text)
            invalid = self.client.put(url, json={"status": "accepted", "eventIds": [other_id]})
            self.assertEqual(invalid.status_code, 404, invalid.text)
            accepted = self.client.put(url, json={"status": "accepted", "eventIds": event_ids})
            self.assertEqual(accepted.status_code, 200, accepted.text)
            saved = accepted.json()
            self.assertEqual({saved[event_id]["status"] for event_id in event_ids}, {"accepted"})
            self.assertEqual(saved[other_id]["status"], "declined")

    def test_stale_responses_are_replaced_when_the_events_change(self):
        self.client.put(f"{self.base}/strategy/response", json={"status": "accepted"})
        first = self.client.get("/api/v1/planning/responses").json()

        class Shifted:
            def advise(self, field, crop, priorities, units, after=None):
                result = follow_advice() if after else advice()
                result["candidates"][0]["calendar"]["stages"]["planted"] = doy(5, 8)
                return result

        self.app.state.advice.rotation = Shifted()
        self.app.state.advice._cache.clear()
        self.app.state.calendar._rotation_cache.clear()
        self.client.put(f"{self.base}/strategy/response", json={"status": "accepted"})
        second = self.client.get("/api/v1/planning/responses").json()
        self.assertEqual(set(second), set(first))  # the same events, not accumulated rows
        changed = {i for i in first if first[i]["fingerprint"] != second[i]["fingerprint"]}
        self.assertTrue(changed)  # a shifted date is a different reviewed event


if __name__ == "__main__":
    unittest.main()
