import unittest
from pathlib import Path

from rule_engine.catalog import load_catalog
from rule_engine.facts import (
    HistoryYear,
    candidate_facts,
    county_facts,
    crop_history,
    hazard_result,
    history_facts,
)
from rule_engine.reference import load_reference
from rule_engine.rules import Hazard
from rule_engine.summary import SeasonSummaryStore

FIXTURES = Path(__file__).parent / "fixtures" / "season_summary"


class FactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.reference = load_reference()
        cls.store = SeasonSummaryStore(FIXTURES)

    def test_history_prefers_csb_cdl_properties(self):
        field = {"sourceProperties": {"CDL2022": 1, "CDL2023": 5, "CDL2024": 1, "CSBACRES": 40}}
        history = crop_history(field, [], self.catalog)
        self.assertEqual(
            [(y.year, y.crop, y.source) for y in history],
            [(2022, "corn", "cdl"), (2023, "soybeans", "cdl"), (2024, "corn", "cdl")],
        )

    def test_history_falls_back_to_summary_then_declared(self):
        seasons = self.store.seasons("191825000014246", "19015")  # corn-corn
        history = crop_history({"crop": "Corn"}, seasons, self.catalog)
        self.assertEqual([(y.year, y.crop) for y in history], [(2023, "corn"), (2024, "corn")])
        declared = crop_history({"crop": "Soybeans", "sourceYear": 2025}, [], self.catalog)
        self.assertEqual(
            [(y.year, y.crop, y.source) for y in declared], [(2025, "soybeans", "declared")]
        )
        self.assertEqual(crop_history({"crop": None}, [], self.catalog), [])

    def test_history_facts_for_continuous_corn(self):
        history = [
            HistoryYear(2021, "corn", 1, "cdl"),
            HistoryYear(2022, "corn", 1, "cdl"),
            HistoryYear(2023, "corn", 1, "cdl"),
            HistoryYear(2024, "corn", 1, "cdl"),
        ]
        facts = history_facts(history, self.catalog.crops["corn"], self.catalog)
        self.assertEqual(facts["history.consecutive_same_crop"], 4)
        self.assertEqual(facts["history.distinct_groups_5y"], 1)
        self.assertEqual(facts["history.share_same_crop_5y"], 1.0)
        self.assertEqual(facts["history.years_since_same_family"], 1)
        self.assertEqual(facts["history.corn_soy_alternation_years"], 1)
        soy = history_facts(history, self.catalog.crops["soybeans"], self.catalog)
        self.assertEqual(soy["history.consecutive_same_crop"], 0)
        self.assertIsNone(soy["history.years_since_same_family"])
        self.assertEqual(soy["history.shared_hosts_prev1"], [])
        self.assertFalse(soy["history.candidate_group_in_5y"])

    def test_alternation_and_shared_hosts(self):
        history = [
            HistoryYear(y, c, None, "cdl")
            for y, c in [
                (2020, "soybeans"),
                (2021, "corn"),
                (2022, "soybeans"),
                (2023, "corn"),
                (2024, "soybeans"),
            ]
        ]
        corn = history_facts(history, self.catalog.crops["corn"], self.catalog)
        self.assertEqual(corn["history.corn_soy_alternation_years"], 5)
        self.assertTrue(corn["history.prev1.n_fixer"])
        soy = history_facts(history, self.catalog.crops["soybeans"], self.catalog)
        self.assertIn("soybean_cyst_nematode", soy["history.shared_hosts_prev1"])
        self.assertEqual(soy["history.consecutive_same_crop"], 1)
        self.assertEqual(candidate_facts(self.catalog.crops["corn"])["candidate.n_fixer"], False)

    def test_county_facts_and_hazard_from_fixture(self):
        seasons = self.store.seasons("191825000014220", "19015")
        county = county_facts(seasons)
        self.assertIn("county.rma_drought_share_lag1", county)
        self.assertIn("county.rma_excess_moisture_share_lag1", county)
        calendar = self.reference.calendar(self.catalog.crops["corn"], "IA")
        wet = Hazard("planted", (-7, 14), "pr_ge25_days", 2, "sum", "ge")
        result = hazard_result(wet, calendar, seasons)
        self.assertEqual(
            (result.seasons_total, result.seasons_hit, result.worst_year), (1, 1, 2025)
        )
        self.assertEqual(result.window, (117, 138))
        heat = Hazard("flowering", (-10, 10), "tmax_ge35_days", 1, "sum", "ge")
        self.assertEqual(hazard_result(heat, calendar, seasons).seasons_hit, 0)
        self.assertEqual(hazard_result(heat, calendar, []).seasons_total, 0)
