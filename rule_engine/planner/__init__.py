"""Multi-year rotation planner on top of the rule engine.

    from rule_engine import build_advisor
    from rule_engine.planner import build_context, RotationModel, RotationEnv, exact_plan

    advisor = build_advisor()
    context = build_context(field, advisor, summary_roots=[...])
    model = RotationModel(context, advisor, horizon=5)
    plan = exact_plan(model)            # reference optimum (reacts to the year just experienced)
    fixed = open_loop_plan(model)       # best sequence fixed in advance
    env = RotationEnv(model, seed=0)    # for learning agents

See model.py for the state, action and reward definitions.
"""

from rule_engine.planner.chance import Persistence, YearChain
from rule_engine.planner.context import (
    FieldContext,
    build_context,
    read_fields,
    state_reference_aws,
)
from rule_engine.planner.dynamics import Action, SoilCarbon, State
from rule_engine.planner.env import RotationEnv
from rule_engine.planner.model import RotationModel, Weights
from rule_engine.planner.solve import (
    Plan,
    evaluate,
    exact_plan,
    fixed_rotation,
    myopic,
    open_loop_plan,
    q_learning,
)

__all__ = [
    "Action",
    "FieldContext",
    "Persistence",
    "Plan",
    "RotationEnv",
    "RotationModel",
    "SoilCarbon",
    "State",
    "Weights",
    "YearChain",
    "build_context",
    "evaluate",
    "exact_plan",
    "fixed_rotation",
    "myopic",
    "open_loop_plan",
    "q_learning",
    "read_fields",
    "state_reference_aws",
]
