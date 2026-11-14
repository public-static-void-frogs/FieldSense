import unittest
from pathlib import Path

from rule_engine.summary import WEEKS, SeasonSummary, SeasonSummaryStore

FIXTURES = Path(__file__).parent / "fixtures" / "season_summary"


class SummaryStoreTests(unittest.TestCase):
    def test_missing_root_yields_no_seasons(self):
        self.assertEqual(SeasonSummaryStore(None).seasons("x", "19015"), [])
        self.assertEqual(SeasonSummaryStore("/nonexistent/path").seasons("x", "19015"), [])

    def test_fixture_field_loads_with_weekly_series(self):
        seasons = SeasonSummaryStore(FIXTURES).seasons("191825000014220", "19015")
        self.assertEqual(len(seasons), 1)
        season = seasons[0]
        self.assertEqual((season.year, season.cdl_prev1, season.cdl_prev2), (2025, 1, 5))
        self.assertEqual(len(season.weekly["tmax_ge35_days"]), WEEKS)
        self.assertGreater(season.scalars["yield_corn_bu_ac"], 100)
        self.assertEqual(SeasonSummaryStore(FIXTURES).seasons("nope", "19015"), [])

    def test_window_aggregates_overlapping_weeks(self):
        season = SeasonSummary(
            csbid="a",
            county_fips="19015",
            year=2025,
            cdl_prev1=1,
            cdl_prev2=5,
            scalars={},
            weekly={
                "hot": [0, 2, 1] + [0] * (WEEKS - 3),
                "tmin": [None, -3.0, 1.0] + [None] * (WEEKS - 3),
            },
        )
        # doy 98..111 covers weeks 1 and 2 (bins (98-91)//7=1, (111-91)//7=2)
        self.assertEqual(season.window("hot", 98, 111, "sum"), 3)
        self.assertEqual(season.window("tmin", 91, 111, "min"), -3.0)
        self.assertIsNone(season.window("tmin", 200, 210, "min"))
        self.assertIsNone(season.window("unknown", 91, 100, "sum"))
