import unittest
from pathlib import Path

from rule_engine.catalog import load_catalog
from rule_engine.engine import RotationAdvisor
from rule_engine.facts import field_facts
from rule_engine.herbicide import herbicide_facts, load_plantback
from rule_engine.reference import load_reference
from rule_engine.rules import load_rules
from rule_engine.ssurgo import parse_soil
from rule_engine.summary import SeasonSummaryStore
from rule_engine.yield_model import CountyTrendYieldModel

FIXTURES = Path(__file__).parent / "fixtures" / "season_summary"
CORN_SOY = {"CDL2020": 1, "CDL2021": 5, "CDL2022": 1, "CDL2023": 5, "CDL2024": 1}
SOY_LAST = {"CDL2020": 5, "CDL2021": 1, "CDL2022": 5, "CDL2023": 1, "CDL2024": 5}


def field(props=CORN_SOY, soil=None, practices=None):
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "crop": "Corn",
        "area": 40.0,
        "sourceId": "191825000014246",
        "countyFips": "19015",
        "sourceYear": 2025,
        "sourceProperties": props,
        "soil": soil,
        "practices": practices,
    }


class InputRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.reference = load_reference()
        cls.advisor = RotationAdvisor(
            cls.catalog,
            load_rules(),
            cls.reference,
            SeasonSummaryStore(FIXTURES),
            CountyTrendYieldModel(),
        )

    def rules(self, crop, **inputs):
        result = self.advisor.advise(field(**inputs), "corn", [], "imperial")
        item = next(c for c in result["candidates"] if c["crop"] == crop)
        found = {f["ruleId"]: f for k in ("risks", "benefits", "advisories") for f in item[k]}
        return found, item, result

    # -- inputs and gaps ----------------------------------------------------------------

    def test_missing_inputs_are_reported_and_new_rules_stay_silent(self):
        found, _, result = self.rules("corn")
        gaps = {g["code"]: g for g in result["dataGaps"]}
        self.assertIn("field.soil.drainage_class", gaps["soil_not_provided"]["facts"])
        self.assertNotIn("field.soil.wetness", gaps["soil_not_provided"]["facts"])
        self.assertIn("field.practice.herbicides", gaps["practices_not_provided"]["facts"])
        self.assertIn("cover_crop_suggested", found)
        self.assertFalse({"erosion_sloping_row_crop", "no_till_erosion_benefit"} & set(found))

    def test_field_facts_normalise_and_derive(self):
        facts = field_facts(
            field(
                soil={"drainageClass": "Poorly drained", "slopePct": 3},
                practices={"tillage": "No-Till", "tileDrained": True, "coverCrop": "None"},
            ),
            [],
            [],
        )
        self.assertEqual(facts["field.soil.drainage_class"], "poorly_drained")
        self.assertEqual(facts["field.soil.wetness"], "tiled")
        self.assertEqual(facts["field.practice.tillage"], "no_till")
        self.assertFalse(facts["field.practice.cover_planned"])

    # -- soil ---------------------------------------------------------------------------

    def test_slope_scales_erosion_and_rewards_perennial_cover(self):
        found, _, _ = self.rules("corn", soil={"slopePct": 7})
        self.assertEqual(found["erosion_sloping_row_crop"]["level"], "medium")
        found, _, _ = self.rules("corn", soil={"slopePct": 12})
        self.assertEqual(found["erosion_steep_slope_row_crop"]["level"], "high")
        self.assertNotIn("erosion_sloping_row_crop", found)
        found, _, _ = self.rules("alfalfa", soil={"slopePct": 12})
        self.assertIn("perennial_cover_on_slope", found)

    def test_alfalfa_wet_soil_and_ph_and_tile_override(self):
        soil = {"drainageClass": "Poorly drained", "ph": 6.0}
        found, _, _ = self.rules("alfalfa", soil=soil)
        self.assertEqual(found["alfalfa_wet_soil"]["level"], "high")
        self.assertIn("alfalfa_low_ph", found)
        found, _, _ = self.rules("alfalfa", soil=soil, practices={"tileDrained": True})
        self.assertNotIn("alfalfa_wet_soil", found)

    def test_soybean_chlorosis_uses_carbonate_then_ph(self):
        found, _, _ = self.rules("soybeans", soil={"caco3Pct": 4, "ph": 7.8})
        self.assertIn("soybean_iron_chlorosis_calcareous", found)
        self.assertNotIn("soybean_iron_chlorosis_high_ph", found)
        self.assertIn("scn_sampling_high_ph", found)
        found, _, _ = self.rules("soybeans", soil={"ph": 7.8})
        self.assertIn("soybean_iron_chlorosis_high_ph", found)

    def test_droughty_soil_hits_high_water_demand_only(self):
        found, _, _ = self.rules("corn", soil={"aws_100cm_mm": 80})
        self.assertIn("droughty_soil_high_water_demand", found)
        found, _, _ = self.rules("soybeans", soil={"aws_100cm_mm": 80})
        self.assertNotIn("droughty_soil_high_water_demand", found)

    # -- tillage ------------------------------------------------------------------------

    def test_no_till_benefit_and_wet_soil_corn_drag(self):
        found, item, _ = self.rules(
            "corn", soil={"drainageClass": "Very poorly drained"}, practices={"tillage": "no_till"}
        )
        self.assertIn("no_till_erosion_benefit", found)
        self.assertIn("strip_till_on_wet_soil", found)
        self.assertIn(
            "no_till_corn_wet_soil_yield_drag",
            {f["ruleId"] for f in item["yield"]["factorsApplied"]},
        )
        self.assertIn("residue_borne_disease_reduced_tillage", found)  # corn after corn

    def test_tilled_soybean_stubble_is_an_erosion_risk(self):
        found, _, _ = self.rules("corn", props=SOY_LAST, practices={"tillage": "reduced"})
        self.assertIn("low_residue_after_soybeans_tilled", found)
        found, _, _ = self.rules("corn", props=SOY_LAST, practices={"tillage": "no_till"})
        self.assertNotIn("low_residue_after_soybeans_tilled", found)

    # -- cover crops and double cropping --------------------------------------------------

    def test_rye_cover_benefits_and_corn_termination(self):
        found, _, _ = self.rules("corn", practices={"coverCrop": "rye"})
        self.assertIn("winter_cover_nitrate_benefit", found)
        self.assertIn("winter_cover_soil_protection", found)
        self.assertEqual(found["rye_before_corn_termination_unknown"]["level"], "low")
        self.assertNotIn("cover_crop_suggested", found)
        found, _, _ = self.rules("corn", practices={"coverCrop": "rye", "coverTerminationDays": 3})
        self.assertEqual(found["rye_before_corn_planted_green"]["level"], "medium")
        found, _, _ = self.rules("corn", practices={"coverCrop": "rye", "coverTerminationDays": 14})
        self.assertFalse({k for k in found if k.startswith("rye_before_corn")})
        found, _, _ = self.rules("soybeans", practices={"coverCrop": "rye"})
        self.assertFalse({k for k in found if k.startswith("rye_before_corn")})

    def test_oats_after_corn_is_too_late(self):
        found, _, _ = self.rules("soybeans", practices={"coverCrop": "oats"})
        self.assertIn("cover_seeded_too_late", found)
        self.assertNotIn("winter_cover_nitrate_benefit", found)

    def test_double_crop_is_a_ranked_choice_with_high_risk(self):
        found, item, _ = self.rules("double_crop_winter_wheat_soybeans")
        self.assertEqual(found["double_crop_soybean_short_season"]["level"], "high")
        self.assertIn("relay_instead_of_double_crop", found)
        self.assertEqual(item["calendar"]["stages"]["planted"], 191)

    # -- herbicides -----------------------------------------------------------------------

    def herbicide(self, crop_id, entries):
        crop = self.catalog.crops[crop_id]
        calendar = self.reference.calendar(crop, "IA")
        return herbicide_facts(
            {"practices": {"herbicides": entries}}, crop, calendar, load_plantback()
        )

    def test_plantback_shortfall_arithmetic(self):
        # fomesafen in July, corn planted in May: 10 months elapsed against an 18-month alfalfa
        # interval (planted in April: 9 months elapsed) and a 10-month corn interval
        facts, unknown = self.herbicide("corn", [{"active": "Fomesafen", "month": 7}])
        self.assertEqual((facts["herbicide.shortfall_months"], unknown), (0.0, []))
        self.assertEqual(facts["herbicide.late_restricted_count"], 1)
        facts, _ = self.herbicide("alfalfa", [{"active": "fomesafen", "month": 7}])
        self.assertEqual(facts["herbicide.shortfall_months"], 9.0)
        self.assertEqual(facts["herbicide.limiting_active"], "fomesafen")
        facts, _ = self.herbicide("soybeans", [{"active": "atrazine", "month": 6, "season": 2}])
        self.assertEqual(facts["herbicide.shortfall_months"], 0.0)
        facts, unknown = self.herbicide("sorghum", ["atrazine", "mystery"])
        self.assertEqual(unknown, ["atrazine", "mystery"])
        self.assertNotIn("herbicide.shortfall_months", facts)

    def test_herbicide_rules_rank_and_report(self):
        practices = {
            "herbicides": [
                {"active": "fomesafen", "month": 7},
                {"active": "sulfentrazone", "month": 5, "season": 2},
            ],
            "weedEscapes": True,
        }
        found, _, _ = self.rules("alfalfa", practices=practices)
        self.assertEqual(found["herbicide_plantback_violated_major"]["level"], "high")
        self.assertIn("weed_escapes_cool_season_break", found)
        found, _, _ = self.rules("corn", practices=practices)
        self.assertIn("herbicide_late_application_carryover", found)
        self.assertIn("same_site_of_action_repeat", found)  # group 14 two seasons running
        self.assertIn("weed_escapes_row_crop", found)
        found, item, _ = self.rules("sorghum", practices=practices)
        gap = next(g for g in item["dataGaps"] if g["code"] == "herbicide_plantback_unknown")
        self.assertEqual(gap["actives"], ["fomesafen", "sulfentrazone"])

    def test_high_ph_extends_chlorimuron_carryover(self):
        practices = {"herbicides": [{"active": "chlorimuron", "month": 6}]}
        found, _, _ = self.rules("corn", practices=practices, soil={"ph": 7.4})
        self.assertIn("herbicide_carryover_high_ph_chlorimuron", found)
        found, _, _ = self.rules("corn", practices=practices, soil={"ph": 6.2})
        self.assertNotIn("herbicide_carryover_high_ph_chlorimuron", found)

    # -- SSURGO -------------------------------------------------------------------------

    def test_parse_soil_converts_units(self):
        payload = {
            "Table": [
                ["mukey", "muname", "aws0100wta", "slope_r", "drainagecl", "nirrcapcl", "caco3_r"],
                [
                    "411278",
                    "Hanlon-Spillville complex",
                    "18.21",
                    "1",
                    "Moderately well drained",
                    "5",
                    None,
                ],
            ]
        }
        soil = parse_soil(payload)
        self.assertEqual(soil["aws_100cm_mm"], 182.1)
        self.assertEqual((soil["slope_pct"], soil["nirr_class"]), (1.0, 5))
        self.assertNotIn("caco3_pct", soil)
        self.assertIsNone(parse_soil({}))


if __name__ == "__main__":
    unittest.main()
