import unittest

from rule_engine.catalog import load_catalog, unit_kind


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


class AddedCropTests(unittest.TestCase):
    """Crops added from the national CSB gap: each maps from CDL and the planned ones carry a
    state price, yield and cost wherever NASS reports them."""

    PLANNED = {
        "cotton": ("TX", "lb"),
        "rice": ("AR", "cwt"),
        "peanuts": ("GA", "lb"),
        "durum_wheat": ("ND", "bu"),
        "sugarbeets": ("MN", "ton"),
        "potatoes": ("ID", "cwt"),
        "sugarcane": ("LA", "ton"),
        "dry_peas": ("ND", "cwt"),
        "lentils": ("MT", "cwt"),
        "chickpeas": ("WA", "cwt"),
        "millet": ("CO", "bu"),
        "flax": ("MT", "bu"),
    }

    @classmethod
    def setUpClass(cls):
        from rule_engine.reference import load_reference

        cls.catalog = load_catalog()
        cls.reference = load_reference()

    def test_cdl_codes_map_to_the_new_crops(self):
        expected = {2: "cotton", 3: "rice", 10: "peanuts", 22: "durum_wheat", 41: "sugarbeets",
                    43: "potatoes", 45: "sugarcane", 53: "dry_peas", 52: "lentils",
                    51: "chickpeas", 29: "millet", 205: "triticale", 32: "flax",
                    225: "double_crop_winter_wheat_corn", 238: "double_crop_winter_wheat_cotton",
                    75: "orchard_vineyard", 54: "vegetables"}  # fmt: skip
        for code, crop in expected.items():
            self.assertEqual(self.catalog.by_cdl(code).id, crop, code)

    def test_permanent_and_vegetable_crops_are_history_only(self):
        for state in ("CA", "FL", "WA"):
            ids = {c.id for c in self.catalog.candidates(state)}
            self.assertFalse({"orchard_vineyard", "vegetables"} & ids, state)

    def test_planned_crops_are_candidates_with_price_and_yield(self):
        for crop_id, (state, unit) in self.PLANNED.items():
            crop = self.catalog.crops[crop_id]
            self.assertIn(crop, self.catalog.candidates(state), crop_id)
            price = self.reference.price(crop_id, state)
            self.assertIsNotNone(price, crop_id)
            self.assertEqual(unit_kind(price.unit), unit, crop_id)
            ref = self.reference.yield_reference(crop_id, state)
            self.assertIsNotNone(ref, crop_id)
            self.assertEqual(unit_kind(ref.unit), unit, crop_id)
            self.assertIsNotNone(crop.t_ha_per(unit), crop_id)

    def test_unit_conversion(self):
        self.assertEqual(unit_kind("$ / CWT"), "cwt")
        self.assertEqual(unit_kind("tons/acre"), "ton")
        self.assertEqual(unit_kind("bu"), "bu")
        rice, durum = self.catalog.crops["rice"], self.catalog.crops["durum_wheat"]
        self.assertAlmostEqual(rice.t_ha_per("cwt/acre"), 0.112085)
        self.assertAlmostEqual(rice.t_ha_per("lb"), 0.00112085)
        self.assertAlmostEqual(durum.t_ha_per("bu/acre"), 0.06725)
        self.assertIsNone(rice.t_ha_per("bu"))

    def test_planned_crops_have_a_cost(self):
        from rule_engine.planner.tables import TILLAGE, CostTable

        table = CostTable(region="Mississippi Portal", state="05")
        self.assertIn("rice", table.crops)
        rice = table.crop_cost("rice", None, TILLAGE[0])
        self.assertFalse(rice.verified)  # matched to an ERS rice region by state
        self.assertIn("Arkansas Non-Delta", rice.sources[0])
        for crop_id in self.PLANNED:
            self.assertIsNotNone(table.crop_cost(crop_id, None, TILLAGE[0]), crop_id)


class ShortReturnTests(unittest.TestCase):
    """Yield rules for the crops whose return interval matters, and the planner's limits on the
    crops that need a processor or a fallow year."""

    @classmethod
    def setUpClass(cls):
        from rule_engine import build_advisor

        cls.advisor = build_advisor()
        cls.catalog = cls.advisor.catalog

    def fired(self, crop_id: str, history: list[str]) -> set[str]:
        from rule_engine.facts import HistoryYear, candidate_facts, history_facts
        from rule_engine.rules import applies, check

        crop = self.catalog.crops[crop_id]
        years = [HistoryYear(2020 + i, c, None, "cdl") for i, c in enumerate(history)]
        facts = {**candidate_facts(crop), **history_facts(years, crop, self.catalog)}
        return {
            rule.id
            for rule in self.advisor.rules.rules
            if rule.effect.yield_factor
            and rule.hazard is None
            and applies(rule, crop, self.catalog)
            and all(check(c, facts)[0] for c in rule.when)
        }

    def test_calibrated_repeat_and_rotation_rules(self):
        self.assertIn("soy_after_soy_yield_penalty", self.fired("soybeans", ["corn", "soybeans"]))
        self.assertNotIn(
            "soy_after_soy_yield_penalty", self.fired("soybeans", ["soybeans", "corn"])
        )
        self.assertIn("continuous_corn_yield_penalty", self.fired("corn", ["soybeans", "corn"]))
        self.assertIn("rotation_yield_benefit", self.fired("corn", ["corn", "oats", "soybeans"]))
        self.assertNotIn("rotation_yield_benefit", self.fired("corn", ["corn", "soybeans"]))

    def test_years_since_same_crop(self):
        from rule_engine.facts import HistoryYear, history_facts

        peanuts = self.catalog.crops["peanuts"]
        years = [
            HistoryYear(2021, "peanuts", None, "cdl"),
            HistoryYear(2022, "cotton", None, "cdl"),
        ]
        self.assertEqual(
            history_facts(years, peanuts, self.catalog)["history.years_since_same_crop"], 2
        )
        self.assertIsNone(
            history_facts(years[1:], peanuts, self.catalog)["history.years_since_same_crop"]
        )

    def test_short_return_yield_rules(self):
        cases = [
            ("peanuts", ["cotton", "peanuts"], "peanut_after_peanut_yield_penalty"),
            ("peanuts", ["peanuts", "cotton"], "peanut_one_year_break_yield_penalty"),
            ("potatoes", ["potatoes", "winter_wheat"], "potato_short_rotation_yield_penalty"),
            ("sugarbeets", ["corn", "sugarbeets"], "sugarbeet_after_sugarbeet_yield_penalty"),
            ("chickpeas", ["barley", "lentils"], "chickpea_after_other_pulse_yield_penalty"),
            ("chickpeas", ["barley", "chickpeas"], "chickpea_after_chickpea_yield_penalty"),
            ("dry_peas", ["barley", "lentils"], "pulse_after_pulse_yield_penalty"),
            ("dry_peas", ["dry_peas", "barley"], "pea_lentil_one_year_break_yield_penalty"),
            ("sugarbeets", ["sugarbeets", "corn"], "sugarbeet_one_year_break_yield_penalty"),
            ("flax", ["spring_wheat", "flax"], "flax_after_flax_yield_penalty"),
        ]
        for crop, history, rule in cases:
            self.assertIn(rule, self.fired(crop, history), (crop, history))
        # a long enough break is free
        self.assertFalse(
            self.fired("peanuts", ["peanuts", "cotton", "corn"])
            & {"peanut_after_peanut_yield_penalty", "peanut_one_year_break_yield_penalty"}
        )
        self.assertNotIn(
            "sugarbeet_after_sugarbeet_yield_penalty",
            self.fired("sugarbeets", ["sugarbeets", "corn"]),
        )
        self.assertFalse(
            self.fired("sugarbeets", ["sugarbeets", "corn", "spring_wheat"])
            & {"sugarbeet_after_sugarbeet_yield_penalty", "sugarbeet_one_year_break_yield_penalty"}
        )
        # one charge per sequence: a pea after a lentil is not also a one-year break
        self.assertNotIn(
            "pea_lentil_one_year_break_yield_penalty",
            self.fired("dry_peas", ["dry_peas", "lentils"]),
        )
        self.assertNotIn(
            "chickpea_after_other_pulse_yield_penalty",
            self.fired("chickpeas", ["barley", "chickpeas"]),
        )
        self.assertNotIn(
            "pulse_after_pulse_yield_penalty", self.fired("dry_peas", ["lentils", "barley"])
        )

    def test_processor_counties(self):
        from rule_engine.planner.tables import processor_counties

        counties = processor_counties()
        self.assertEqual(set(counties), {"sugarbeets", "sugarcane", "potatoes"})
        self.assertIn("16011", counties["potatoes"])  # Bingham, ID
        self.assertNotIn("19153", counties["sugarbeets"])  # Polk, IA

    def test_minimum_return_interval(self):
        from types import SimpleNamespace

        from rule_engine.planner.model import RotationModel
        from rule_engine.planner.tables import load_adjustments

        model = SimpleNamespace(adjustments=load_adjustments())

        def too_soon(history, crop):
            return RotationModel._returns_too_soon(model, tuple(history), crop)

        self.assertTrue(too_soon(["sugarbeets", "spring_wheat"], "sugarbeets"))
        self.assertTrue(too_soon(["corn", "sugarbeets"], "sugarbeets"))
        self.assertFalse(too_soon(["sugarbeets", "corn", "spring_wheat"], "sugarbeets"))
        self.assertTrue(too_soon(["flax", "barley"], "flax"))
        self.assertFalse(too_soon(["corn", "corn"], "corn"))  # no limit: penalties only

    def test_state_cost_budgets(self):
        from rule_engine.planner.tables import TILLAGE, CostTable

        red_river = CostTable(region="Northern Great Plains", state="38")
        beets = red_river.crop_cost("sugarbeets", None, TILLAGE[0])
        self.assertAlmostEqual(beets.usd_per_acre, 1673.36)
        self.assertTrue(beets.verified)
        panhandle = CostTable(region="Northern Great Plains", state="31")
        self.assertAlmostEqual(
            panhandle.crop_cost("sugarbeets", None, TILLAGE[0]).usd_per_acre, 1461.25
        )
        washington = CostTable(region="Fruitful Rim", state="53")
        self.assertIn("WSU", washington.crop_cost("potatoes", None, TILLAGE[0]).sources[0])

    def test_sugarcane_stand_has_a_maximum(self):
        from rule_engine.planner.tables import load_adjustments

        adjustments = load_adjustments()
        self.assertLessEqual(
            adjustments["sugarcane_min_stand_years"]["value"],
            adjustments["sugarcane_max_stand_years"]["value"],
        )
