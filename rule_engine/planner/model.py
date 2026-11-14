"""The rotation planning problem as a Markov decision process.

State    last five crops, years planned so far, soil carbon pools, the year just experienced.
Action   crop x tillage x cover crop grown before it (invalid combinations are masked).
Chance   one historical year per step (weather, yields and prices together). Its odds depend on
         the year just experienced (chance.py): drought and price level carry over.
Reward   USD per acre per year: revenue - cost - risk penalty + soil carbon value.

    revenue  = drawn-year yield x rotation and practice yield factors (engine rules) x soil
               water modifier x drawn-year price
    cost     = cost of production without land (ISU budgets) + cover crop cost
    risk     = weight x engine points of every finding that is not already paid for in yield
    soil     = weight x change in stable soil carbon (t C/ha)

The crop history and the soil pools move deterministically with the action. The year just
experienced is the random part of the state: because it shifts the odds of the next year, the
best plan is a policy that reacts to it, not a fixed sequence. A state with `prev=None` does not
track it and sees each step's odds from the start of the plan; solving from
`open_loop_state` therefore gives the best fixed sequence. With `Persistence(strength=0)`, or
too few years, the years are independent and the two coincide.
"""

import math
from dataclasses import dataclass, field, replace

from rule_engine.engine import RotationAdvisor
from rule_engine.planner.adapter import RuleAdapter
from rule_engine.planner.chance import Persistence, build_chain
from rule_engine.planner.context import FieldContext
from rule_engine.planner.dynamics import Action, SoilCarbon, State, shift
from rule_engine.planner.sampler import Year, YearSampler
from rule_engine.planner.tables import (
    COVER,
    TILLAGE,
    CostTable,
    load_adjustments,
    load_carbon_inputs,
)

DEFAULT_CROPS = ("corn", "soybeans", "oats", "alfalfa")
HA_PER_ACRE = 0.404686


@dataclass(frozen=True)
class Weights:
    """Preferences, not data. Change them to express what the farmer values."""

    risk_usd_per_point: float = 20.0  # USD/acre charged per engine risk point
    soil_usd_per_t_c: float = 50.0  # USD per tonne of stable carbon gained per hectare
    risk_aversion: float = 0.0  # subtract this many standard deviations of the yearly reward
    cover_cost_share_usd: float = 0.0  # USD/acre paid back for a cover crop (e.g. IDALS 20-30)


@dataclass(frozen=True)
class Outcome:
    reward: float
    revenue: float
    cost: float
    risk: float
    soil: float
    yield_per_acre: float
    price: float
    year: int
    detail: dict = field(default_factory=dict)


def _mean(values: list[float], weights: list[float]) -> float:
    return sum(v * w for v, w in zip(values, weights))


class RotationModel:
    def __init__(
        self,
        context: FieldContext,
        advisor: RotationAdvisor,
        crops: tuple[str, ...] | None = None,
        priorities: tuple[str, ...] = (),
        horizon: int = 5,
        weights: Weights = Weights(),
        tillage: tuple[str, ...] = TILLAGE,
        cover: tuple[str, ...] = COVER,
        costs: CostTable | None = None,
        soil_carbon: SoilCarbon = SoilCarbon(),
        persistence: Persistence = Persistence(),
    ):
        self.context, self.advisor = context, advisor
        self.horizon, self.weights = horizon, weights
        self.costs = costs or CostTable()
        self.soil_carbon = soil_carbon
        self.carbon_inputs = load_carbon_inputs()
        self.adjustments = load_adjustments()
        self.adapter = RuleAdapter(advisor, context, priorities)
        candidates = set(advisor.candidate_ids(context.region))
        wanted = [c for c in (crops or DEFAULT_CROPS)]
        self.gaps: list[dict] = list(context.gaps)
        usable = []
        for crop in wanted:
            if crop not in candidates:
                self.gaps.append({"code": "crop_not_candidate", "crop": crop})
            elif crop not in self.costs.crops:
                self.gaps.append({"code": "no_cost_budget", "crop": crop})
            else:
                usable.append(crop)
        self.sampler = YearSampler(context, advisor, self.adapter, usable)
        for crop, reason in self.sampler.unavailable.items():
            self.gaps.append({"code": reason, "crop": crop})
        self.crops = tuple(c for c in usable if c in self.sampler.basis)
        if not self.crops:
            raise ValueError("no crop has a cost budget, a price and a yield for this field")
        if not self.sampler.years:
            raise ValueError("no historical year to draw from")
        self.years: list[Year] = self.sampler.years
        self.chain = build_chain(self.years, context.seasons, self.sampler.basis, persistence)
        self._uniform = [1.0 / len(self.years)] * len(self.years)
        self.tillage, self.cover = tuple(tillage), tuple(cover)
        self.all_actions = [
            Action(c, t, k) for c in self.crops for t in self.tillage for k in self.cover
        ]
        self._lifecycle = {c: advisor.catalog.crops[c].value("lifecycle") for c in self.crops}
        self._season = {c: advisor.catalog.crops[c].value("season") for c in self.crops}
        self._base: dict = {}
        self._expected: dict = {}
        young, old = soil_carbon.initial(context.soil)
        latest = self.chain.latest if self.chain else None
        self.initial_state = State(0, context.history, young, old, latest)
        self.open_loop_state = replace(self.initial_state, prev=None)
        if self.chain:
            self.gaps.append({"code": "year_odds_from_few_analog_years", "years": len(self.years)})
        if old is None:
            self.gaps.append({"code": "soil_organic_matter_unknown", "affects": ["soil_carbon"]})
        elif not soil_carbon.verified:
            self.gaps.append({"code": "soil_carbon_model_uncalibrated"})
        self._data_gaps()

    # -- actions and transition ---------------------------------------------------------

    def actions(self, state: State) -> list[Action]:
        previous = state.history[-1] if state.history else None
        out = []
        for action in self.all_actions:
            established = self._lifecycle[action.crop] == "perennial" and previous == action.crop
            if established and action.tillage != self.tillage[-1]:
                continue  # a standing perennial is not tilled: keep one representative action
            if action.cover != "none":
                previous_perennial = (
                    previous is not None
                    and self.advisor.catalog.crops[previous].value("lifecycle") == "perennial"
                )
                if self._season[action.crop] != "warm" or previous_perennial or established:
                    continue  # an overwintering cover crop fits only before a spring-planted crop
            out.append(action)
        return out

    def expected_yield_t_ha(self, state: State, action: Action) -> float:
        crop = self.advisor.catalog.crops[action.crop]
        basis = self.sampler.basis[action.crop]
        per_acre = (
            basis.expected_yield
            * self.adapter.history_part(
                state.history, action.crop, action.tillage, action.cover
            ).factor
            * self._establishment(state, action)
        )
        factor = crop.bu_to_t_ha if basis.unit == "bu" else crop.ton_to_t_ha
        return per_acre * (factor or 0.0)

    def distribution(self, state: State) -> list[float]:
        """Odds of each drawable year for the coming season."""
        if self.chain is None:
            return self._uniform
        if state.prev is None:
            return self.chain.marginal(state.t)
        return self.chain.matrix[state.prev]

    def transition(self, state: State, action: Action, year_index: int | None = None) -> State:
        """Next state; `year_index` is the year that was drawn, needed when the state tracks it."""
        tracked = self.chain is not None and state.prev is not None
        if tracked and year_index is None:
            raise ValueError("this state tracks the year just experienced: pass year_index")
        young, old = self._advance(state, action)
        history = shift(state.history, action.crop)
        return State(state.t + 1, history, young, old, year_index if tracked else None)

    def _advance(self, state: State, action: Action) -> tuple[float | None, float | None]:
        young, old = state.young, state.old
        if old is not None:
            crop = self.advisor.catalog.crops[action.crop]
            added = self.soil_carbon.stable_input(
                crop, self.expected_yield_t_ha(state, action), action.cover, self.carbon_inputs
            )
            young, old = self.soil_carbon.step(young, old, added)
        return young, old

    def terminal(self, state: State) -> bool:
        return state.t >= self.horizon

    # -- reward -------------------------------------------------------------------------

    def _establishment(self, state: State, action: Action) -> float:
        previous = state.history[-1] if state.history else None
        row = self.adjustments.get(f"{action.crop}_seeding_year_yield")
        return row["value"] if row and previous != action.crop else 1.0

    def _water_modifier(self, drought_loss: float) -> float:
        """Scale the season's drought loss by the field's water storage against the reference.

        Direction is supported by Mieno (UNL 2025, preliminary): low water-holding soils lose
        about 50 bu/acre more corn in a severe deficit year. The proportional form is a heuristic.
        """
        aws, reference = self.context.soil.get("aws_100cm_mm"), self.context.reference_aws_mm
        if not aws or not reference or not drought_loss:
            return 1.0
        scale = min(2.0, max(0.5, reference / float(aws)))
        return max(0.5, 1.0 - drought_loss * (scale - 1.0))

    def _soil_reward(self, state: State, action: Action) -> float:
        if state.old is None or not self.weights.soil_usd_per_t_c:
            return 0.0
        gain_t_c_ha = sum(self._advance(state, action)) - state.stable_carbon
        return self.weights.soil_usd_per_t_c * gain_t_c_ha * HA_PER_ACRE  # USD/acre

    def _base_outcomes(self, history: tuple[str, ...], action: Action) -> list[Outcome]:
        """Everything except the soil term, for every drawable year."""
        key = (history, action)
        if key in self._base:
            return self._base[key]
        previous = history[-1] if history else None
        part = self.adapter.history_part(history, action.crop, action.tillage, action.cover)
        state = State(0, history, None, None)
        establishment = self._establishment(state, action)
        cost = self.costs.crop_cost(action.crop, previous, action.tillage)
        cover = self.costs.cover_cost(action.cover)
        cost_usd = cost.usd_per_acre + cover.usd_per_acre
        if action.cover != "none":
            cost_usd -= self.weights.cover_cost_share_usd
        outcomes = []
        for year in self.years:
            draw = year.crops[action.crop]
            weather_points, unpaid = 0.0, []
            if draw.weather is not None:
                for hit in draw.weather.hazards:
                    if hit.rule not in draw.paid_rules:
                        weather_points += hit.points
                        unpaid.append(hit.rule)
                weather_points += draw.weather.county_points
            water = self._water_modifier(draw.drought_loss)
            yield_per_acre = draw.yield_per_acre * part.factor * establishment * water
            revenue = yield_per_acre * draw.price
            risk = self.weights.risk_usd_per_point * (part.points + weather_points)
            outcomes.append(
                Outcome(
                    reward=revenue - cost_usd - risk,
                    revenue=revenue,
                    cost=cost_usd,
                    risk=risk,
                    soil=0.0,
                    yield_per_acre=yield_per_acre,
                    price=draw.price,
                    year=year.year,
                    detail={
                        "yieldMode": draw.mode,
                        "yieldAnomaly": round(draw.anomaly, 3),
                        "ruleYieldFactor": round(part.factor, 3),
                        "waterModifier": round(water, 3),
                        "establishmentFactor": establishment,
                        "rulePoints": part.points,
                        "weatherPoints": weather_points,
                        "hazardsAsPoints": unpaid,
                    },
                )
            )
        self._base[key] = outcomes
        return outcomes

    def outcome(self, state: State, action: Action, year_index: int) -> Outcome:
        base = self._base_outcomes(state.history, action)[year_index]
        soil = self._soil_reward(state, action)
        return Outcome(**{**base.__dict__, "reward": base.reward + soil, "soil": soil})

    def expected(self, state: State, action: Action) -> float:
        """Mean yearly reward under the state's year odds, less risk_aversion x its spread."""
        odds = (
            None if self.chain is None else state.prev if state.prev is not None else -state.t - 1
        )
        key = (state.history, action, odds)
        if key not in self._expected:
            rewards = [o.reward for o in self._base_outcomes(state.history, action)]
            weights = self.distribution(state)
            average = _mean(rewards, weights)
            spread = math.sqrt(_mean([(r - average) ** 2 for r in rewards], weights))
            self._expected[key] = (average, spread)
        average, spread = self._expected[key]
        return average - self.weights.risk_aversion * spread + self._soil_reward(state, action)

    def summary(self, state: State, action: Action) -> dict:
        """Expected breakdown of one step, for reports."""
        outcomes = self._base_outcomes(state.history, action)
        part = self.adapter.history_part(state.history, action.crop, action.tillage, action.cover)
        rewards = [o.reward for o in outcomes]
        soil = self._soil_reward(state, action)
        odds = self.distribution(state)
        return {
            "crop": action.crop,
            "tillage": action.tillage,
            "coverCrop": action.cover,
            "expectedUsdPerAcre": round(_mean(rewards, odds) + soil, 2),
            "worstYearUsdPerAcre": round(min(rewards) + soil, 2),
            "bestYearUsdPerAcre": round(max(rewards) + soil, 2),
            "worstYear": outcomes[rewards.index(min(rewards))].year,
            "revenueUsdPerAcre": round(_mean([o.revenue for o in outcomes], odds), 2),
            "costUsdPerAcre": round(outcomes[0].cost, 2),
            "riskPenaltyUsdPerAcre": round(_mean([o.risk for o in outcomes], odds), 2),
            "soilValueUsdPerAcre": round(soil, 2),
            "yieldPerAcre": round(_mean([o.yield_per_acre for o in outcomes], odds), 2),
            "yieldUnit": self.sampler.basis[action.crop].unit + "/acre",
            "yieldRules": [r[0] for r in part.yield_rules],
            "pointRules": [r[0] for r in part.point_rules],
            "weakRules": list(part.weak_rules),
        }

    def key(self, state: State) -> tuple:
        """Hashable state for tabular solvers; the soil pools are rounded to 0.05 t C/ha."""
        if state.old is None or not self.weights.soil_usd_per_t_c:
            return state.t, state.history, state.prev
        pools = round(state.young / 0.05), round(state.old / 0.05)
        return state.t, state.history, state.prev, *pools

    # -- data gaps ----------------------------------------------------------------------

    def _data_gaps(self) -> None:
        for crop in self.crops:
            basis = self.sampler.basis[crop]
            for note in basis.notes:
                self.gaps.append({"code": note, "crop": crop})
            if not basis.yield_verified:
                self.gaps.append({"code": "yield_unverified", "crop": crop})
            modes = {y.crops[crop].mode for y in self.years}
            if modes != {"observed"}:
                self.gaps.append(
                    {
                        "code": "yield_not_observed_every_year",
                        "crop": crop,
                        "years": {
                            m: [y.year for y in self.years if y.crops[crop].mode == m]
                            for m in sorted(modes - {"observed"})
                        },
                    }
                )
            unverified = sorted(
                {
                    t
                    for (c, s, t), cost in self.costs.rows.items()
                    if c == crop and not cost.verified
                }
            )
            if unverified:
                self.gaps.append({"code": "cost_unverified", "crop": crop, "tillage": unverified})
        if "rye" in self.cover and not self.costs.cover_cost("rye").verified:
            self.gaps.append({"code": "cover_crop_seed_cost_unverified"})
        if self.context.history_source == "cdl":
            self.gaps.append({"code": "history_is_satellite_estimate", "source": "USDA CDL/CSB"})
