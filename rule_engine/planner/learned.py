"""Loading a trained policy for serving a plan, without making torch a requirement.

`load_policy(path)` returns `(policy, None)` or `(None, code)`. A policy only fits the crop
list and observation it was trained with (`tabular.ACTIONS`, `ppo.encode`): one trained before
a crop was added to `tables.CROPS` is refused instead of being read with shifted inputs.
"""

from pathlib import Path

NO_FILE = "no_policy_file"
NO_TORCH = "torch_not_installed"
NO_FIT = "policy_does_not_fit"


def observation_size() -> int:
    """Length of the vector the network reads for one state."""
    import torch

    from rule_engine.planner.ppo import N_ACTIONS, encode
    from rule_engine.planner.tabular import CROPS, HISTORY, STATIC_NAMES

    statics = torch.zeros(1, 2 * len(STATIC_NAMES) + 3 * len(CROPS))
    obs = encode(
        torch.zeros(1, N_ACTIONS),
        torch.zeros(1, N_ACTIONS, dtype=torch.bool),
        torch.tensor([1]),
        torch.zeros(1, HISTORY, dtype=torch.long),
        torch.zeros(1, 2),
        statics,
    )
    return int(obs.shape[1])


def load_policy(path: Path | str | None):
    """(LearnedPolicy, None), or (None, why it cannot be used)."""
    if path is None or not Path(path).is_file():
        return None, NO_FILE
    try:
        import torch  # noqa: F401
    except ModuleNotFoundError:
        return None, NO_TORCH
    from rule_engine.planner.ppo import N_ACTIONS, LearnedPolicy
    from rule_engine.planner.tabular import CROPS

    try:
        policy = LearnedPolicy.load(path)
    except (RuntimeError, KeyError):  # another network shape, or not a policy file
        return None, NO_FIT
    net = policy.net
    if policy.crops is not None and policy.crops != CROPS:  # same count, another order
        return None, NO_FIT
    if net.body[0].in_features != observation_size() or net.policy.out_features != N_ACTIONS:
        return None, NO_FIT
    return policy, None
