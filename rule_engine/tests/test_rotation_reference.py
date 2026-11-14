import unittest

from rule_engine.catalog import load_catalog
from rule_engine.reference import load_reference


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.reference = load_reference()

    def test_corn_calendar_comes_from_nass_region_table(self):
        calendar = self.reference.calendar(self.catalog.crops["corn"], "IA")
        self.assertEqual(calendar.kind, "nass_region")
        self.assertEqual(calendar.stages["flowering"], 198)
        self.assertEqual(calendar.stages["harvested"], 292)

    def test_alfalfa_calendar_falls_back_to_group_default(self):
        calendar = self.reference.calendar(self.catalog.crops["alfalfa"], "IA")
        self.assertEqual(calendar.kind, "group_default")
        self.assertIn("flowering", calendar.stages)
        self.assertIn("unverified", calendar.source)

    def test_winter_wheat_uses_fall_sown_crop_calendar(self):
        calendar = self.reference.calendar(self.catalog.crops["winter_wheat"], "IA")
        self.assertEqual(calendar.kind, "crop_default")
        self.assertLess(calendar.stages["flowering"], 160)
        self.assertNotIn("planted", calendar.stages)

    def test_prices_carry_source_and_verification(self):
        corn = self.reference.price("corn")
        self.assertEqual((corn.price_usd, corn.unit, corn.verified), (4.62, "bu", True))
        self.assertIn("RMA", corn.source)
        oats = self.reference.price("oats")
        self.assertTrue(oats.verified)
        self.assertEqual(oats.level, "state")
        self.assertIn("NASS", oats.source)
        self.assertEqual(self.reference.price("rye").level, "national")
        self.assertIsNone(self.reference.price("grass_pasture"))

    def test_reference_yields(self):
        oats = self.reference.yield_reference("oats", "IA")
        self.assertLessEqual(oats.low, oats.mid)
        self.assertLessEqual(oats.mid, oats.high)
        self.assertEqual(oats.unit, "bu/acre")
        self.assertTrue(oats.verified)
        self.assertFalse(self.reference.yield_reference("winter_wheat", "IA").verified)
        corn = self.reference.yield_reference("corn", "IA")  # state table: county fallback
        self.assertEqual((corn.level, corn.unit, corn.verified), ("state", "bu/acre", True))
        self.assertIsNone(self.reference.yield_reference("corn", "ZZ"))
