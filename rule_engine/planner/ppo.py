"""One rotation policy for all fields, trained with PPO on the tabulated fields (tabular.py).

The policy sees, for the field and the moment of the decision:

- the rule engine's expected reward of each allowed action for the coming year (what a
  year-by-year advisor would rank by), in absolute terms and relative to the best one;
- which actions are allowed;
- the last five crops, the years left in the plan;
- the carry-over signals of the year just experienced (drought class, price level);
- the field's soil, position and per-crop expected yield and price.

It has to learn what the one-year score misses: what each choice does to the following years.
Invalid actions are masked in the policy (logits set to -inf), the standard masked-PPO scheme.

Requires PyTorch; nothing else in the planner imports this module.
"""

import zlib
from dataclasses import dataclass

import numpy as np
import torch
from torch import nn

from rule_engine.planner.dynamics import Action, State
from rule_engine.planner.model import RotationModel
from rule_engine.planner.tabular import (
    ACTION_INDEX,
    ACTIONS,
    CROPS,
    HISTORY,
    LOCAL,
    MAX_YEARS,
    SLOT,
    SUB,
    FieldTable,
    field_statics,
    myopic_choice,
    score,
    tokens,
    year_signals,
)

REWARD_SCALE = 300.0  # USD/acre per unit of network input and return
MAX_HORIZON = 8
N_ACTIONS = len(ACTIONS)


def is_test_county(county: str, share: int = 10) -> bool:
    """Whole counties are held out, so test fields are in places the policy never trained on."""
    return zlib.crc32(county.encode()) % share == 0


def encode(expected, mask, remaining, history, signal, statics) -> torch.Tensor:
    """Network input. expected [B, A] USD/acre, mask [B, A] bool, remaining [B] years left
    (including this one), history [B, HISTORY] tokens, signal [B, 2], statics [B, S]."""
    valid = mask.float()
    scaled = torch.where(mask, expected, torch.zeros_like(expected)) / REWARD_SCALE
    best = torch.where(mask, expected, torch.full_like(expected, -1e9)).max(dim=1, keepdim=True)
    relative = torch.where(mask, expected - best.values, torch.zeros_like(expected)) / REWARD_SCALE
    left = nn.functional.one_hot(remaining.long().clamp(0, MAX_HORIZON), MAX_HORIZON + 1).float()
    crops = nn.functional.one_hot(history.long(), len(CROPS) + 1).float().flatten(1)
    return torch.cat([scaled, relative, valid, left, crops, signal, statics], dim=1)


class PolicyNet(nn.Module):
    def __init__(self, inputs: int, hidden: int = 256):
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(inputs, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU()
        )
        self.policy = nn.Linear(hidden, N_ACTIONS)
        self.value = nn.Linear(hidden, 1)

    def forward(self, obs: torch.Tensor, mask: torch.Tensor):
        hidden = self.body(obs)
        logits = self.policy(hidden).masked_fill(~mask, -1e9)
        return logits, self.value(hidden).squeeze(-1)


class FieldSet:
    """Many FieldTables concatenated, with global node indices.

    The per-node arrays stay in main memory (they are large and only a batch is read at a time);
    the per-field arrays and the network live on `device`.
    """

    def __init__(self, tables: list[FieldTable], device: str = "cpu"):
        self.tables = tables
        self.device = device
        offsets = np.cumsum([0] + [t.nodes for t in tables])
        self.total = int(offsets[-1])
        self.root_cpu = torch.as_tensor(offsets[:-1])
        self.scale = torch.empty((self.total, LOCAL), dtype=torch.float32)
        self.fixed = torch.empty((self.total, LOCAL), dtype=torch.float32)
        self.mask = torch.empty((self.total, LOCAL), dtype=torch.bool)
        self.next_node = torch.empty((self.total, tables[0].next_node.shape[1]), dtype=torch.int32)
        self.node_t = torch.empty(self.total, dtype=torch.int8)
        self.node_history = torch.empty((self.total, HISTORY), dtype=torch.int8)
        self.node_field = torch.empty(self.total, dtype=torch.int32)
        for i, (table, start) in enumerate(zip(tables, offsets)):
            rows = slice(int(start), int(start) + table.nodes)
            self.scale[rows] = torch.from_numpy(table.scale)
            self.fixed[rows] = torch.from_numpy(table.fixed)
            self.mask[rows] = torch.from_numpy(table.mask)
            self.next_node[rows] = torch.from_numpy(
                np.where(table.next_node >= 0, table.next_node + start, -1).astype(np.int32)
            )
            self.node_t[rows] = torch.from_numpy(table.node_t.astype(np.int8))
            self.node_history[rows] = torch.from_numpy(table.node_history)
            self.node_field[rows] = i

        def stack(parts, dtype):
            return torch.as_tensor(np.stack(parts), dtype=dtype, device=device)

        self.gain = stack([t.gain for t in tables], torch.float32)  # [field, slot, year]
        self.weather = stack([t.weather for t in tables], torch.float32)
        self.odds = stack([t.odds for t in tables], torch.float32)
        self.signals = stack([t.signals for t in tables], torch.float32)
        self.statics = stack([t.statics for t in tables], torch.float32)
        self.first = torch.as_tensor([t.first for t in tables], device=device)
        self.horizon = torch.as_tensor([t.horizon for t in tables], device=device)
        # expected gain and weather term of the coming year: [field, year just experienced, slot]
        self.gain_ahead = torch.einsum("fpy,fsy->fps", self.odds, self.gain)
        self.weather_ahead = torch.einsum("fpy,fsy->fps", self.odds, self.weather)
        crops = stack([t.crops for t in tables], torch.long)  # [field, slot], -1 unused
        slot = torch.as_tensor(SLOT, device=device)
        within = torch.arange(LOCAL, device=device) % SUB
        # local action -> global action; unused slots point at a spare column that is dropped
        self.to_global = torch.where(crops >= 0, crops, len(CROPS))[:, slot] * SUB + within
        self.slot_of_crop = torch.full((len(tables), len(CROPS) + 1), 0, device=device)
        self.slot_of_crop.scatter_(
            1, torch.where(crops >= 0, crops, len(CROPS)), slot[::SUB].expand_as(crops)
        )
        self.slot = slot

    def __len__(self) -> int:
        return len(self.tables)

    def observe(self, node: torch.Tensor, prev: torch.Tensor):
        """(network input, global action mask) for decisions at `node` (a CPU index tensor)
        after year `prev` (on the device)."""
        device = self.device
        field = self.node_field[node].long().to(device)
        scale, fixed = self.scale[node].to(device), self.fixed[node].to(device)
        local_mask = self.mask[node].to(device)
        ahead = self.gain_ahead[field, prev][:, self.slot]
        expected_local = scale * ahead + fixed + self.weather_ahead[field, prev][:, self.slot]
        index = self.to_global[field]
        expected = torch.zeros((len(node), N_ACTIONS + SUB), device=device)
        mask = torch.zeros((len(node), N_ACTIONS + SUB), dtype=torch.bool, device=device)
        expected.scatter_(1, index, expected_local)
        mask.scatter_(1, index, local_mask)
        expected, mask = expected[:, :N_ACTIONS], mask[:, :N_ACTIONS]
        obs = encode(
            expected,
            mask,
            self.horizon[field] - self.node_t[node].to(device),
            self.node_history[node].to(device),
            self.signals[field, prev],
            self.statics[field],
        )
        return obs, mask

    def local_action(self, node: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        """Global action index (device) -> the field's local action index (device)."""
        field = self.node_field[node].long().to(self.device)
        return self.slot_of_crop[field, action // SUB] * SUB + action % SUB

    def step(self, node: torch.Tensor, action: torch.Tensor, year: torch.Tensor):
        """(reward in USD/acre on the device, next node on the CPU) of global `action` in `year`."""
        local = self.local_action(node, action)
        local_cpu = local.cpu()
        field = self.node_field[node].long().to(self.device)
        slot = local // SUB
        scale = self.scale[node, local_cpu].to(self.device)
        fixed = self.fixed[node, local_cpu].to(self.device)
        reward = scale * self.gain[field, slot, year] + fixed + self.weather[field, slot, year]
        return reward, self.next_node[node, local_cpu // SUB].long().clamp(min=0)

    @property
    def inputs(self) -> int:
        node = torch.zeros(1, dtype=torch.long)
        return self.observe(node, node.to(self.device))[0].shape[1]


@dataclass
class Config:
    envs: int = 8192
    iterations: int = 400
    epochs: int = 4
    minibatches: int = 8
    lr: float = 3e-4
    clip: float = 0.2
    gae_lambda: float = 0.95
    entropy: float = 0.02
    entropy_end: float = 0.001
    value_weight: float = 0.5
    max_grad_norm: float = 0.5
    hidden: int = 256
    seed: int = 0


def greedy_choices(net: PolicyNet, data: FieldSet, batch: int = 65536) -> list[np.ndarray]:
    """The policy's most likely local action for every [node, year just experienced] of every
    field."""
    years = torch.arange(MAX_YEARS, device=data.device)
    rows = max(1, batch // MAX_YEARS)
    picks = []
    net.eval()
    with torch.no_grad():
        for start in range(0, data.total, rows):
            node = torch.arange(start, min(start + rows, data.total)).repeat_interleave(MAX_YEARS)
            obs, mask = data.observe(node, years.repeat(len(node) // MAX_YEARS))
            action = net(obs, mask)[0].argmax(dim=1)
            picks.append(data.local_action(node, action).view(-1, MAX_YEARS).cpu())
    net.train()
    flat = torch.cat(picks).numpy()
    sizes = np.cumsum([t.nodes for t in data.tables])[:-1]
    return np.split(flat, sizes)


def benchmark(net: PolicyNet, data: FieldSet) -> dict:
    """Exact expected plan value of the learned policy against the optimum and the myopic rule."""
    rows = []
    for table, choice in zip(data.tables, greedy_choices(net, data)):
        best, _ = score(table)
        learned, _ = score(table, choice)
        short, _ = score(table, myopic_choice)
        rows.append((best, learned, short, int((table.crops >= 0).sum())))
    best, learned, short, crops = (np.asarray(c, dtype=np.float64) for c in zip(*rows))
    gap = best - short

    def part(select) -> dict:
        return {
            "fields": int(select.sum()),
            "optimumUsdPerAcre": round(float(best[select].mean()), 1),
            "learnedUsdPerAcre": round(float(learned[select].mean()), 1),
            "myopicUsdPerAcre": round(float(short[select].mean()), 1),
            "gapClosed": round(
                float((learned[select] - short[select]).sum() / max(1e-9, gap[select].sum())), 3
            ),
            "meanRegretUsdPerAcre": round(float((best - learned)[select].mean()), 1),
            "worseThanMyopicShare": round(float((learned < short - 0.5)[select].mean()), 3),
            "within1PctOfOptimumShare": round(
                float(((best - learned) <= 0.01 * np.abs(best) + 0.5)[select].mean()), 3
            ),
        }

    out = part(np.ones(len(rows), dtype=bool))
    out["byCropCount"] = {str(n): part(crops == n) for n in sorted(set(crops.astype(int)))}
    return out


def train(data: FieldSet, config: Config = Config(), watch: FieldSet | None = None, log=print):
    """PPO with action masking over many fields at once. Returns the trained network."""
    torch.manual_seed(config.seed)
    device = data.device
    net = PolicyNet(data.inputs, config.hidden).to(device)
    optimiser = torch.optim.Adam(net.parameters(), lr=config.lr, eps=1e-5)
    horizon = int(data.horizon.max())
    if int(data.horizon.min()) != horizon:
        raise ValueError("all fields must share one horizon")
    for iteration in range(config.iterations):
        progress = iteration / config.iterations
        for group in optimiser.param_groups:
            group["lr"] = config.lr * (1.0 - progress)
        entropy_weight = config.entropy + (config.entropy_end - config.entropy) * progress

        # -- collect one plan per environment ---------------------------------------------
        field = torch.randint(len(data), (config.envs,))
        node = data.root_cpu[field]
        field = field.to(device)
        prev = data.first[field]
        kept = {k: [] for k in ("obs", "mask", "action", "logp", "value", "reward")}
        with torch.no_grad():
            for _ in range(horizon):
                obs, mask = data.observe(node, prev)
                logits, value = net(obs, mask)
                policy = torch.distributions.Categorical(logits=logits)
                action = policy.sample()
                year = torch.multinomial(data.odds[field, prev], 1).squeeze(1)
                reward, following = data.step(node, action, year)
                reward = reward / REWARD_SCALE
                for key, item in zip(
                    kept, (obs, mask, action, policy.log_prob(action), value, reward)
                ):
                    kept[key].append(item)
                node, prev = following, year
        values, rewards = torch.stack(kept["value"]), torch.stack(kept["reward"])
        advantage = torch.zeros_like(rewards)
        running = torch.zeros(config.envs, device=device)
        for t in range(horizon - 1, -1, -1):
            ahead = values[t + 1] if t + 1 < horizon else torch.zeros_like(running)
            delta = rewards[t] + ahead - values[t]
            running = delta + config.gae_lambda * running
            advantage[t] = running
        returns = (advantage + values).flatten()
        advantage = advantage.flatten()
        obs, mask = torch.cat(kept["obs"]), torch.cat(kept["mask"])
        action, old_logp = torch.cat(kept["action"]), torch.cat(kept["logp"])

        # -- update -----------------------------------------------------------------------
        size = len(action)
        for _ in range(config.epochs):
            for index in torch.randperm(size, device=device).chunk(config.minibatches):
                logits, value = net(obs[index], mask[index])
                policy = torch.distributions.Categorical(logits=logits)
                ratio = (policy.log_prob(action[index]) - old_logp[index]).exp()
                adv = advantage[index]
                adv = (adv - adv.mean()) / (adv.std() + 1e-8)
                clipped = ratio.clamp(1.0 - config.clip, 1.0 + config.clip)
                loss = (
                    -torch.min(ratio * adv, clipped * adv).mean()
                    + config.value_weight * (value - returns[index]).pow(2).mean()
                    - entropy_weight * policy.entropy().mean()
                )
                optimiser.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), config.max_grad_norm)
                optimiser.step()
        if log and (iteration % 25 == 0 or iteration == config.iterations - 1):
            line = (
                f"iteration {iteration}: sampled return {rewards.sum(0).mean() * REWARD_SCALE:.0f}"
            )
            if watch is not None:
                seen = benchmark(net, watch)
                line += (
                    f" | held-out learned {seen['learnedUsdPerAcre']} of optimum"
                    f" {seen['optimumUsdPerAcre']}, myopic {seen['myopicUsdPerAcre']},"
                    f" gap closed {seen['gapClosed']}"
                )
            log(line)
    return net


class LearnedPolicy:
    """A trained network as a policy for RotationModel: `evaluate(model, policy.act_for(model))`."""

    def __init__(self, net: PolicyNet, device: str = "cpu"):
        self.net, self.device = net.to(device).eval(), device
        self.crops: tuple[str, ...] | None = CROPS  # the crop order it was trained with

    def save(self, path) -> None:
        inputs = self.net.body[0].in_features
        hidden = self.net.body[0].out_features
        saved = {"state": self.net.state_dict(), "inputs": inputs, "hidden": hidden}
        torch.save(saved | {"crops": list(CROPS)}, path)  # the crop order the network reads

    @classmethod
    def load(cls, path, device: str = "cpu") -> "LearnedPolicy":
        saved = torch.load(path, map_location=device, weights_only=True)
        net = PolicyNet(saved["inputs"], saved["hidden"])
        net.load_state_dict(saved["state"])
        policy = cls(net, device)
        policy.crops = tuple(saved["crops"]) if "crops" in saved else None
        return policy

    def act_for(self, model: RotationModel):
        """state -> Action, for a field the network may never have seen."""
        statics = torch.as_tensor(field_statics(model))[None]
        signals = torch.as_tensor(year_signals(model))

        def act(state: State) -> Action:
            expected = torch.zeros(1, N_ACTIONS)
            mask = torch.zeros(1, N_ACTIONS, dtype=torch.bool)
            for action in model.actions(state):
                index = ACTION_INDEX.get(action)
                if index is not None:
                    expected[0, index] = model.expected(state, action)
                    mask[0, index] = True
            signal = signals[state.prev if state.prev is not None else 0][None]
            obs = encode(
                expected,
                mask,
                torch.tensor([model.horizon - state.t]),
                torch.tensor([tokens(state.history)]),
                signal,
                statics,
            )
            with torch.no_grad():
                logits, _ = self.net(obs.to(self.device), mask.to(self.device))
            return ACTIONS[int(logits.argmax(dim=1))]

        return act


assert HISTORY == 5  # the history one-hot width is part of the saved network's input size
