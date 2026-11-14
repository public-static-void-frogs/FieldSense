"""Solvers: exact dynamic programming (the reference), tabular Q-learning, and fixed baselines.

Every plan is scored the same way, by `evaluate`: the exact expected value of following a policy
from the model's initial state under the model's year odds.
"""

from dataclasses import dataclass, replace
from random import Random

from rule_engine.planner.dynamics import Action, State
from rule_engine.planner.env import RotationEnv
from rule_engine.planner.model import RotationModel


@dataclass(frozen=True)
class Plan:
    value: float  # expected total USD/acre over the horizon (risk-adjusted if risk_aversion > 0)
    actions: tuple[Action, ...]  # the most likely action of each year
    steps: tuple[dict, ...]
    method: str

    @property
    def adaptive(self) -> bool:
        """True when some year's action depends on what happened before it."""
        return any("choices" in step for step in self.steps)

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "expectedTotalUsdPerAcre": round(self.value, 2),
            "expectedPerYearUsdPerAcre": round(self.value / max(1, len(self.actions)), 2),
            "adaptive": self.adaptive,
            "steps": list(self.steps),
        }


def successors(model: RotationModel, state: State, action: Action) -> list[tuple[float, State]]:
    """[(probability, next state)]: one state unless the state tracks the year just experienced."""
    if model.chain is None or state.prev is None:
        return [(1.0, model.transition(state, action))]
    base = model.transition(state, action, 0)
    return [(p, replace(base, prev=j)) for j, p in enumerate(model.distribution(state)) if p > 0]


def evaluate(model: RotationModel, policy, method: str) -> Plan:
    """Exact expected value of a policy (state -> action) from the model's initial state.

    A year where the policy always takes the same action is reported as one step. A year where
    the action depends on what came before lists each choice with its probability and the years
    after which it is taken.
    """
    frontier: dict[State, float] = {model.initial_state: 1.0}
    total, actions, steps = 0.0, [], []
    for year in range(1, model.horizon + 1):
        groups: dict[Action, list[tuple[float, State]]] = {}
        following: dict[State, float] = {}
        for state, weight in frontier.items():
            action = policy(state)
            total += weight * model.expected(state, action)
            groups.setdefault(action, []).append((weight, state))
            for p, after in successors(model, state, action):
                following[after] = following.get(after, 0.0) + weight * p
        ranked = sorted(groups.items(), key=lambda g: -sum(w for w, _ in g[1]))
        actions.append(ranked[0][0])
        after = [
            {model.chain.labels[s.prev] for _, s in members if s.prev is not None}
            for _, members in ranked
        ]
        # The years just experienced explain the split only when each leads to a single choice.
        telling = sum(len(years) for years in after) == len(set().union(*after))
        choices = []
        for (action, members), years in zip(ranked, after):
            share = sum(w for w, _ in members)
            typical = max(members, key=lambda m: m[0])[1]
            choice = model.summary(typical, action)
            choice["expectedUsdPerAcre"] = round(
                sum(w * model.expected(s, action) for w, s in members) / share, 2
            )
            if len(ranked) > 1:
                choice["probability"] = round(share, 3)
                if telling:
                    choice["afterYears"] = sorted(years)
            choices.append(choice)
        steps.append(
            {"year": year, **choices[0]}
            if len(choices) == 1
            else {"year": year, "choices": choices}
        )
        frontier = following
    return Plan(total, tuple(actions), tuple(steps), method)


def _solve(model: RotationModel, start: State) -> dict:
    """Backward induction over the states reachable from `start`: {state key: (value, _, action)}."""
    best: dict = {}

    def value(state: State) -> float:
        if model.terminal(state):
            return 0.0
        key = model.key(state)
        if key not in best:
            last = state.t + 1 >= model.horizon
            options = []
            for i, action in enumerate(model.actions(state)):
                worth = model.expected(state, action)
                if not last:
                    worth += sum(p * value(s) for p, s in successors(model, state, action))
                options.append((worth, -i, action))
            best[key] = max(options, key=lambda o: o[:2])
        return best[key][0]

    value(start)
    return best


def exact_plan(model: RotationModel) -> Plan:
    """The optimum: the best action in every state, reacting to the year just experienced."""
    best = _solve(model, model.initial_state)
    return evaluate(model, lambda s: best[model.key(s)][2], "dynamic_programming")


def open_loop_plan(model: RotationModel) -> Plan:
    """The best sequence fixed in advance. Equal to `exact_plan` when years are independent."""
    best = _solve(model, model.open_loop_state)
    sequence, state = [], model.open_loop_state
    while not model.terminal(state):
        sequence.append(best[model.key(state)][2])
        state = model.transition(state, sequence[-1])
    return evaluate(model, lambda s: sequence[s.t], "dynamic_programming_fixed_sequence")


def q_learning(
    model: RotationModel,
    episodes: int = 20000,
    alpha: float = 0.1,
    epsilon: float = 0.2,
    seed: int = 0,
) -> tuple[Plan, dict]:
    """Tabular Q-learning on sampled years. Returns the greedy plan and the Q table.

    The agent only sees sampled rewards and the year just experienced; the returned plan is then
    scored with `evaluate` so it can be compared with the exact plan.
    """
    env, rng = RotationEnv(model, seed=seed), Random(seed)
    q: dict = {}

    def row(state: State) -> dict:
        key = model.key(state)
        if key not in q:
            q[key] = {a: 0.0 for a in model.actions(state)}
        return q[key]

    for episode in range(episodes):
        env.reset()
        rate = epsilon * (1.0 - episode / episodes)
        while not model.terminal(env.state):
            values = row(env.state)
            if rng.random() < rate:
                action = rng.choice(list(values))
            else:
                action = max(values, key=values.get)
            _, reward, done, _, _ = env.step(action)
            target = reward + (0.0 if done else max(row(env.state).values()))
            values[action] += alpha * (target - values[action])

    def greedy(state: State) -> Action:
        values = row(state)
        return max(values, key=values.get)

    return evaluate(model, greedy, "q_learning"), q


def fixed_rotation(model: RotationModel, crops: tuple[str, ...], tillage: str, cover: str) -> Plan:
    """A repeating crop sequence with one tillage system; cover crop where it is allowed."""

    def policy(state: State) -> Action:
        crop = crops[state.t % len(crops)]
        allowed = [a for a in model.actions(state) if a.crop == crop]
        exact = [a for a in allowed if a.tillage == tillage and a.cover == cover]
        same_tillage = [a for a in allowed if a.tillage == tillage and a.cover == "none"]
        return (exact or same_tillage or allowed)[0]

    return evaluate(model, policy, "fixed:" + "-".join(crops) + f"/{tillage}/{cover}")


def myopic(model: RotationModel) -> Plan:
    """Best expected reward for the coming year only, year after year."""
    return evaluate(
        model,
        lambda s: max(model.actions(s), key=lambda a: model.expected(s, a)),
        "myopic",
    )
