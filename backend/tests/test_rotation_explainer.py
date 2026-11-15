import sys
import unittest

from app.services import rotation_explainer as explainer
from app.services.rotation_advice import REPO

FIELD = {
    "id": "f1", "crop": "Corn", "area": 10, "sourceId": None, "countyFips": "19153",
    "sourceYear": 2025,
    "sourceProperties": {"CDL2021": 1, "CDL2022": 5, "CDL2023": 1, "CDL2024": 1, "CDL2025": 1},
}  # fmt: skip


class RotationExplainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO))
        from rule_engine import build_advisor

        advisor = build_advisor()
        cls.advice = advisor.advise(FIELD, "corn", ["water"], "metric")
        cls.rules = explainer.rule_index(advisor.rules)

    def test_topics_accept_only_known_names(self):
        self.assertEqual(explainer.explanation_topics({}), set())
        self.assertEqual(
            explainer.explanation_topics({"explain": ["why", "luck", "method"]}), {"why", "method"}
        )
        self.assertEqual(explainer.explanation_topics({"explain": "sources"}), {"sources"})

    def test_why_lists_the_rules_behind_the_score_with_what_they_rest_on(self):
        why = explainer.explain(self.advice, {"why"}, self.rules)["why"]
        intended = why["intended"]
        self.assertTrue(intended["isIntended"])
        self.assertGreater(intended["rank"], why["recommended"]["rank"])
        points = [p["points"] for p in intended["addedRisk"]]
        self.assertEqual(points, sorted(points, key=abs, reverse=True))
        rootworm = next(
            p for p in intended["addedRisk"] if p["ruleId"] == "corn_rootworm_continuous"
        )
        self.assertEqual(rootworm["basedOn"]["conditions"][0]["actual"], 3)
        self.assertTrue(rootworm["references"])
        self.assertEqual(why["basedOn"]["history"]["kind"], "cdl")
        self.assertTrue(why["basedOn"]["history"]["satelliteEstimate"])
        gaps = {row["gap"] for row in why["differenceFromRecommended"]}
        self.assertTrue(gaps and all(gap != 0 for gap in gaps))

    def test_method_reports_the_weights_the_result_used(self):
        method = explainer.explain(self.advice, {"method"}, self.rules)["method"]
        self.assertEqual(method["weights"]["priorityMultiplier"], 2)
        self.assertEqual(method["weights"]["riskPointsByLevel"], {"low": 1, "medium": 2, "high": 3})
        self.assertTrue(method["steps"] and method["limits"])

    def test_sources_name_data_sources_documents_and_rule_references(self):
        sources = explainer.explain(self.advice, {"why", "sources"}, self.rules)["sources"]
        names = [row["name"] for row in sources["dataSources"]]
        self.assertTrue(any("Cropland Data Layer" in name for name in names))
        self.assertTrue(all(row["url"].startswith("https://") for row in sources["dataSources"]))
        used = {row["ruleId"] for row in sources["ruleReferences"]}
        self.assertIn("corn_rootworm_continuous", used)
        self.assertTrue(sources["projectDocuments"])

    def test_nothing_is_added_unless_asked(self):
        self.assertEqual(explainer.explain(self.advice, set(), self.rules), {})

    def test_no_candidates_is_reported(self):
        self.assertEqual(explainer.why({"candidates": []}, {})["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
