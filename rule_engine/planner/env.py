"""Gymnasium-shaped environment over RotationModel (reset / step), with no extra dependency.

    env = RotationEnv(model, seed=0)
    observation, info = env.reset()
    observation, reward, terminated, truncated, info = env.step(action_index)

Actions are indices into `env.actions` (model.all_actions). `info["validActions"]` lists the
indices allowed in the current state; stepping with any other index raises ValueError.
The year drawn at each step follows the model's year odds, which depend on the year before.
"""

from random import Random

from rule_engine.planner.dynamics import Action, State
from rule_engine.planner.model import RotationModel


class RotationEnv:
    def __init__(self, model: RotationModel, seed: int | None = None):
        self.model = model
        self.actions: list[Action] = model.all_actions
        self._index = {action: i for i, action in enumerate(self.actions)}
        self.rng = Random(seed)
        self.state: State = model.initial_state

    def observation(self) -> dict:
        state = self.state
        return {
            "year": state.t,
            "history": list(state.history),
            "stableCarbonTHa": None if state.old is None else round(state.stable_carbon, 2),
            "lastYear": self._last_year(state),
        }

    def _last_year(self, state: State) -> dict | None:
        """What the agent knows about the year just experienced: the carry-over signals."""
        chain = self.model.chain
        if chain is None or state.prev is None:
            return None
        year = chain.labels[state.prev]
        return {"index": state.prev, "year": year, **{k: chain.end[year][k] for k in chain.signals}}

    def valid_actions(self) -> list[int]:
        return [self._index[a] for a in self.model.actions(self.state)]

    def _info(self) -> dict:
        return {"validActions": [] if self.model.terminal(self.state) else self.valid_actions()}

    def reset(self, seed: int | None = None) -> tuple[dict, dict]:
        if seed is not None:
            self.rng = Random(seed)
        self.state = self.model.initial_state
        return self.observation(), self._info()

    def step(self, action: int | Action) -> tuple[dict, float, bool, bool, dict]:
        if self.model.terminal(self.state):
            raise ValueError("episode is over; call reset()")
        chosen = action if isinstance(action, Action) else self.actions[action]
        if chosen not in self.model.actions(self.state):
            raise ValueError(f"{chosen.label()} is not valid in this state")
        odds = self.model.distribution(self.state)
        year_index = self.rng.choices(range(len(odds)), weights=odds)[0]
        outcome = self.model.outcome(self.state, chosen, year_index)
        self.state = self.model.transition(self.state, chosen, year_index)
        info = self._info()
        info["outcome"] = outcome
        return self.observation(), outcome.reward, self.model.terminal(self.state), False, info
