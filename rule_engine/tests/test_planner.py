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
from rule_engine.planner.sampler import YearSampler, modelled_loss
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

    def test_one_matching_year_does_not_take_all_the_odds(self):
        # 2025 ended in a drought class that only 2000 started from
        labels = list(range(1981, 2026))
        start = {y: {"drought": 0.0, "price": 1.0} for y in labels}
        end = {y: {"drought": 0.0, "price": 1.0} for y in labels}
        start[2000]["drought"], end[2025]["drought"] = 3.0, 3.0
        chain = YearChain(labels, start, end, Persistence())
        first = chain.matrix[chain.latest]
        self.assertEqual(max(range(len(first)), key=first.__getitem__), labels.index(2000))
        self.assertLess(first[labels.index(2000)], 0.5)
        for row in chain.matrix:
            self.assertGreaterEqual(1.0 / sum(p * p for p in row), 45**0.5 - 1e-9)

    def test_no_chain_without_strength_or_years(self):
        model = self.model(persistence=Persistence(strength=0.0))
        self.assertIsNone(model.chain)
        self.assertIsNone(model.initial_state.prev)
        self.assertIsNone(
            build_chain(model.years[:3], {}, model.sampler.price_level, Persistence())
        )
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


class EconomicsTests(unittest.TestCase):
    def test_prices_are_drawn_as_changes_around_the_planning_price(self):
        from rule_engine.planner.sampler import price_changes

        changes = price_changes({1990: 2.0, 1991: 3.0, 1992: 3.0, 1993: 1.5})
        self.assertEqual(sorted(changes), [1991, 1992, 1993])  # the first year has no change
        self.assertAlmostEqual(sum(changes.values()) / 3, 1.0)
        self.assertGreater(changes[1991], changes[1992])
        self.assertGreater(changes[1992], changes[1993])

    def test_soil_test_sets_the_fertilizer_cost_change(self):
        from rule_engine.planner.nutrients import category, cost_changes, soil_test_effect

        self.assertEqual(category("phosphorus", 9)[0], "very_low")
        self.assertEqual(category("phosphorus", 10)[0], "low")
        self.assertEqual(category("phosphorus", 30, "mehlich3_icp")[0], "optimum")
        self.assertEqual(category("potassium", 150, "moist")[0], "optimum")
        self.assertEqual(category("potassium", 150, "dried")[0], "low")
        self.assertIsNone(category("potassium", 150, "unknown"))
        effects = soil_test_effect({"phosphorus": {"ppm": 40}, "potassium": {"ppm": 100}}, "NE")
        self.assertEqual([e["category"] for e in effects], ["very_high", "very_low"])
        self.assertEqual(effects[0]["calibration"], "iowa_applied_elsewhere")
        # corn: no P (-67 lb x 0.72) and build-up K ((145 - 46) lb x 0.39)
        self.assertAlmostEqual(cost_changes(effects)["corn"], -67 * 0.72 + 99 * 0.39, places=2)
        self.assertEqual(
            cost_changes(soil_test_effect({"phosphorus": {"ppm": 20}}, "IA"))["corn"], 0
        )

    def test_farmer_cost_replaces_the_level_and_keeps_the_differences(self):
        table = CostTable(region="Heartland")
        gap = (
            table.crop_cost("corn", "corn", "conventional").usd_per_acre
            - table.crop_cost("corn", "soybeans", "conventional").usd_per_acre
        )
        table.override("corn", 500.0)
        self.assertEqual(table.crop_cost("corn", "soybeans", "conventional").usd_per_acre, 500.0)
        self.assertAlmostEqual(
            table.crop_cost("corn", "corn", "conventional").usd_per_acre, 500.0 + gap
        )


class ZeroYieldTests(unittest.TestCase):
    def test_a_zero_county_yield_is_not_an_observation(self):
        advisor = build_advisor()
        base = several_years(build_context(field(), advisor, [FIXTURES], reference_aws_mm=180.0))
        zeroed = {
            year: replace(s, scalars={**s.scalars, "yield_corn_bu_ac": 0.0})
            for year, s in base.seasons.items()
        }
        model = RotationModel(
            replace(base, seasons=zeroed), advisor, crops=("corn", "soybeans"), horizon=1
        )
        basis = model.sampler.basis["corn"]
        self.assertGreater(basis.expected_yield, 0)
        self.assertNotEqual(basis.yield_level, "county")

    def test_a_yield_series_that_ended_long_ago_is_not_the_yield_level(self):
        advisor = build_advisor()
        context = build_context(field(), advisor, [FIXTURES], reference_aws_mm=180.0)
        # NASS published Iowa sorghum yields for 1980-1984 only: their trend read at 1985 is not
        # a 2026 yield, so the level comes from a wider area instead (the national series)
        crops = ("corn", "soybeans", "sorghum")
        model = RotationModel(context, advisor, crops=crops, horizon=2)
        basis = model.sampler.basis["sorghum"]
        self.assertEqual(basis.yield_level, "national")
        self.assertIn("yield_from_national", basis.notes)
        # planned as of 1986 the same series is current
        sampler = YearSampler(context, advisor, model.adapter, ["sorghum"], now=1986)
        self.assertEqual(sampler.basis["sorghum"].yield_level, "state")

    def county_corn(self, yields):
        """The corn basis of a field whose county published `yields` ({year: bu/acre})."""
        advisor = build_advisor()
        base = build_context(field(), advisor, [FIXTURES], reference_aws_mm=180.0)
        season = base.seasons[2025]
        seasons = {
            year: replace(
                season,
                year=year,
                scalars={**season.scalars, "yield_corn_bu_ac": yields.get(year, 0.0)},
            )
            for year in range(1981, 2026)
        }
        model = RotationModel(
            replace(base, seasons=seasons), advisor, crops=("corn", "soybeans"), horizon=1
        )
        return model, model.sampler.basis["corn"]

    def test_a_county_series_that_ended_is_not_the_yield_level(self):
        # county yields published for 1981-1993 only, at a third of today's level
        model, basis = self.county_corn({year: 60.0 for year in range(1981, 1994)})
        self.assertNotEqual(basis.yield_level, "county")
        self.assertGreater(basis.expected_yield, 120)
        self.assertIn("yield_history_ended", basis.notes)
        self.assertIn({"code": "yield_history_ended", "crop": "corn"}, model.gaps)
        # two recent years do not make a level either
        _, basis = self.county_corn({2024: 60.0, 2025: 60.0})
        self.assertNotEqual(basis.yield_level, "county")

    def test_a_short_county_series_gives_its_recent_mean_not_a_trend(self):
        # five falling years: their trend read at 2026 would be 140
        falling = {2021: 190.0, 2022: 180.0, 2023: 170.0, 2024: 160.0, 2025: 150.0}
        _, basis = self.county_corn(falling)
        self.assertEqual(basis.yield_level, "county")
        self.assertAlmostEqual(basis.expected_yield, 170.0, places=6)
        # old years are not read as bad years against the recent level
        _, basis = self.county_corn(falling | {1981: 60.0, 1982: 60.0})
        self.assertAlmostEqual(basis.expected_yield, 170.0, places=6)
        self.assertEqual(basis.observed_years, 5)


class FarmerResultTests(unittest.TestCase):
    """What the farmer reports: the crops replace the CDL labels, the yields set the level."""

    @classmethod
    def setUpClass(cls):
        cls.advisor = build_advisor()

    def basis(self, own=None, crop="corn"):
        record = field()
        if own:
            record["ownYields"] = {crop: own}
        context = several_years(
            build_context(record, self.advisor, [FIXTURES], reference_aws_mm=180.0)
        )
        model = RotationModel(context, self.advisor, crops=("corn", "soybeans"), horizon=1)
        return model.sampler.basis[crop]

    def test_declared_crops_replace_the_satellite_labels(self):
        record = field()
        record["declaredHistory"] = {2025: "soybeans", 2026: "corn", 2027: "not_a_crop"}
        from rule_engine.facts import crop_history

        context = build_context(record, self.advisor, [FIXTURES], reference_aws_mm=180.0)
        by_year = {y.year: y for y in crop_history(record, [], self.advisor.catalog)}
        self.assertEqual((by_year[2025].crop, by_year[2025].source), ("soybeans", "declared"))
        self.assertEqual((by_year[2026].crop, by_year[2026].source), ("corn", "declared"))
        self.assertEqual((by_year[2024].crop, by_year[2024].source), ("soybeans", "cdl"))
        self.assertNotIn(2027, by_year)
        self.assertEqual(context.last_history_year, 2026)  # the plan starts the year after

    def test_own_yields_set_the_field_level(self):
        plain = self.basis()
        self.assertEqual((plain.own_ratio, plain.own_points), (1.0, ()))
        probe = self.basis({2022: 1.0, 2023: 1.0, 2024: 1.0, 2025: 1.0})
        reference = {year: base for year, _, base in probe.own_points}
        self.assertEqual(sorted(reference), [2022, 2023, 2024, 2025])

        full = self.basis({year: 1.2 * base for year, base in reference.items()})
        self.assertAlmostEqual(full.own_ratio, 1.2, places=6)
        self.assertAlmostEqual(full.expected_yield, 1.2 * plain.expected_yield, places=6)
        self.assertEqual(full.yield_level, "field")

    def test_few_own_yields_are_pulled_towards_the_county_level(self):
        plain = self.basis()
        probe = self.basis({2024: 1.0, 2025: 1.0})
        two = self.basis({year: 1.2 * base for year, _, base in probe.own_points})
        # two reported years and two filled at the reference level: (1.2 + 1.2 + 1 + 1) / 4
        self.assertAlmostEqual(two.own_ratio, 1.1, places=6)
        self.assertAlmostEqual(two.expected_yield, 1.1 * plain.expected_yield, places=6)

    def test_only_the_latest_ten_own_yields_count(self):
        own = {year: 100.0 for year in range(2010, 2026)}
        self.assertEqual(
            [year for year, _, _ in self.basis(own).own_points], list(range(2016, 2026))
        )


class CropOptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.advisor = build_advisor()
        cls.context = build_context(field(), cls.advisor, [FIXTURES], reference_aws_mm=180.0)
        cls.model = RotationModel(
            cls.context, cls.advisor, crops=("corn", "soybeans", "oats", "alfalfa"), horizon=3
        )

    def test_best_option_is_the_best_fixed_plan(self):
        from rule_engine.planner.solve import crop_options

        options = crop_options(self.model)
        self.assertEqual(sorted(o["steps"][0][1].crop for o in options), sorted(self.model.crops))
        values = [o["value"] for o in options]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertAlmostEqual(values[0], open_loop_plan(self.model).value, places=6)
        self.assertTrue(all(len(o["steps"]) == 3 for o in options))

    def test_replay_runs_the_plan_through_consecutive_years(self):
        from rule_engine.planner.solve import crop_options, replay

        model = RotationModel(
            several_years(self.context), self.advisor, crops=("corn", "soybeans", "oats"), horizon=3
        )
        steps = crop_options(model)[0]["steps"]
        found = replay(model, steps)
        first, runs = found["first"], found["runs"]
        self.assertEqual([y["year"] for y in first["years"]], list(range(2019, 2026)))
        self.assertAlmostEqual(sum(y["odds"] for y in first["years"]), 1.0, places=6)
        summary = model.summary(*steps[0])
        self.assertAlmostEqual(
            first["mean"], summary["revenueUsdPerAcre"] - summary["costUsdPerAcre"], delta=0.02
        )
        self.assertLessEqual(first["p10"], first["p50"])
        self.assertLessEqual(first["p50"], first["p90"])
        self.assertEqual([r["year"] for r in runs["starts"]], list(range(2019, 2024)))
        self.assertTrue(0.0 <= runs["lossProbability"] <= 1.0)

    def test_a_seeded_perennial_stand_is_kept(self):
        from rule_engine.planner.dynamics import Action, State

        model = self.model
        start = model.open_loop_state
        seeded = model.transition(start, Action("alfalfa", "conventional", "none"))
        self.assertEqual({a.crop for a in model.actions(seeded)}, {"alfalfa"})
        old = State(0, ("corn", "alfalfa", "alfalfa", "alfalfa"), start.young, start.old, None)
        self.assertGreater(len({a.crop for a in model.actions(old)}), 1)
        # a stand that fills the known history may be older than it looks
        unknown_age = State(0, ("alfalfa",), start.young, start.old, None)
        self.assertGreater(len({a.crop for a in model.actions(unknown_age)}), 1)


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
        self.assertEqual(table.reward.shape[1:], (self.tabular.LOCAL, self.tabular.MAX_YEARS))
        self.assertEqual(
            [self.tabular.CROPS[c] for c in table.crops if c >= 0], list(self.model.crops)
        )
        unused = self.tabular.SLOT >= len(self.model.crops)
        self.assertFalse(table.mask[:, unused].any())
        last = table.node_t == self.model.horizon - 1
        self.assertTrue((table.next_node[last] == -1).all())
        self.assertTrue(np.allclose(table.odds[:7, :7].sum(axis=1), 1.0, atol=1e-5))

    def test_factored_reward_is_the_model_reward(self):
        table, model = self.table, self.model
        state = model.open_loop_state
        actions = self.tabular.ACTIONS
        for a in np.flatnonzero(table.mask[0]):
            action = actions[table.global_actions[a]]
            for y in range(len(model.years)):
                self.assertAlmostEqual(
                    float(table.reward[0, a, y]), model.outcome(state, action, y).reward, delta=0.01
                )

    def test_regional_costs(self):
        heartland = CostTable(region="Heartland")
        plain = CostTable()
        level = heartland.regional["corn"].usd_per_acre
        self.assertAlmostEqual(
            heartland.crop_cost("corn", "soybeans", "conventional").usd_per_acre, level
        )
        # the corn-after-corn and tillage differences come from the state budgets
        for previous, tillage in (("corn", "conventional"), ("soybeans", "strip_till")):
            self.assertAlmostEqual(
                heartland.crop_cost("corn", previous, tillage).usd_per_acre - level,
                plain.crop_cost("corn", previous, tillage).usd_per_acre
                - plain.crop_cost("corn", "soybeans", "conventional").usd_per_acre,
            )
        # ERS has no Heartland sorghum table: the national row is used and flagged
        self.assertFalse(heartland.crop_cost("sorghum", None, "no_till").verified)
        self.assertEqual(
            heartland.crop_cost("alfalfa", "alfalfa", "no_till"),
            plain.crop_cost("alfalfa", "alfalfa", "no_till"),
        )

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


class SoilLevelTests(unittest.TestCase):
    def test_soil_index_moves_yield_within_limits(self):
        import unittest.mock

        from rule_engine.planner import soil_level as module

        means = {"19169": {"county_fips": "19169", "fields": "40", "nccpi_corn": "0.60"}}
        with unittest.mock.patch.object(module, "county_means", lambda: means):
            better = module.soil_level("corn", {"nccpi_corn": 0.80}, "19169")
            self.assertAlmostEqual(better.ratio, 1 + 0.44 * 0.20)
            self.assertEqual(module.soil_level("corn", {"nccpi_corn": 0.05}, "19169").ratio, 0.85)
            self.assertIsNone(module.soil_level("corn", {}, "19169"))
            self.assertIsNone(module.soil_level("corn", {"nccpi_corn": 0.8}, "01001"))
            self.assertIsNone(module.soil_level("oats", {"nccpi_corn": 0.8}, "19169"))
            self.assertIsNone(module.soil_level("soybeans", {"nccpi_soy": 0.8}, "19169"))


class CellIndexTests(unittest.TestCase):
    """A field outside the sample reads the sampled field of its weather cell and county."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        import duckdb

        from rule_engine.cells import CellIndex, cell

        cls.cell = staticmethod(cell)
        cls.dir = tempfile.TemporaryDirectory()
        path = Path(cls.dir.name) / "summary_index.parquet"
        ix, iy = cell(-93.6, 42.0)
        rows = f"('A', '19169', {ix}, {iy}), ('B', '19169', {ix + 3}, {iy}), ('C', '19015', {ix}, {iy})"
        duckdb.connect().execute(
            f"COPY (SELECT * FROM (VALUES {rows}) t(CSBID, county_fips, ix, iy)) TO '{path}' "
            "(FORMAT PARQUET)"
        )
        cls.index = CellIndex(path)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_sampled_field_reads_itself(self):
        twin = self.index.twin("B", "19169", -93.6, 42.0)
        self.assertEqual((twin.csbid, twin.source, twin.distance_km), ("B", "own", 0.0))

    def test_same_cell_and_county(self):
        twin = self.index.twin("X", "19169", -93.6, 42.0)
        self.assertEqual((twin.csbid, twin.source, twin.distance_km), ("A", "weather_cell", 0.0))

    def test_county_decides_before_distance(self):
        # C is in the same cell but another county: its county yield is not this field's
        twin = self.index.twin("X", "19015", -93.6 + 2 / 24, 42.0)
        self.assertEqual((twin.csbid, twin.source), ("C", "nearby_cell"))
        self.assertGreater(twin.distance_km, 5)

    def test_nothing_close_enough(self):
        self.assertIsNone(self.index.twin("X", "19169", -90.0, 42.0))
        self.assertIsNone(self.index.twin("X", "01001", -93.6, 42.0))

    def test_twin_summaries_do_not_supply_crop_history(self):
        from rule_engine.summary import summary_key, summary_source

        field = {"sourceId": "X", "countyFips": "19169"}
        self.assertEqual(summary_key(field), ("X", "19169", True))
        field["summaryTwin"] = {
            "sourceId": "A",
            "countyFips": "19169",
            "source": "weather_cell",
            "distanceKm": 0.0,
        }
        self.assertEqual(summary_key(field), ("A", "19169", False))
        self.assertEqual(summary_source(field, [1])["kind"], "weather_cell")
        self.assertEqual(summary_source(field, [])["kind"], "none")


class GapFillTests(unittest.TestCase):
    """Crops without a yield or a price of their own take a documented wider level."""

    @classmethod
    def setUpClass(cls):
        cls.advisor = build_advisor()
        cls.context = build_context(field(), cls.advisor, [FIXTURES], reference_aws_mm=180.0)
        cls.adapter = RuleAdapter(cls.advisor, cls.context, [])

    def sampler(self, crops, context=None):
        return YearSampler(context or self.context, self.advisor, self.adapter, crops)

    def test_a_crop_whose_state_series_ended_takes_the_national_yield(self):
        basis = self.sampler(["sorghum"]).basis["sorghum"]  # NASS stopped Iowa sorghum in 1984
        self.assertEqual(basis.yield_level, "national")
        self.assertIn("yield_from_national", basis.notes)
        self.assertGreater(basis.expected_yield, 40)  # bu/acre of US grain sorghum
        self.assertGreater(basis.observed_years, 10)

    def test_a_crop_with_no_state_series_takes_the_national_or_region_yield(self):
        # NASS publishes no Iowa spring wheat yield, and the Heartland states none either
        basis = self.sampler(["spring_wheat"]).basis["spring_wheat"]
        self.assertEqual(basis.yield_level, "national")
        # corn for grain in a New England county: NASS reports silage only there, so the
        # level is the mean of the Northern Crescent states
        field_ct = {**self.context.field, "stateFips": "09", "countyFips": "09003"}
        context = replace(self.context, region="CT", field=field_ct, seasons={})
        basis = self.sampler(["corn"], context).basis["corn"]
        self.assertEqual(basis.yield_level, "region")
        self.assertIn("yield_from_region", basis.notes)
        self.assertGreater(basis.expected_yield, 100)

    def test_an_own_state_series_is_not_replaced_by_a_wider_one(self):
        basis = self.sampler(["oats"]).basis["oats"]
        self.assertEqual(basis.yield_level, "state")
        self.assertNotIn("yield_from_national", basis.notes)

    def test_regional_series_is_the_mean_of_the_region_states(self):
        import importlib.util

        path = Path(__file__).parents[1] / "planner" / "scripts" / "build_regional_history.py"
        spec = importlib.util.spec_from_file_location("build_regional_history", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        def row(state, year, value):
            return {
                "kind": "yield", "crop": "corn", "geography": state, "year": str(year),
                "value": str(value), "unit": "bu/acre", "nass_short_desc": "CORN",
            }  # fmt: skip

        history = [row("NY", 2020, 100), row("PA", 2020, 120), row("NY", 2021, 90)]
        history.append(row("IA", 2020, 200))
        out = module.regional_rows(history, {"NY": "A", "PA": "A", "IA": "B"})
        # 2021 has one state only, and the region of IA has one state
        self.assertEqual(out, [["yield", "corn", "ERS:A", 2020, 110.0, "bu/acre", "CORN", 2]])

    def test_a_crop_with_no_state_quote_takes_the_latest_published_price(self):
        # the rule engine has no cotton quote for Iowa: the latest US marketing year stands in
        basis = self.sampler(["cotton"]).basis["cotton"]
        self.assertEqual(basis.price_level, "national")
        self.assertIn("planning_price_from_history", basis.notes)
        self.assertTrue(0.3 < basis.price < 2.0)  # USD per lb

    def test_a_price_series_that_ended_is_not_todays_price(self):
        from rule_engine.planner.sampler import _history_quote

        def row(state, year, value):
            return {
                "kind": "price", "crop": "x", "geography": state, "year": str(year),
                "value": str(value), "unit": "usd/cwt", "nass_short_desc": "X",
            }  # fmt: skip

        rows = [row("RI", 2015, 9), row("US", 2025, 12)]
        quote = _history_quote(rows, "x", "RI", 2026)
        self.assertEqual((quote.price_usd, quote.level, quote.unit), (12.0, "national", "cwt"))
        self.assertIsNone(_history_quote(rows, "x", "RI", 2040))

    def test_pasture_is_not_sold_so_it_has_no_price(self):
        sampler = self.sampler(["grass_pasture"])
        self.assertEqual(sampler.unavailable, {"grass_pasture": "not_marketed"})

    def test_other_hay_has_a_yield_and_price_series(self):
        basis = self.sampler(["other_hay"]).basis["other_hay"]
        self.assertEqual(basis.yield_level, "state")
        self.assertGreater(basis.observed_years, 30)
        self.assertGreater(basis.price_years, 30)
