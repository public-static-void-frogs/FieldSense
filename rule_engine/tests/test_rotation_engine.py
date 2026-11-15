import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rule_engine.catalog import load_catalog
from rule_engine.engine import RotationAdvisor
from rule_engine.reference import load_reference
from rule_engine.rules import load_rules
from rule_engine.summary import SeasonSummaryStore
from rule_engine.yield_model import CountyTrendYieldModel

FIXTURES = Path(__file__).parent / "fixtures" / "season_summary"


def field(csbid, crop="Corn", props=None):
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "crop": crop,
        "area": 40.0,
        "sourceId": csbid,
        "countyFips": "19015",
        "sourceYear": 2025,
        "sourceProperties": props,
    }


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.advisor = RotationAdvisor(
            load_catalog(),
            load_rules(),
            load_reference(),
            SeasonSummaryStore(FIXTURES),
            CountyTrendYieldModel(),
        )

    def test_continuous_corn_flags_rootworm_and_penalises_yield(self):
        props = {f"CDL{y}": 1 for y in range(2020, 2025)}
        result = self.advisor.advise(field("191825000014246", props=props), "corn", [], "imperial")
        corn = next(c for c in result["candidates"] if c["crop"] == "corn")
        self.assertTrue(corn["isIntended"])
        ids = {r["ruleId"] for r in corn["risks"]}
        self.assertIn("corn_rootworm_continuous", ids)
        self.assertIn("continuous_corn_yield_penalty", ids)
        self.assertIn("wet_planting_window", ids)
        self.assertIn(
            "continuous_corn_yield_penalty", {f["ruleId"] for f in corn["yield"]["factorsApplied"]}
        )
        self.assertEqual(corn["yield"]["unit"], "bu/acre")
        self.assertGreater(corn["revenue"]["midUsd"], 0)
        self.assertGreaterEqual(len(result["candidates"]), 3)
        soy = next(c for c in result["candidates"] if c["crop"] == "soybeans")
        self.assertLess(soy["rank"], corn["rank"])
        self.assertIn("pest_break_benefit", {b["ruleId"] for b in soy["benefits"]})
        wet = next(r for r in corn["risks"] if r["ruleId"] == "wet_planting_window")
        t = wet["trigger"]
        self.assertEqual((t["seasonsHit"], t["seasonsTotal"], t["stage"]), (1, 1, "planted"))
        # hit in the one season on record, but no yield loss is found for corn: low
        self.assertEqual((wet["level"], t["levelBasis"], t["expectedLoss"]), ("low", "loss", 0.0))
        self.assertEqual(t["lossWhenHit"]["finding"], "no_loss_found")
        trigger = wet["trigger"]
        self.assertEqual((trigger["type"], trigger["metric"]), ("hazard", "pr_ge25_days"))
        self.assertEqual([s["hit"] for s in trigger["perSeason"]], [True])
        self.assertGreaterEqual(trigger["worstValue"], trigger["threshold"])
        rootworm = next(r for r in corn["risks"] if r["ruleId"] == "corn_rootworm_continuous")
        condition = rootworm["trigger"]["conditions"][0]
        self.assertEqual(condition["fact"], "history.consecutive_same_crop")
        self.assertEqual(condition["actual"], 5)
        self.assertEqual(corn["score"], sum(p["points"] for p in corn["scoreBreakdown"]))
        self.assertEqual(result["historySource"]["kind"], "cdl")
        self.assertTrue(result["historySource"]["satelliteEstimate"])
        self.assertNotIn("explanation", json.dumps(result))

    def test_hazard_level_is_the_expected_loss_and_frequency_alone_stops_at_medium(self):
        props = {f"CDL{y}": 1 for y in range(2020, 2025)}

        def wet(loss):
            row = {"loss": loss, "se": "0.02", "sample": "all", "finding": "loss"}
            table = {("wet_planting_window", "corn"): row | {"county_years": "100"}}
            with mock.patch("rule_engine.facts._hazard_losses", return_value=table if loss else {}):
                result = self.advisor.advise(
                    field("191825000014246", props=props), "corn", [], "metric"
                )
            corn = next(c for c in result["candidates"] if c["crop"] == "corn")
            found = next(r for r in corn["risks"] if r["ruleId"] == "wet_planting_window")
            return found["level"], found["trigger"]

        # the hazard hit the one season on record (share 1.0)
        level, trigger = wet("0.02")
        self.assertEqual((level, trigger["expectedLoss"]), ("low", 0.02))
        level, trigger = wet("0.05")
        self.assertEqual((level, trigger["levelBasis"]), ("medium", "loss"))
        level, trigger = wet("0.2")  # high by expected loss, but one season cannot justify it
        self.assertEqual((level, trigger["levelCapped"]), ("medium", True))
        level, trigger = wet(None)  # no measured loss: graded by frequency, never above medium
        self.assertEqual((level, trigger["levelBasis"]), ("medium", "frequency"))
        self.assertEqual((trigger["levelCapped"], trigger["lossWhenHit"]), (False, None))

    def test_unless_gate_suppresses_hazard_only_when_the_fact_holds(self):
        source = Path(load_rules.__code__.co_filename).parent / "data" / "rules"
        with tempfile.TemporaryDirectory() as folder:
            for path in source.glob("*.yaml"):
                text = path.read_text()
                if "id: wet_planting_window" in text:
                    start = text.index("id: wet_planting_window")
                    at = text.index("    hazard:", start)
                    gate = (
                        "    unless:\n      - {fact: county.irrigated_share, op: ge, value: 0.5}\n"
                    )
                    text = text[:at] + gate + text[at:]
                (Path(folder) / path.name).write_text(text)
            advisor = RotationAdvisor(
                load_catalog(),
                load_rules(Path(folder)),
                load_reference(),
                SeasonSummaryStore(FIXTURES),
                CountyTrendYieldModel(),
            )
        props = {f"CDL{y}": 1 for y in range(2020, 2025)}

        def corn(shares):
            with mock.patch("rule_engine.facts._county_irrigated", return_value=shares):
                result = advisor.advise(field("191825000014246", props=props), "corn", [], "metric")
            return next(c for c in result["candidates"] if c["crop"] == "corn")

        irrigated = corn({("corn", "19015"): 0.9})
        self.assertNotIn("wet_planting_window", {r["ruleId"] for r in irrigated["risks"]})
        suppressed = {
            g["ruleId"]: g for g in irrigated["dataGaps"] if g["code"] == "rule_suppressed"
        }
        self.assertIn("heat_at_flowering", suppressed)  # the shipped gate applies as well
        self.assertEqual(suppressed["wet_planting_window"]["conditions"][0]["actual"], 0.9)
        unknown = corn({})  # no Census row: the hazard still fires
        self.assertIn("wet_planting_window", {r["ruleId"] for r in unknown["risks"]})
        dry = corn({("corn", "19015"): 0.1})
        self.assertIn("wet_planting_window", {r["ruleId"] for r in dry["risks"]})

    def test_fall_cereal_calendar_and_diversity_benefit_has_no_yield_factor(self):
        props = {"CDL2022": 1, "CDL2023": 5, "CDL2024": 1, "CDL2025": 5}
        result = self.advisor.advise(field("191825000014220", props=props), "corn", [], "metric")
        wheat = next(c for c in result["candidates"] if c["crop"] == "winter_wheat")
        self.assertEqual(wheat["calendar"]["kind"], "crop_default")
        self.assertNotIn("planted", wheat["calendar"]["stages"])
        self.assertIn(
            {
                "code": "hazard_stage_not_in_calendar",
                "ruleId": "wet_planting_window",
                "stage": "planted",
            },
            wheat["dataGaps"],
        )
        oats = next(c for c in result["candidates"] if c["crop"] == "oats")
        self.assertIn("diversity_benefit", {b["ruleId"] for b in oats["benefits"]})
        self.assertEqual(oats["yield"]["factorsApplied"], [])

    def test_priorities_change_ranking_and_income_bonus(self):
        props = {"CDL2022": 1, "CDL2023": 5, "CDL2024": 1}
        base = self.advisor.advise(field("191825000014220", props=props), "soybeans", [], "metric")
        erosion = self.advisor.advise(
            field("191825000014220", props=props), "soybeans", ["erosion"], "metric"
        )
        rank = lambda res, crop: next(c["rank"] for c in res["candidates"] if c["crop"] == crop)  # noqa: E731
        self.assertLessEqual(rank(erosion, "alfalfa"), rank(base, "alfalfa"))
        items = [
            {"crop": "a", "score": 0.0, "revenue": {"midUsd": 100}},
            {"crop": "b", "score": 0.0, "revenue": {"midUsd": 50}},
            {"crop": "c", "score": 0.0, "revenue": {"midUsd": 10}},
            {"crop": "d", "score": 0.0, "revenue": None},
        ]
        RotationAdvisor._apply_income_bonus(items, ["income"])
        self.assertEqual([i["score"] for i in items], [-2.0, -1.0, 0.0, 0.0])
        self.assertIsNone(items[3]["scoreBreakdown"][0]["revenueRank"])
        for item in items:
            item.pop("scoreBreakdown")
        RotationAdvisor._apply_income_bonus(items, [])
        self.assertEqual([i["score"] for i in items], [-2.0, -1.0, 0.0, 0.0])
        self.assertEqual(
            next(c for c in base["candidates"] if c["crop"] == "corn")["yield"]["unit"], "t/ha"
        )

    def test_field_without_csbid_still_returns_candidates_with_gaps(self):
        result = self.advisor.advise(field(None, crop="Soybeans"), "soybeans", [], "metric")
        self.assertIn("no_csb_id", {g["code"] for g in result["dataGaps"]})
        self.assertEqual(result["historySource"]["kind"], "declared")
        self.assertEqual(result["history"][0]["source"], "declared")
        soy = next(c for c in result["candidates"] if c["crop"] == "soybeans")
        self.assertEqual(soy["yield"]["level"], "state")  # no county yield without seasons
        self.assertIn("scn_soy_after_soy", {r["ruleId"] for r in soy["risks"]})
        self.assertTrue(all(c["soil"] for c in result["candidates"]))
        with self.assertRaises(ValueError):
            self.advisor.advise(field(None), "canola", [], "metric")
