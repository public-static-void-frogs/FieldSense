import unittest

from rule_engine.catalog import load_catalog


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()

    def test_corn_maps_from_cdl_1_and_inherits_group_traits(self):
        corn = self.catalog.by_cdl(1)
        self.assertEqual(corn.id, "corn")
        self.assertEqual(corn.group.id, "warm_season_grain")
        self.assertEqual(corn.value("family"), "Poaceae")
        self.assertEqual(corn.trait("rusle_c").value, 0.40)
        self.assertIn("corn_rootworm", corn.value("hosts"))
        self.assertIsNone(self.catalog.by_cdl(None))
        self.assertIsNone(self.catalog.by_cdl(9999))

    def test_crop_trait_overrides_group(self):
        canola = self.catalog.crops["canola"]
        self.assertEqual(canola.value("family"), "Brassicaceae")
        self.assertEqual(canola.group.traits["family"].value, "Poaceae")

    def test_candidates_for_iowa_exclude_non_crop_and_fallow(self):
        ids = {crop.id for crop in self.catalog.candidates("IA")}
        self.assertTrue({"corn", "soybeans", "oats", "alfalfa", "winter_wheat"} <= ids)
        self.assertFalse({"fallow", "non_crop", "barley"} & ids)
        self.assertGreaterEqual(len(ids), 3)

    def test_unverified_trait_keeps_flag_and_source(self):
        soybeans = self.catalog.crops["soybeans"]
        rusle = soybeans.trait("rusle_c")
        self.assertFalse(rusle.verified)
        self.assertIn("proxy", rusle.source)
        self.assertTrue(soybeans.trait("humus_balance").verified)

    def test_non_crop_codes_map_to_non_crop_group(self):
        self.assertEqual(self.catalog.by_cdl(176).group.id, "grass_hay_pasture")
        self.assertEqual(self.catalog.by_cdl(121).group.id, "non_crop")
