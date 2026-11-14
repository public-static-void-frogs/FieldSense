import tempfile
import unittest
from pathlib import Path

from rule_engine.catalog import load_catalog
from rule_engine.rules import Condition, RuleError, applies, evaluate, load_rules

BAD_RULE = """
version: "t"
rules:
  - id: bad
    title: Bad
    category: water
    applies_to: {{crops: [corn]}}
    when:
      - {{fact: {fact}, op: {op}, value: 1}}
    effect: {{kind: risk, level: high}}
    evidence_strength: weak
"""


class RuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.rules = load_rules()

    def test_shipped_rules_load_with_unique_ids_and_version(self):
        ids = [rule.id for rule in self.rules.rules]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("corn_rootworm_continuous", ids)
        self.assertIn("heat_at_flowering", ids)
        self.assertTrue(self.rules.version)
        timed = [rule for rule in self.rules.rules if rule.hazard]
        self.assertTrue(
            all(rule.effect.level_bands for rule in timed if rule.effect.kind == "risk")
        )

    def _load_bad(self, fact, op):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "x.yaml").write_text(BAD_RULE.format(fact=fact, op=op))
            load_rules(Path(folder))

    def test_unknown_fact_or_operator_fails_at_load(self):
        with self.assertRaises(RuleError):
            self._load_bad("weather.tmax", "ge")
        with self.assertRaises(RuleError):
            self._load_bad("history.years", "approximately")

    def test_prose_explanation_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            text = BAD_RULE.format(fact="history.years", op="ge") + "    explanation: words\n"
            (Path(folder) / "x.yaml").write_text(text)
            with self.assertRaises(RuleError):
                load_rules(Path(folder))

    def test_evaluate_operators_and_missing_facts(self):
        facts = {
            "history.years": 4,
            "history.prev1.crop": "corn",
            "history.shared": ["a"],
            "candidate.min_return_years": 2,
            "history.since": 1,
        }
        self.assertTrue(evaluate([Condition("history.years", "ge", 4)], facts))
        self.assertFalse(evaluate([Condition("history.years", "gt", 4)], facts))
        self.assertTrue(
            evaluate([Condition("history.prev1.crop", "in", ["corn", "sorghum"])], facts)
        )
        self.assertTrue(evaluate([Condition("history.shared", "contains", "a")], facts))
        self.assertFalse(evaluate([Condition("history.missing", "ge", 1)], facts))
        self.assertTrue(evaluate([Condition("history.missing", "is_null")], facts))
        self.assertTrue(
            evaluate([Condition("history.since", "lt", "@candidate.min_return_years")], facts)
        )

    def test_applies_via_crop_group_and_trait(self):
        by_id = {rule.id: rule for rule in self.rules.rules}
        corn, soy, oats, alfalfa = (
            self.catalog.crops[c] for c in ("corn", "soybeans", "oats", "alfalfa")
        )
        self.assertTrue(applies(by_id["corn_rootworm_continuous"], corn, self.catalog))
        self.assertFalse(applies(by_id["corn_rootworm_continuous"], soy, self.catalog))
        self.assertTrue(applies(by_id["heat_at_flowering"], oats, self.catalog))
        self.assertTrue(applies(by_id["scn_soy_after_soy"], soy, self.catalog))
        self.assertFalse(applies(by_id["scn_soy_after_soy"], corn, self.catalog))
        self.assertTrue(applies(by_id["erosion_protection_benefit"], alfalfa, self.catalog))
        self.assertFalse(applies(by_id["erosion_protection_benefit"], corn, self.catalog))
        self.assertTrue(applies(by_id["legume_n_credit"], corn, self.catalog))
        self.assertFalse(applies(by_id["legume_n_credit"], soy, self.catalog))
