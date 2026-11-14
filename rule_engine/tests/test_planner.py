import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from rule_engine import build_advisor
from rule_engine.facts import HistoryYear
from rule_engine.planner import (
    Action,
    Persistence,
    RotationEnv,
    RotationModel,
    SoilCarbon,
    Weights,
    build_context,
    evaluate,
    exact_plan,
    fixed_rotation,
    myopic,
    open_loop_plan,
    q_learning,
)
from rule_engine.planner.adapter import RuleAdapter
from rule_engine.planner.chance import YearChain, build_chain
from rule_engine.planner.sampler import modelled_loss
from rule_engine.planner.tables import CostTable, load_responses

FIXTURES = Path(__file__).parent / "fixtures" / "season_summary"
CSBID = "191825000014246"


def field(history=(1, 5, 1, 5, 1), soil=True):
    record = {
        "id": "planner-test",
        "area": 40.0,
        "sourceId": CSBID,
        "stateFips": "19",
        "countyFips": "19015",
        "sourceYear": 2025,
        "sourceProperties": {f"CDL{2021 + i}": code for i, code in enumerate(history)},
    }
    if soil:
        record["soil"] = {
            "om_pct": 4.0,
            "aws_100cm_mm": 150.0,
            "slope_pct": 2.0,
            "drainage_class": "Well drained",
        }
    return record


class PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.advisor = build_advisor()
        cls.context = build_context(field(), cls.advisor, [FIXTURES], reference_aws_mm=180.0)
        cls.model = RotationModel(cls.context, cls.advisor, horizon=4)

    def test_context_reads_history_and_seasons(self):
        self.assertEqual(self.context.history, ("corn", "soybeans", "corn", "soybeans", "corn"))
        self.assertEqual(self.context.history_source, "cdl")
        self.assertEqual(sorted(self.context.seasons), [2025])
        codes = {gap["code"] for gap in self.model.gaps}
        self.assertIn("history_is_satellite_estimate", codes)

    def test_history_part_matches_engine_assessment(self):
        """The adapter's lean rule pass must find what the engine's own assessment finds."""
        adapter = RuleAdapter(self.advisor, self.context)
        for history, crop, tillage, cover in [
            (("corn",) * 5, "corn", "conventional", "none"),
            (("corn", "soybeans", "corn", "soybeans", "corn"), "soybeans", "no_till", "rye"),
            (("soybeans", "oats", "corn", "soybeans", "corn"), "oats", "strip_till", "none"),
            (("corn", "alfalfa", "alfalfa", "alfalfa", "alfalfa"), "corn", "no_till", "none"),
        ]:
            part = adapter.history_part(history, crop, tillage, cover)
            years = [HistoryYear(i, c, None, "declared") for i, c in enumerate(history)]
            assessed = self.advisor._assess(
                self.advisor.catalog.crops[crop],
                adapter.field_with(tillage, cover),
                years,
                [],
                16.0,
                [],
                "imperial",
                "IA",
            )
            findings = assessed["risks"] + assessed["benefits"] + assessed["advisories"]
            expected_yield = {f["ruleId"] for f in findings if f["yieldFactor"]}
            expected_points = {
                f["ruleId"]: f["points"] for f in findings if f["points"] and not f["yieldFactor"]
            }
            self.assertEqual({r[0] for r in part.yield_rules}, expected_yield, history)
            self.assertEqual(dict(part.point_rules), expected_points, history)

    def test_continuous_corn_costs_more_and_yields_less(self):
        adapter = self.model.adapter
        rotated = adapter.history_part(("soybeans",), "corn", "conventional", "none")
        continuous = adapter.history_part(("corn",), "corn", "conventional", "none")
        self.assertLess(continuous.factor, rotated.factor)
        costs = CostTable()
        self.assertGreater(
            costs.crop_cost("corn", "corn", "conventional").usd_per_acre,
            costs.crop_cost("corn", "soybeans", "conventional").usd_per_acre,
        )
        derived = costs.crop_cost("corn", "corn", "strip_till")
        self.assertFalse(derived.verified)
        self.assertAlmostEqual(derived.usd_per_acre, 686.02 + 633.97 - 637.98, places=2)

    def test_alfalfa_seeding_year(self):
        costs = CostTable()
        self.assertLess(
            costs.crop_cost("alfalfa", "corn", "no_till").usd_per_acre,
            costs.crop_cost("alfalfa", "alfalfa", "no_till").usd_per_acre,
        )
        state = self.model.initial_state
        seeding = Action("alfalfa", "no_till", "none")
        after = self.model.transition(state, seeding)
        first = self.model.summary(state, seeding)["yieldPerAcre"]
        second = self.model.summary(after, seeding)["yieldPerAcre"]
        self.assertAlmostEqual(first / second, 0.625, places=2)

    def test_action_mask(self):
        state = self.model.initial_state
        labels = {a.label() for a in self.model.actions(state)}
        self.assertIn("corn/no_till/rye", labels)
        self.assertNotIn("oats/conventional/rye", labels)  # cool-season crop
        stand = self.model.transition(state, Action("alfalfa", "no_till", "none"))
        labels = {a.label() for a in self.model.actions(stand)}
        self.assertNotIn("corn/no_till/rye", labels)  # no rye into a standing perennial
        self.assertEqual({a for a in labels if a.startswith("alfalfa")}, {"alfalfa/no_till/none"})

    def test_modelled_loss_uses_response_table(self):
        adapter = self.model.adapter
        season = self.context.seasons[2025]
        weather = adapter.weather_part("corn", season)
        factor, drought, paid = modelled_loss("corn", weather, load_responses())
        self.assertGreater(factor, 0.0)
        self.assertLessEqual(factor, 1.0)
        if weather.drought_weeks is not None:
            self.assertIn("drought_monitor_critical_stage", paid)
            self.assertAlmostEqual(
                drought,
                min(0.6, weather.drought_weeks * 0.0065 + weather.d4_weeks * 0.08),
                places=6,
            )

    def test_soil_carbon_step(self):
        carbon = SoilCarbon()
        young, old = carbon.initial({"om_pct": 4.0})
        self.assertAlmostEqual(young + old, 4.0 * 22.62, places=1)
        _, bare = carbon.step(young, old, 0.0)
        _, fed = carbon.step(young, old, 1.0)
        self.assertLess(bare, fed)
        self.assertEqual(carbon.initial({}), (None, None))
        no_soil = build_context(field(soil=False), self.advisor, [FIXTURES])
        model = RotationModel(no_soil, self.advisor, horizon=2)
        self.assertIn("soil_organic_matter_unknown", {g["code"] for g in model.gaps})
        self.assertEqual(exact_plan(model).steps[0]["soilValueUsdPerAcre"], 0.0)

    def test_env_episode(self):
        env = RotationEnv(self.model, seed=1)
        observation, info = env.reset()
        self.assertEqual(observation["year"], 0)
        total, done, steps = 0.0, False, 0
        while not done:
            observation, reward, done, truncated, info = env.step(info["validActions"][0])
            total += reward
            steps += 1
        self.assertEqual(steps, self.model.horizon)
        self.assertEqual(info["validActions"], [])
        with self.assertRaises(ValueError):
            env.step(0)
        env.reset()
        rye_before_oats = env.actions.index(Action("oats", "conventional", "rye"))
        with self.assertRaises(ValueError):
            env.step(rye_before_oats)

    def test_exact_plan_is_at_least_as_good_as_baselines(self):
        best = exact_plan(self.model)
        self.assertEqual(len(best.actions), self.model.horizon)
        for other in (
            myopic(self.model),
            fixed_rotation(self.model, ("corn",), "conventional", "none"),
            fixed_rotation(self.model, ("corn", "soybeans"), "conventional", "none"),
            fixed_rotation(self.model, ("corn", "soybeans"), "no_till", "rye"),
        ):
            self.assertGreaterEqual(best.value + 1e-6, other.value, other.method)

    def test_q_learning_approaches_exact_plan(self):
        model = RotationModel(
            self.context,
            self.advisor,
            crops=("corn", "soybeans", "oats"),
            horizon=3,
            tillage=("conventional", "no_till"),
        )
        best = exact_plan(model)
        learned, table = q_learning(model, episodes=6000, seed=3)
        self.assertTrue(table)
        self.assertLessEqual(learned.value, best.value + 1e-6)
        self.assertGreater(learned.value, best.value - 0.05 * abs(best.value))

    def test_weights_change_the_plan_value(self):
        plain = RotationModel(
            self.context, self.advisor, horizon=3, weights=Weights(risk_usd_per_point=0.0)
        )
        cautious = RotationModel(
            self.context, self.advisor, horizon=3, weights=Weights(risk_usd_per_point=60.0)
        )
        action = Action("corn", "conventional", "none")
        state = plain.initial_state
        self.assertGreater(plain.expected(state, action), cautious.expected(state, action))


def several_years(context):
    """The fixture season repeated as 2019-2025, alternating a drought-free and a drought year."""
    season = context.seasons[2025]
    weeks = len(season.weekly["dm_max"])
    seasons = {}
    for year in range(2019, 2026):
        level = 3.0 if year % 2 else -1.0
        weekly = {**season.weekly, "dm_max": [level] * weeks}
        seasons[year] = replace(season, year=year, weekly=weekly)
    return replace(context, seasons=seasons)


class CarryOverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.advisor = build_advisor()
        base = build_context(field(), cls.advisor, [FIXTURES], reference_aws_mm=180.0)
        cls.context = several_years(base)
        cls.crops = ("corn", "soybeans", "oats")

    def model(self, **options):
        return RotationModel(self.context, self.advisor, crops=self.crops, horizon=3, **options)

    def test_chain_prefers_years_that_start_like_this_one_ended(self):
        start = {1: {"drought": 0.0, "price": None}, 2: {"drought": 3.0, "price": None}}
        end = {1: {"drought": 3.0, "price": None}, 2: {"drought": 0.0, "price": None}}
        chain = YearChain([1, 2], start, end, Persistence(strength=0.8))
        self.assertEqual(chain.signals, ("drought",))
        for row in chain.matrix:
            self.assertAlmostEqual(sum(row), 1.0)
        self.assertGreater(chain.matrix[0][1], chain.matrix[0][0])  # year 1 ended dry
        self.assertGreater(chain.matrix[1][0], chain.matrix[1][1])
        self.assertGreaterEqual(min(chain.matrix[0]), 0.1)  # the uniform share remains
        self.assertAlmostEqual(sum(chain.marginal(3)), 1.0)

    def test_no_chain_without_strength_or_years(self):
        model = self.model(persistence=Persistence(strength=0.0))
        self.assertIsNone(model.chain)
        self.assertIsNone(model.initial_state.prev)
        self.assertIsNone(build_chain(model.years[:3], {}, model.sampler.basis, Persistence()))
        self.assertAlmostEqual(exact_plan(model).value, open_loop_plan(model).value)

    def test_state_tracks_the_year_just_experienced(self):
        model = self.model()
        self.assertEqual(model.initial_state.prev, len(model.years) - 1)
        self.assertIn("year_odds_from_few_analog_years", {g["code"] for g in model.gaps})
        action = model.actions(model.initial_state)[0]
        with self.assertRaises(ValueError):
            model.transition(model.initial_state, action)
        self.assertEqual(model.transition(model.initial_state, action, 2).prev, 2)
        self.assertIsNone(model.transition(model.open_loop_state, action).prev)
        env = RotationEnv(model, seed=4)
        observation, info = env.reset()
        self.assertEqual(observation["lastYear"]["year"], 2025)
        observation, *_ = env.step(info["validActions"][0])
        self.assertIn(observation["lastYear"]["year"], range(2019, 2026))

    def test_reacting_is_never_worse_than_a_fixed_sequence(self):
        model = self.model()
        best, fixed = exact_plan(model), open_loop_plan(model)
        self.assertFalse(fixed.adaptive)
        self.assertGreaterEqual(best.value + 1e-6, fixed.value)
        self.assertGreaterEqual(best.value + 1e-6, myopic(model).value)
        learned, _ = q_learning(model, episodes=3000, seed=2)
        self.assertLessEqual(learned.value, best.value + 1e-6)

    def test_fixed_sequence_value_matches_its_own_forecast(self):
        """The open-loop solver's forecast uses step odds seen from the start of the plan."""
        model = self.model()
        fixed = open_loop_plan(model)
        state, total = model.open_loop_state, 0.0
        for action in fixed.actions:
            total += model.expected(state, action)
            state = model.transition(state, action)
        self.assertAlmostEqual(total, fixed.value, places=6)


class TabularTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from rule_engine.planner import tabular

        cls.tabular = tabular
        cls.advisor = build_advisor()
        base = build_context(field(), cls.advisor, [FIXTURES], reference_aws_mm=180.0)
        cls.model = RotationModel(
            several_years(base), cls.advisor, crops=("corn", "soybeans", "oats"), horizon=3
        )
        cls.table = tabular.tabulate(cls.model)

    def test_table_agrees_with_the_model(self):
        best, _ = self.tabular.score(self.table)
        short, _ = self.tabular.score(self.table, self.tabular.myopic_choice)
        self.assertAlmostEqual(best, exact_plan(self.model).value, delta=1.0)
        self.assertAlmostEqual(short, myopic(self.model).value, delta=1.0)
        self.assertGreaterEqual(best, short)

    def test_table_shape(self):
        table = self.table
        self.assertEqual(table.node_t[0], 0)
        self.assertEqual(
            table.reward.shape[1:], (len(self.tabular.ACTIONS), self.tabular.MAX_YEARS)
        )
        alfalfa = [i for i, a in enumerate(self.tabular.ACTIONS) if a.crop == "alfalfa"]
        self.assertFalse(table.mask[:, alfalfa].any())  # not among this model's crops
        last = table.node_t == self.model.horizon - 1
        self.assertTrue((table.next_node[last] == -1).all())
        self.assertTrue(np.allclose(table.odds[:7, :7].sum(axis=1), 1.0, atol=1e-5))

    def test_learned_policy_trains_scores_and_reloads(self):
        try:
            import torch  # noqa: F401
        except ImportError:
            self.skipTest("PyTorch is not installed")
        from rule_engine.planner import ppo

        data = ppo.FieldSet([self.table, self.table])
        net = ppo.train(data, ppo.Config(envs=64, iterations=3, hidden=16), log=None)
        result = ppo.benchmark(net, data)
        self.assertLessEqual(result["learnedUsdPerAcre"], result["optimumUsdPerAcre"] + 0.1)
        with tempfile.TemporaryDirectory() as folder:
            ppo.LearnedPolicy(net).save(f"{folder}/policy.pt")
            policy = ppo.LearnedPolicy.load(f"{folder}/policy.pt")
        plan = evaluate(self.model, policy.act_for(self.model), "ppo")
        self.assertAlmostEqual(plan.value, result["learnedUsdPerAcre"], delta=1.0)


if __name__ == "__main__":
    unittest.main()
