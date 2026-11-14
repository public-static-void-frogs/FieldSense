import unittest
from datetime import date
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from support import create_field, isolated_app, register

from app.services.calendar_events import (
    CalendarEvents,
    drought_events,
    rotation_events,
    weather_events,
)
from app.services.drought import DroughtMonitor, dominant

FIELD = {"id": "11111111-1111-1111-1111-111111111111", "name": "North", "crop": "Corn"}
TODAY = date(2026, 11, 15)


def doy(month, day):
    return date(2027, month, day).timetuple().tm_yday


def candidate(crop, rank, intended=False, score=10.0, stages=None):
    return {
        "crop": crop, "label": crop.title(), "rank": rank, "isIntended": intended,
        "score": score,
        "group": "legume" if crop == "soybeans" else "grain", "soil": [], "dataGaps": [],
        "risks": [{"title": "Repeat crop"}], "benefits": [{"title": "Breaks disease cycle"}],
        "calendar": {"stages": stages or {}, "localShiftDays": {"planted": -3}},
    }  # fmt: skip


def advice(**extra):
    stages = {"planted": doy(5, 1), "flowering": doy(7, 20), "harvested": doy(10, 5)}
    return {
        "candidates": [
            candidate("soybeans", 1, False, 5.0, stages),
            candidate("corn", 2, True, 12.0, {"harvested": doy(10, 1)}),
        ],
        "offSeason": {
            "status": "ok", "afterCrop": "corn", "seedingDoy": doy(11, 20),
            "options": [
                {"id": "rye", "label": "Cereal rye", "level": "reliable", "share": 0.9,
                 "seasonsMet": 18, "seasonsTotal": 20},
                {"id": "oats", "label": "Oats", "level": "unlikely", "share": 0.2,
                 "seasonsMet": 4, "seasonsTotal": 20},
            ],
        },
        "seasonTiming": {
            "crops": {
                "soybeans": {
                    "stages": {"sow": {"early": "04-20", "typical": "05-01", "late": "05-15"}},
                    "heatAtFlowering": {"vulnerable": True},
                }
            }
        },
        **extra,
    }  # fmt: skip


class RotationEventTests(unittest.TestCase):
    def setUp(self):
        self.events = {e["title"]: e for e in rotation_events(FIELD, advice(), TODAY)}

    def test_dates_follow_the_calendar_of_the_best_ranked_crop(self):
        self.assertEqual(self.events["Sow Soybeans"]["date"], "2027-05-01")
        self.assertEqual(self.events["Sow Soybeans"]["priority"], "High priority")  # changes crop
        self.assertIn("score 5 against 12 for Corn", self.events["Sow Soybeans"]["description"])
        self.assertIn("04-20 to 05-15", self.events["Sow Soybeans"]["description"])
        self.assertEqual(self.events["Soil check before sowing Soybeans"]["date"], "2027-04-10")
        self.assertEqual(self.events["Prepare the field for Soybeans"]["date"], "2027-04-21")
        scout = self.events["Scout Soybeans at flowering"]
        self.assertEqual((scout["date"], scout["priority"]), ("2027-07-20", "Important"))
        self.assertEqual(self.events["Harvest Soybeans"]["date"], "2027-10-05")

    def test_current_crop_harvest_and_cover_crop_only_when_still_ahead(self):
        self.assertNotIn("Harvest Corn", self.events)  # 1 October has passed
        self.assertEqual(self.events["Seed cereal rye"]["date"], "2026-11-20")
        self.assertNotIn("Seed oats", self.events)
        earlier = {e["title"]: e for e in rotation_events(FIELD, advice(), date(2026, 8, 1))}
        self.assertEqual(earlier["Harvest Corn"]["date"], "2026-10-01")

    def test_every_event_has_a_stable_id_and_the_calendar_fields(self):
        again = rotation_events(FIELD, advice(), TODAY)
        self.assertEqual([e["id"] for e in again], [e["id"] for e in self.events.values()])
        for event in again:
            self.assertEqual(event["fieldId"], FIELD["id"])
            self.assertTrue(event["rationale"] and event["duration"])

    def test_no_calendar_or_candidates_gives_no_sowing(self):
        self.assertEqual(rotation_events(FIELD, {"candidates": []}, TODAY), [])
        bare = advice(candidates=[candidate("soybeans", 1, True)], offSeason=None)
        self.assertEqual(rotation_events(FIELD, bare, TODAY), [])


def day(index, **values):
    base = dict(
        date=f"2026-07-{index + 10:02d}", temperature=25.0, low=15.0, rainfall=0.0, wind=10.0,
        weatherCode=1, cropAssessment={"alerts": []},
    )  # fmt: skip
    return {**base, **values}


def series(records, units=None):
    return {
        "records": records,
        "units": units or {"temperature": "°C", "rainfall": "mm", "wind": "km/h"},
        "cropAssessment": {"context": {"crop": "Corn"}},
    }


class WeatherEventTests(unittest.TestCase):
    def titles(self, records, **kw):
        return {e["title"]: e for e in weather_events(FIELD, series(records, **kw))}

    def test_heatwave_needs_three_hot_days_in_a_row(self):
        hot = [day(i, temperature=33.0) for i in range(3)] + [day(3), day(4, temperature=36.0)]
        wave = self.titles(hot)["Heatwave expected"]
        self.assertEqual((wave["date"], wave["duration"]), ("2026-07-10", "3 days"))
        self.assertEqual(wave["priority"], "Important")
        self.assertEqual(wave["category"], "Weather alert")
        hot[2]["temperature"] = 36.0
        self.assertEqual(self.titles(hot)["Heatwave expected"]["priority"], "High priority")
        self.assertNotIn("Heatwave expected", self.titles([day(0, temperature=40.0), day(1)]))

    def test_imperial_units_are_converted(self):
        units = {"temperature": "°F", "rainfall": "in", "wind": "mph"}
        records = [day(i, temperature=95.0) for i in range(3)]  # 35 C
        self.assertIn("Heatwave expected", self.titles(records, units=units))
        events = self.titles([day(0, rainfall=2.5, wind=40.0)], units=units)  # 63 mm, 64 km/h
        self.assertIn("Extreme rainfall expected", events)
        self.assertIn("Damaging wind expected", events)

    def test_extreme_conditions_and_season_limited_frost(self):
        events = self.titles([day(0, weatherCode=96, low=-3.0)])
        self.assertIn("Thunderstorms expected", events)
        self.assertIn("Hard frost expected", events)
        winter = day(0, low=-10.0, date="2026-12-10")
        self.assertNotIn("Hard frost expected", self.titles([winter]))

    def test_crop_alerts_reuse_the_crop_model_and_skip_what_a_heatwave_covers(self):
        alert = {"ruleId": "dry_soil", "severity": "high"}
        records = [day(i, cropAssessment={"alerts": [alert]}) for i in range(2)]
        irrigation = self.titles(records)["Dry soil risk for Corn"]
        self.assertEqual((irrigation["category"], irrigation["duration"]), ("Irrigation", "2 days"))
        stress = {"ruleId": "heat_stress", "severity": "high"}
        hot = [day(i, temperature=34.0, cropAssessment={"alerts": [stress]}) for i in range(3)]
        events = self.titles(hot)
        self.assertIn("Heatwave expected", events)
        self.assertNotIn("Heat stress risk for Corn", events)
        caution = [day(0, cropAssessment={"alerts": [{**alert, "severity": "caution"}]})]
        self.assertEqual(self.titles(caution), {})


STATUS = {
    "county": "Polk County", "fips": "19153", "mapDate": "2026-11-10", "category": "d2",
    "shares": {"d0": 100.0, "d1": 80.0, "d2": 45.0, "d3": 0.0, "d4": 0.0},
    "weeksCompared": 6, "trend": "worsening",
}  # fmt: skip


class DroughtTests(unittest.TestCase):
    def test_event_reports_category_trend_and_priority(self):
        (event,) = drought_events(FIELD, STATUS, TODAY)
        self.assertEqual(event["title"], "Severe drought in Polk County")
        self.assertEqual((event["date"], event["priority"]), ("2026-11-15", "High priority"))
        self.assertIn("45%", event["description"])
        (mild,) = drought_events(FIELD, {**STATUS, "category": "d1", "trend": "steady"}, TODAY)
        self.assertEqual(mild["priority"], "Important")
        self.assertEqual(drought_events(FIELD, {**STATUS, "category": None}, TODAY), [])
        self.assertEqual(drought_events(FIELD, None, TODAY), [])

    def test_dominant_category_needs_a_third_of_the_county(self):
        self.assertEqual(dominant({"d0": 90, "d1": 31, "d2": 29}), "d1")
        self.assertIsNone(dominant({"d0": 10, "d1": 0}))

    def monitor(self, rows, county=None):
        calls = []
        found = {"FIPS": "19153", "name": "Polk"} if county is None else county

        def handler(request):
            calls.append(str(request.url))
            if "fcc.gov" in str(request.url):
                return httpx.Response(200, json={"County": found})
            return httpx.Response(200, json=rows)

        return DroughtMonitor(httpx.Client(transport=httpx.MockTransport(handler))), calls

    def test_status_reads_the_weekly_maps_and_caches_them(self):
        def row(map_date, d1, d2):
            return {"mapDate": f"{map_date}T00:00:00", "d0": 100.0, "d1": d1, "d2": d2,
                    "d3": 0.0, "d4": 0.0}  # fmt: skip

        monitor, calls = self.monitor([row("2026-11-10", 80.0, 40.0), row("2026-10-06", 50.0, 0.0)])
        status = monitor.status(41.6, -93.6, TODAY)
        self.assertEqual((status["category"], status["trend"]), ("d2", "worsening"))
        self.assertEqual(status["mapDate"], "2026-11-10")
        self.assertTrue(any("aoi=19153" in url and "statisticsType=1" in url for url in calls))
        monitor.status(41.6, -93.6, TODAY)
        self.assertEqual(len(calls), 2)  # one county lookup, one Monitor request

    def test_outside_the_us_has_no_status(self):
        monitor, _ = self.monitor([], county={})
        self.assertIsNone(monitor.status(50.4, 30.5, TODAY))


class StubWeather:
    def __init__(self, records):
        self.records = records

    def today(self, preferences):
        return TODAY

    def forecast(self, location):
        return {
            **series(self.records), "latitude": location.latitude, "longitude": location.longitude,
            "dataKind": "forecast",
        }  # fmt: skip


class CalendarServiceTests(unittest.TestCase):
    preferences = SimpleNamespace(units="metric", time_zone="UTC", location=None)

    def service(self, rotation, drought, records=()):
        crop_model = SimpleNamespace(predict=lambda series, context: series)
        return CalendarEvents(StubWeather(list(records)), crop_model, rotation, drought)

    def field(self):
        return {**FIELD, "area": 5, "geometry": {"type": "Point", "coordinates": [-93.6, 42.0]}}

    def test_sources_are_merged_in_date_order_and_failures_are_isolated(self):
        class Rotation:
            def advise(self, *args):
                return advice()

        class Drought:
            def status(self, lat, lng, today):
                return STATUS

        service = self.service(Rotation(), Drought())
        events = service.for_field(self.field(), self.preferences)
        dates = [e["date"] for e in events]
        self.assertEqual(dates, sorted(dates))
        titles = {e["title"] for e in events}
        self.assertIn("Sow Soybeans", titles)
        self.assertIn("Severe drought in Polk County", titles)

        class Broken:
            def advise(self, *args):
                raise RuntimeError("no data")

            def status(self, *args):
                raise RuntimeError("down")

        events = self.service(Broken(), Broken()).for_field(self.field(), self.preferences)
        self.assertEqual(events, [])

    def test_rotation_result_is_cached_per_day(self):
        calls = []

        class Rotation:
            def advise(self, *args):
                calls.append(args)
                return advice()

        class Drought:
            def status(self, *args):
                return None

        service = self.service(Rotation(), Drought())
        service.for_field(self.field(), self.preferences)
        service.for_field(self.field(), self.preferences)
        self.assertEqual(len(calls), 1)


class CalendarEndpointTests(unittest.TestCase):
    def setUp(self):
        directory, self.app = isolated_app()
        self.addCleanup(directory.cleanup)
        self.addCleanup(self.app.state.engine.dispose)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.assertEqual(register(self.client).status_code, 201)
        self.other = TestClient(self.app)
        self.addCleanup(self.other.close)
        self.assertEqual(register(self.other, "other@example.com").status_code, 201)

        class Rotation:
            def advise(self, *args):
                return advice()

        self.app.state.calendar.rotation = Rotation()

    def test_field_and_system_events_follow_the_response_contract(self):
        field = create_field(self.client)
        other = create_field(self.other)
        events = self.client.get(f"/api/v1/fields/{field['id']}/events")
        self.assertEqual(events.status_code, 200, events.text)
        keys = {"id", "fieldId", "fieldName", "date", "category", "title", "description",
                "priority", "duration", "rationale"}  # fmt: skip
        self.assertTrue(events.json())
        for event in events.json():
            self.assertEqual(set(event), keys)
            self.assertEqual(event["fieldId"], field["id"])
        system = self.client.get("/api/v1/planning/events").json()
        self.assertEqual({e["fieldId"] for e in system}, {field["id"]})
        self.assertEqual(len(system), len(events.json()))
        self.assertNotIn(other["id"], {e["fieldId"] for e in system})
        self.assertEqual(self.other.get(f"/api/v1/fields/{field['id']}/events").status_code, 404)


if __name__ == "__main__":
    unittest.main()
