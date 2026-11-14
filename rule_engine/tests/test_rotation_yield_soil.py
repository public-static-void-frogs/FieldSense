import unittest
from pathlib import Path

from rule_engine.catalog import load_catalog
from rule_engine.facts import HistoryYear
from rule_engine.reference import load_reference
from rule_engine.soil import DerivedSoilIndicators
from rule_engine.summary import SeasonSummaryStore
from rule_engine.yield_model import (
    CountyTrendYieldModel,
    apply_yield_factors,
    display_yield,
    gross_revenue,
)

FIXTURES = Path(__file__).parent / "fixtures" / "season_summary"


class YieldModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.reference = load_reference()
        cls.seasons = SeasonSummaryStore(FIXTURES).seasons("191825000014220", "19015")
        cls.model = CountyTrendYieldModel()

    def test_corn_from_county_yields(self):
        corn = self.catalog.crops["corn"]
        est = self.model.predict(corn, self.seasons, self.reference, "IA")
        self.assertEqual((est.level, est.method), ("county", "county_trend"))
        self.assertEqual(est.inputs["unit"], "bu/acre")
        self.assertTrue(est.verified)
        self.assertLessEqual(est.low_t_ha, est.mid_t_ha)
        self.assertLessEqual(est.mid_t_ha, est.high_t_ha)
        self.assertAlmostEqual(est.mid_t_ha / corn.bu_to_t_ha, 212.7, delta=5)
        bu, unit = display_yield(corn, est.mid_t_ha, "imperial")
        self.assertEqual(unit, "bu/acre")
        self.assertAlmostEqual(bu, est.mid_t_ha / corn.bu_to_t_ha, places=0)
        self.assertEqual(display_yield(corn, 10.0, "metric"), (10.0, "t/ha"))

    def test_oats_from_reference_and_sorghum_missing(self):
        oats = self.catalog.crops["oats"]
        est = self.model.predict(oats, self.seasons, self.reference, "IA")
        self.assertEqual(est.level, "state")
        self.assertTrue(est.verified)
        ref = self.reference.yield_reference("oats", "IA")
        self.assertAlmostEqual(est.mid_t_ha, ref.mid * oats.bu_to_t_ha)
        self.assertIsNone(
            self.model.predict(self.catalog.crops["sorghum"], [], self.reference, "IA")
        )
        fallback = self.model.predict(self.catalog.crops["corn"], [], self.reference, "IA")
        self.assertEqual((fallback.method, fallback.level), ("reference_range", "state"))
        self.assertIsNone(self.model.predict(self.catalog.crops["corn"], [], self.reference, "ZZ"))

    def test_factors_and_revenue(self):
        corn = self.catalog.crops["corn"]
        est = self.model.predict(corn, self.seasons, self.reference, "IA")
        adjusted = apply_yield_factors(est, [("continuous_corn_yield_penalty", (0.85, 0.96))])
        self.assertAlmostEqual(adjusted.low_t_ha, est.low_t_ha * 0.85)
        self.assertAlmostEqual(adjusted.high_t_ha, est.high_t_ha * 0.96)
        self.assertEqual(adjusted.factors, ("continuous_corn_yield_penalty",))
        revenue = gross_revenue(est, self.reference.price("corn"), corn, 40.0)
        acres = 40.0 / 0.404686
        self.assertAlmostEqual(
            revenue.mid_usd, est.mid_t_ha / corn.bu_to_t_ha * acres * 4.62, delta=1
        )
        self.assertTrue(revenue.price_verified)
        self.assertIsNone(gross_revenue(est, None, corn, 40.0))


class SoilIndicatorTests(unittest.TestCase):
    def test_alfalfa_versus_corn_directions(self):
        catalog = load_catalog()
        provider = DerivedSoilIndicators()
        history = [HistoryYear(2024, "corn", 1, "cdl")]
        alfalfa = {i.id: i for i in provider.indicators({}, catalog.crops["alfalfa"], history, [])}
        corn = {i.id: i for i in provider.indicators({}, catalog.crops["corn"], history, [])}
        self.assertEqual(alfalfa["erosion_exposure"].direction, "better")
        self.assertEqual(corn["erosion_exposure"].direction, "worse")
        self.assertEqual(alfalfa["n_balance"].direction, "better")
        self.assertEqual(corn["n_balance"].direction, "worse")
        self.assertEqual(corn["rootzone_dry_weeks"].direction, "unknown")
        self.assertTrue(all(i.kind == "derived_indicator" for i in corn.values()))
        self.assertEqual(corn["rootzone_dry_weeks"].basis, "smap_rootzone")
        self.assertEqual(corn["rotation_diversity"].basis, "cdl_history")
        self.assertEqual(corn["erosion_exposure"].basis, "crop_trait")
