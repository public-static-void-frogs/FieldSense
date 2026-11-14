import unittest
from pathlib import Path
from unittest import mock

from rule_engine.catalog import load_catalog
from rule_engine.engine import RotationAdvisor
from rule_engine.reference import load_reference
from rule_engine.regions import field_region
from rule_engine.rules import load_rules
from rule_engine.summary import SeasonSummaryStore
from rule_engine.yield_model import CountyTrendYieldModel

FIXTURES = Path(__file__).parent / "fixtures" / "season_summary"


def kansas_field():
    return {
        "id": "ks-1",
        "sourceId": "201825000000001",
        "stateFips": "20",
        "countyFips": "20173",
        "area": 60.0,
        "sourceYear": 2025,
        "sourceProperties": {"CDL2023": 24, "CDL2024": 5, "CDL2025": 24},
    }


class RegionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = load_reference()
        cls.advisor = RotationAdvisor(
            load_catalog(),
            load_rules(),
            cls.reference,
            SeasonSummaryStore(FIXTURES),
            CountyTrendYieldModel(),
        )

    def test_field_region_from_state_or_county_fips(self):
        self.assertEqual(field_region({"stateFips": "20"}), "KS")
        self.assertEqual(field_region({"stateFips": 6}), "CA")
        self.assertEqual(field_region({"countyFips": "19015"}), "IA")
        self.assertIsNone(field_region({"countyFips": "015"}))
        self.assertIsNone(field_region({"stateFips": "99"}))
        self.assertIsNone(field_region({}))

    def test_candidates_differ_by_state(self):
        kansas = self.advisor.candidate_ids("KS")
        iowa = self.advisor.candidate_ids("IA")
        self.assertIn("winter_wheat", kansas)
        self.assertIn("sorghum", kansas)
        self.assertIn("corn", iowa)
        self.assertNotEqual(set(kansas), set(iowa))

    def test_field_is_ranked_in_its_own_state(self):
        result = self.advisor.advise(kansas_field(), "winter_wheat", [], "metric")
        self.assertEqual(result["region"], "KS")
        self.assertNotIn("region_not_supported", {g["code"] for g in result["dataGaps"]})
        crops = {c["crop"] for c in result["candidates"]}
        self.assertEqual(crops, set(self.advisor.candidate_ids("KS")))

    def test_unrecognised_fips_uses_the_default_region(self):
        record = kansas_field() | {"stateFips": "99", "countyFips": "99001"}
        self.assertEqual(self.advisor.region_for(record), ("IA", []))

    def test_state_without_candidates_falls_back_with_gap(self):
        candidates = self.advisor.catalog.candidates
        with mock.patch.object(
            type(self.advisor.catalog),
            "candidates",
            lambda _, region=None: [] if region == "KS" else candidates(region),
        ):
            region, gaps = self.advisor.region_for(kansas_field())
            self.assertEqual(region, "IA")
            self.assertEqual([g["code"] for g in gaps], ["region_not_supported"])
            result = self.advisor.advise(kansas_field(), "corn", [], "metric")
        self.assertEqual(result["dataGaps"][0]["code"], "region_not_supported")

    def test_state_calendar_and_price_are_used(self):
        wheat = self.advisor.catalog.crops["winter_wheat"]
        kansas = self.reference.calendar(wheat, "KS")
        self.assertEqual(kansas.region, "KS")
        self.assertNotIn("default", kansas.kind)
        self.assertNotEqual(kansas.stages, self.reference.calendar(wheat, "IA").stages)
        # the curated oats quote was observed in Iowa, so Kansas uses its own
        self.assertEqual(self.reference.price("oats", "KS").region, "KS")
        self.assertEqual(self.reference.price("oats", "IA").region, "IA")
        # a national quote is kept everywhere
        self.assertIsNone(self.reference.price("winter_wheat", "KS").region)


if __name__ == "__main__":
    unittest.main()
