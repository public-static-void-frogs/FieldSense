"""A plan built by a learned policy instead of the exact optimum."""

import tempfile
import unittest
from pathlib import Path

from rule_engine import build_advisor
from rule_engine.planner import RotationModel, build_context
from rule_engine.planner.dynamics import Action
from rule_engine.planner.learned import NO_FILE, NO_FIT, load_policy, observation_size
from rule_engine.planner.solve import crop_options
from rule_engine.tests.test_planner import FIXTURES, field, several_years

try:
    import torch
except ModuleNotFoundError:  # the planner serves the exact plan without it
    torch = None


class ScaleTests(unittest.TestCase):
    def test_every_crop_the_policy_can_plan_has_a_yield_and_a_price_scale(self):
        from rule_engine.planner.tables import CROPS
        from rule_engine.planner.tabular import PRICE_SCALE, YIELD_SCALE

        self.assertEqual(set(CROPS) - set(YIELD_SCALE), set())
        self.assertEqual(set(CROPS) - set(PRICE_SCALE), set())


class PolicyPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.advisor = build_advisor(summary_root=FIXTURES)
        context = several_years(
            build_context(field(), cls.advisor, [FIXTURES], reference_aws_mm=180.0)
        )
        cls.model = RotationModel(context, cls.advisor, crops=("corn", "soybeans"), horizon=3)

    def test_the_seasons_after_the_first_follow_the_given_policy(self):
        wanted = Action("corn", self.model.tillage[0], "none")
        options = crop_options(self.model, policy=lambda state: wanted)
        self.assertEqual({o["steps"][0][1].crop for o in options}, {"corn", "soybeans"})
        for option in options:
            self.assertEqual([a for _, a in option["steps"][1:]], [wanted, wanted])
        optimum = {o["steps"][0][1].crop: o["value"] for o in crop_options(self.model)}
        for option in options:  # no policy beats the optimum for the same first crop
            self.assertLessEqual(option["value"], optimum[option["steps"][0][1].crop] + 1e-9)

    def test_an_action_the_state_does_not_allow_falls_back_to_the_optimum(self):
        options = crop_options(self.model, policy=lambda state: Action("rice", "none", "none"))
        optimum = crop_options(self.model)
        self.assertEqual(
            [[a for _, a in o["steps"]] for o in options],
            [[a for _, a in o["steps"]] for o in optimum],
        )

    def test_missing_file_is_reported_not_raised(self):
        self.assertEqual(load_policy(None), (None, NO_FILE))
        self.assertEqual(load_policy(Path("/nonexistent/policy.pt")), (None, NO_FILE))

    @unittest.skipIf(torch is None, "torch is not installed")
    def test_a_saved_network_plans_and_a_wrong_sized_one_is_refused(self):
        from rule_engine.planner.ppo import LearnedPolicy, PolicyNet

        torch.manual_seed(0)
        with tempfile.TemporaryDirectory() as folder:
            good, bad = Path(folder) / "policy.pt", Path(folder) / "old.pt"
            LearnedPolicy(PolicyNet(observation_size(), 16)).save(good)
            LearnedPolicy(PolicyNet(observation_size() - 12, 16)).save(bad)
            policy, why = load_policy(good)
            self.assertIsNone(why)
            self.assertEqual(load_policy(bad), (None, NO_FIT))
        options = crop_options(self.model, policy=policy.act_for(self.model))
        self.assertEqual(len(options), 2)
        for option in options:
            self.assertEqual(len(option["steps"]), 3)
            for state, action in option["steps"]:
                self.assertIn(action, self.model.actions(state))


if __name__ == "__main__":
    unittest.main()
