"""The second loss measure: a season against operating costs, not the full economic cost."""

import unittest

from rule_engine import build_advisor
from rule_engine.planner import RotationModel, build_context
from rule_engine.planner.solve import crop_options, replay
from rule_engine.planner.tables import CostTable
from rule_engine.tests.test_planner import FIXTURES, field, several_years


class OperatingCostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.advisor = build_advisor(summary_root=FIXTURES)
        cls.context = several_years(
            build_context(field(), cls.advisor, [FIXTURES], reference_aws_mm=180.0)
        )

    def test_ers_crops_split_into_operating_costs_and_the_rest(self):
        table = CostTable(region="Heartland")
        share = table.operating_share("corn", None)
        self.assertTrue(0.5 < share < 0.75)  # ERS corn: seed, fertilizer, chemicals, fuel, repairs
        self.assertTrue(0.3 < table.operating_share("soybeans", None) < share)
        table.override("corn", 500.0)  # the farmer's own number: its split is not known
        self.assertIsNone(table.operating_share("corn", None))

    def test_overhead_is_the_part_of_the_crop_cost_that_is_not_operating(self):
        model = RotationModel(self.context, self.advisor, crops=("corn", "soybeans"), horizon=2)
        state, action = crop_options(model)[0]["steps"][0]
        previous = state.history[-1]
        cost = model.costs.crop_cost(action.crop, previous, action.tillage).usd_per_acre
        share = model.costs.operating_share(action.crop, previous)
        self.assertAlmostEqual(model.overhead(state.history, action), (1 - share) * cost)

    def test_loss_against_operating_costs_is_never_more_likely_than_against_all_costs(self):
        model = RotationModel(self.context, self.advisor, crops=("corn", "soybeans"), horizon=2)
        steps = crop_options(model)[0]["steps"]
        first = replay(model, steps)["first"]
        overhead = model.overhead(steps[0][0].history, steps[0][1])
        self.assertAlmostEqual(first["overhead"], overhead)
        expected = sum(y["odds"] for y in first["years"] if y["cash"] + overhead < 0)
        self.assertAlmostEqual(first["operatingLossProbability"], expected)
        self.assertLessEqual(first["operatingLossProbability"], first["lossProbability"])
        runs = replay(model, steps)["runs"]
        self.assertLessEqual(runs["operatingLossProbability"], runs["lossProbability"])

    def test_a_farmer_cost_has_no_operating_measure(self):
        record = field() | {"economics": {"costs": {"corn": 700.0, "soybeans": 450.0}}}
        context = several_years(
            build_context(record, self.advisor, [FIXTURES], reference_aws_mm=180.0)
        )
        model = RotationModel(context, self.advisor, crops=("corn", "soybeans"), horizon=2)
        found = replay(model, crop_options(model)[0]["steps"])
        self.assertIsNone(found["first"]["operatingLossProbability"])
        self.assertIsNone(found["runs"]["operatingLossProbability"])


if __name__ == "__main__":
    unittest.main()
