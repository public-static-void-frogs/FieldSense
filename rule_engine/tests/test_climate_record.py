import json
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from rule_engine.catalog import load_catalog
from rule_engine.engine import RotationAdvisor
from rule_engine.offseason import killing_frost_doy, off_season
from rule_engine.reference import load_reference, localize
from rule_engine.rules import load_rules
from rule_engine.summary import ClimateRecordStore, SeasonSummaryStore
from rule_engine.yield_model import CountyTrendYieldModel

WEEKS = 53
NODE = (42.15, -93.5)  # grid row 29, column 125
FLOWERING_WEEK = 28  # days 196-202; Iowa corn flowers on day 198
FIRST_YEAR = 2014


def weeks(value, **overrides):
    series = [value] * WEEKS
    for week, replacement in overrides.items():
        series[int(week[1:])] = replacement
    return series


def season(year, hot=False, last_warm_week=42):
    """One node-year: warm from week 15 to `last_warm_week`, hard freeze outside it."""
    warm = range(15, last_warm_week + 1)
    return {
        "ix": 125,
        "lat": NODE[0],
        "lon": NODE[1],
        "year": year,
        "tmax_max": weeks(28.0),
        "tmin_min": [10.0 if w in warm else -5.0 for w in range(WEEKS)],
        "pr_mm": weeks(20.0),
        "gdd0": [105.0 if w in warm else 0.0 for w in range(WEEKS)],
        "tmax_ge35_days": weeks(0, **{f"w{FLOWERING_WEEK}": 2 if hot else 0}),
        "tmax_ge30_days": weeks(0),
        "pr_ge25_days": weeks(0),
    }


def write_record(root: Path, seasons: list[dict]) -> ClimateRecordStore:
    (root / "iy=29").mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(seasons), root / "iy=29" / "data_0.parquet")
    grid = {
        "lat0": 49.4,
        "lon0": -124.75,
        "lat_step": -0.25,
        "lon_step": 0.25,
        "week0_doy": 0,
        "weeks": WEEKS,
        "source": "test grid",
    }
    (root / "grid.json").write_text(json.dumps(grid))
    return ClimateRecordStore(root)


def field(props=None, **extra):
    return {
        "id": "f1",
        "area": 40.0,
        "stateFips": "19",
        "countyFips": "19015",
        "latitude": 42.1,
        "longitude": -93.45,
        "sourceProperties": props or {f"CDL{y}": 1 for y in range(2021, 2026)},
        **extra,
    }


class ClimateRecordTests(unittest.TestCase):
    def advisor(self, seasons):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        store = write_record(Path(folder.name), seasons)
        advisor = RotationAdvisor(
            load_catalog(),
            load_rules(),
            load_reference(),
            SeasonSummaryStore(None),
            CountyTrendYieldModel(),
            climate=store,
        )
        return advisor, store

    def twelve(self, hot_years=0, late_autumns=0):
        return [
            season(FIRST_YEAR + i, hot=i < hot_years, last_warm_week=46 if i < late_autumns else 42)
            for i in range(12)
        ]

    def test_nearest_node_and_whole_year_windows(self):
        _, store = self.advisor(self.twelve())
        record = store.record(42.1, -93.45)
        self.assertEqual((record.latitude, record.longitude, len(record.seasons)), (*NODE, 12))
        self.assertLess(record.distance_km, 10)
        first = record.seasons[0]
        self.assertEqual(first.window("tmin_min", 1, 60, "min"), -5.0)  # winter weeks exist
        self.assertEqual(first.window("gdd0", 105, 111, "sum"), 105.0)  # week 15 alone
        self.assertEqual(killing_frost_doy(first), 304)  # middle of week 43
        self.assertIsNone(store.record(30.0, -93.45))  # no node nearby
        self.assertIsNone(store.record(None, None))

    def test_weather_hazard_counts_the_long_record_without_field_summaries(self):
        advisor, _ = self.advisor(self.twelve(hot_years=3))
        result = advisor.advise(field(), "corn", [], "metric")
        self.assertEqual(result["seasonsAvailable"], [])
        self.assertEqual(result["weatherRecord"]["seasons"], 12)
        self.assertEqual(result["weatherRecord"]["firstYear"], FIRST_YEAR)
        corn = next(c for c in result["candidates"] if c["crop"] == "corn")
        heat = next(r for r in corn["risks"] if r["ruleId"] == "heat_at_flowering")
        trigger = heat["trigger"]
        self.assertEqual((trigger["seasonsHit"], trigger["seasonsTotal"]), (3, 12))
        self.assertEqual((trigger["record"], heat["level"]), ("weather_record", "medium"))
        gap = next(g for g in result["dataGaps"] if g["code"] == "no_csb_id")
        self.assertNotIn("weather", gap["affects"])

    def test_rare_hazard_is_not_reported(self):
        advisor, _ = self.advisor(self.twelve(hot_years=1))  # 1 season in 12
        result = advisor.advise(field(), "corn", [], "metric")
        corn = next(c for c in result["candidates"] if c["crop"] == "corn")
        self.assertNotIn("heat_at_flowering", {r["ruleId"] for r in corn["risks"]})

    def test_field_outside_the_grid_reports_the_gap(self):
        advisor, _ = self.advisor(self.twelve())
        result = advisor.advise(field(latitude=30.0), "corn", [], "metric")
        self.assertIsNone(result["weatherRecord"])
        self.assertIn("no_weather_record", {g["code"] for g in result["dataGaps"]})
        self.assertEqual(result["offSeason"]["status"], "no_weather_record")

    def test_local_sowing_date_moves_the_window_and_keeps_the_calendar_kind(self):
        advisor, _ = self.advisor(self.twelve())
        local = {"corn": {"stages": {"planted": 131, "mature": None}, "source": "local model"}}
        result = advisor.advise(field(stageCalendar=local), "corn", [], "metric")
        calendar = next(c for c in result["candidates"] if c["crop"] == "corn")["calendar"]
        self.assertEqual((calendar["stages"]["planted"], calendar["stages"]["emerged"]), (131, 143))
        self.assertEqual(calendar["stages"]["flowering"], 198)
        self.assertEqual(calendar["localShiftDays"], {"planted": 7, "emerged": 7})
        self.assertEqual(
            (calendar["kind"], calendar["localSource"]), ("nass_region", "local model")
        )
        soy = next(c for c in result["candidates"] if c["crop"] == "soybeans")["calendar"]
        self.assertEqual(soy["localShiftDays"], {})

    def test_localize_ignores_stages_the_calendar_lacks(self):
        wheat = load_reference().calendar(load_catalog().crops["winter_wheat"], "IA")
        self.assertIs(localize(wheat, {"planted": 270}, "x"), wheat)

    def test_off_season_after_corn_depends_on_the_autumn(self):
        advisor, _ = self.advisor(self.twelve(late_autumns=9))
        slot = advisor.advise(field(), "corn", [], "metric")["offSeason"]
        self.assertEqual((slot["status"], slot["afterCrop"]), ("ok", "corn"))
        self.assertEqual((slot["harvestDoy"], slot["seedingDoy"]), (292, 299))
        options = {o["id"]: o for o in slot["options"]}
        # seeded on day 299: 450 degree days in a late autumn, 30 otherwise
        self.assertEqual(
            (options["cereal_rye"]["seasonsMet"], options["cereal_rye"]["level"]), (9, "marginal")
        )
        self.assertEqual(options["winter_wheat"]["seasonsMet"], 9)
        self.assertEqual(options["winter_wheat"]["cropId"], "winter_wheat")
        # the killing frost comes 5 or 33 days after seeding: never the 40 days oats need
        self.assertEqual((options["oats"]["seasonsMet"], options["oats"]["level"]), (0, "unlikely"))
        self.assertEqual(slot["firstKillingFrostDoy"], 332)

    def test_off_season_after_a_small_grain_is_wide_open(self):
        advisor, _ = self.advisor(self.twelve())
        props = {f"CDL{y}": 1 for y in range(2021, 2025)} | {"CDL2025": 28}  # oats last
        slot = advisor.advise(field(props), "corn", [], "metric")["offSeason"]
        self.assertEqual((slot["afterCrop"], slot["seedingDoy"]), ("oats", 215))
        self.assertEqual({o["level"] for o in slot["options"]}, {"reliable"})

    def test_off_season_states_why_it_has_no_options(self):
        advisor, _ = self.advisor(self.twelve()[:5])
        slot = advisor.advise(field(), "corn", [], "metric")["offSeason"]
        self.assertEqual((slot["status"], slot["options"]), ("weather_record_too_short", []))
        self.assertEqual(off_season(None, None, None, (), [])["status"], "previous_crop_unknown")
        self.assertEqual(
            off_season("alfalfa", None, "crop_default", (), [])["status"], "no_harvest_in_calendar"
        )


if __name__ == "__main__":
    unittest.main()
