"""Declarative rule set: YAML loading, validation and condition evaluation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from rule_engine.catalog import Catalog, Crop

DEFAULT_RULES = Path(__file__).resolve().parent / "data" / "rules"
CATEGORIES = (
    "pest_disease",
    "soil_nutrient",
    "erosion",
    "water",
    "temperature",
    "diversity",
    "yield",
    "market",
    "weed",
)
OPERATORS = ("eq", "ne", "gt", "ge", "lt", "le", "in", "not_in", "contains", "is_null", "not_null")
LEVELS = ("low", "medium", "high")
EVIDENCE = ("strong", "moderate", "weak")
KINDS = ("risk", "benefit", "advisory")
KNOWN_FACT_PREFIXES = ("candidate.", "history.", "county.", "field.", "herbicide.")
HAZARD_METRICS = (
    "tmax_max",
    "tmin_min",
    "pr_mm",
    "eto_mm",
    "rz_pctl_min",
    "rz_pctl_mean",
    "dm_max",
    "eddi_max",
    "tmax_ge35_days",
    "tmax_ge30_days",
    "tmin_le0_days",
    "tmin_lem2_days",
    "pr_ge25_days",
    "rz_lt20_days",
)
STAGES = ("planted", "emerged", "flowering", "grain_fill", "mature", "harvested")


class RuleError(ValueError):
    pass


@dataclass(frozen=True)
class Condition:
    fact: str
    op: str
    value: Any = None


@dataclass(frozen=True)
class Hazard:
    stage: str
    window_days: tuple[int, int]
    metric: str
    threshold: float
    aggregate: Literal["sum", "min", "max"]
    compare: Literal["ge", "le"]


@dataclass(frozen=True)
class Effect:
    kind: str
    level: str | None = None
    level_bands: dict[str, float] | None = None
    yield_factor: tuple[float, float] | None = None


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    category: str
    applies_to: dict[str, tuple[str, ...]]
    when: tuple[Condition, ...]
    hazard: Hazard | None
    # the rule is suppressed when all of these hold; a missing fact never suppresses it
    unless: tuple[Condition, ...]
    effect: Effect
    evidence_strength: str
    sources: tuple[str, ...]
    needs_local_review: bool
    uses_traits: tuple[str, ...]


@dataclass(frozen=True)
class RuleSet:
    rules: tuple[Rule, ...]
    version: str


def _condition(raw, rule_id) -> Condition:
    fact, op = raw.get("fact"), raw.get("op")
    if not isinstance(fact, str) or not fact.startswith(KNOWN_FACT_PREFIXES):
        raise RuleError(f"{rule_id}: unknown fact {fact!r}")
    if op not in OPERATORS:
        raise RuleError(f"{rule_id}: unknown operator {op!r}")
    if op in ("is_null", "not_null") and "value" in raw:
        raise RuleError(f"{rule_id}: {op} takes no value")
    if op in ("in", "not_in") and not isinstance(raw.get("value"), list):
        raise RuleError(f"{rule_id}: {op} needs a list value")
    return Condition(fact=fact, op=op, value=raw.get("value"))


def _hazard(raw, rule_id) -> Hazard:
    if raw["stage"] not in STAGES:
        raise RuleError(f"{rule_id}: unknown stage {raw['stage']!r}")
    if raw["metric"] not in HAZARD_METRICS:
        raise RuleError(f"{rule_id}: unknown hazard metric {raw['metric']!r}")
    if raw["aggregate"] not in ("sum", "min", "max") or raw["compare"] not in ("ge", "le"):
        raise RuleError(f"{rule_id}: hazard aggregate/compare invalid")
    start, end = raw["window_days"]
    return Hazard(
        stage=raw["stage"],
        window_days=(int(start), int(end)),
        metric=raw["metric"],
        threshold=float(raw["threshold"]),
        aggregate=raw["aggregate"],
        compare=raw["compare"],
    )


def _effect(raw, rule_id, timed: bool) -> Effect:
    if raw.get("kind") not in KINDS:
        raise RuleError(f"{rule_id}: effect kind must be one of {KINDS}")
    level, bands = raw.get("level"), raw.get("level_bands")
    if level is not None and level not in LEVELS:
        raise RuleError(f"{rule_id}: unknown level {level!r}")
    if bands is not None and (set(bands) != set(LEVELS)):
        raise RuleError(f"{rule_id}: level_bands must define low, medium and high")
    if raw["kind"] == "risk" and not (level or bands):
        raise RuleError(f"{rule_id}: a risk needs a level or level_bands")
    if timed and raw["kind"] == "risk" and not bands:
        raise RuleError(f"{rule_id}: a timed hazard needs level_bands")
    factor = raw.get("yield_factor")
    if factor is not None:
        low, high = factor
        if not (0 < float(low) <= float(high)):
            raise RuleError(f"{rule_id}: yield_factor must be 0 < low <= high")
        factor = (float(low), float(high))
    return Effect(
        kind=raw["kind"],
        level=level,
        level_bands={k: float(v) for k, v in bands.items()} if bands else None,
        yield_factor=factor,
    )


def _rule(raw) -> Rule:
    rule_id = raw.get("id")
    if not rule_id:
        raise RuleError("rule without id")
    if raw.get("category") not in CATEGORIES:
        raise RuleError(f"{rule_id}: unknown category {raw.get('category')!r}")
    if raw.get("evidence_strength") not in EVIDENCE:
        raise RuleError(f"{rule_id}: unknown evidence_strength")
    applies = raw.get("applies_to") or {}
    if set(applies) - {"crops", "groups", "traits", "except_crops"} or not (
        set(applies) - {"except_crops"}
    ):
        raise RuleError(f"{rule_id}: applies_to needs crops, groups and/or traits")
    hazard = _hazard(raw["hazard"], rule_id) if "hazard" in raw else None
    when = tuple(_condition(c, rule_id) for c in raw.get("when") or ())
    unless = tuple(_condition(c, rule_id) for c in raw.get("unless") or ())
    if hazard is not None and when:
        raise RuleError(f"{rule_id}: a hazard rule takes unless, not when")
    if any(c.op in ("is_null", "not_null") for c in unless):
        raise RuleError(f"{rule_id}: unless conditions must test a known value")
    if "explanation" in raw:
        raise RuleError(f"{rule_id}: prose explanations are not part of the rule format")
    if hazard is None and not when:
        raise RuleError(f"{rule_id}: needs a when block or a hazard")
    return Rule(
        id=rule_id,
        title=raw["title"],
        category=raw["category"],
        applies_to={key: tuple(values) for key, values in applies.items()},
        when=when,
        hazard=hazard,
        unless=unless,
        effect=_effect(raw["effect"], rule_id, hazard is not None),
        evidence_strength=raw["evidence_strength"],
        sources=tuple(raw.get("sources") or ()),
        needs_local_review=bool(raw.get("needs_local_review", False)),
        uses_traits=tuple(raw.get("uses_traits") or ()),
    )


def load_rules(folder: Path = DEFAULT_RULES) -> RuleSet:
    rules: list[Rule] = []
    versions = set()
    for path in sorted(Path(folder).glob("*.yaml")):
        document = yaml.safe_load(path.read_text()) or {}
        versions.add(str(document.get("version", "unversioned")))
        rules.extend(_rule(raw) for raw in document.get("rules") or ())
    seen = set()
    for rule in rules:
        if rule.id in seen:
            raise RuleError(f"duplicate rule id {rule.id}")
        seen.add(rule.id)
    return RuleSet(rules=tuple(rules), version="+".join(sorted(versions)))


def _trait_selector(crop: Crop, selector: str) -> bool:
    for op in ("~", ">=", "<=", "!=", "=", ">", "<"):
        if op in selector:
            name, raw = selector.split(op, 1)
            actual = crop.value(name.strip())
            expected = yaml.safe_load(raw.strip())
            if op == "~":
                return isinstance(actual, (list, tuple)) and expected in actual
            if actual is None:
                return False
            return _compare(
                {"=": "eq", "!=": "ne", ">": "gt", "<": "lt", ">=": "ge", "<=": "le"}[op],
                actual,
                expected,
            )
    raise RuleError(f"bad trait selector {selector!r}")


def applies(rule: Rule, crop: Crop, catalog: Catalog) -> bool:
    if crop.id in rule.applies_to.get("except_crops", ()):
        return False
    if crop.id in rule.applies_to.get("crops", ()):
        return True
    if crop.group.id in rule.applies_to.get("groups", ()):
        return True
    return any(_trait_selector(crop, s) for s in rule.applies_to.get("traits", ()))


def _compare(op, actual, expected) -> bool:
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if actual is None or expected is None:
        return False
    if isinstance(actual, bool) or isinstance(actual, str):
        return False
    return {
        "gt": actual > expected,
        "ge": actual >= expected,
        "lt": actual < expected,
        "le": actual <= expected,
    }[op]


def _resolve(value, facts):
    if isinstance(value, str) and value.startswith("@"):
        return facts.get(value[1:])
    return value


def check(condition: Condition, facts: dict) -> tuple[bool, Any, Any]:
    """(holds, actual, expected) for one condition; expected has @fact references resolved."""
    present = condition.fact in facts
    actual = facts.get(condition.fact)
    expected = _resolve(condition.value, facts)
    if condition.op == "is_null":
        ok = actual is None
    elif condition.op == "not_null":
        ok = actual is not None
    elif not present:
        ok = False
    elif condition.op == "in":
        ok = actual in expected
    elif condition.op == "not_in":
        ok = actual not in expected
    elif condition.op == "contains":
        ok = isinstance(actual, (list, tuple, set)) and expected in actual
    else:
        ok = _compare(condition.op, actual, expected)
    return ok, actual, expected


def evaluate(conditions, facts: dict) -> bool:
    return all(check(condition, facts)[0] for condition in conditions)
