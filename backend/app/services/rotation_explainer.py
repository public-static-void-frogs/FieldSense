"""Build assistant explanations from the rotation engine's results and rule references."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rule_engine.rules import RuleSet


TOPICS = ("why", "method", "sources")
FINDING_GROUPS = ("risks", "benefits", "advisories")


def explanation_topics(args: dict) -> tuple[str, ...]:
    requested = args.get("explain")
    if not isinstance(requested, list):
        return ()
    return tuple(topic for topic in TOPICS if topic in requested)


def rule_index(rules: RuleSet) -> dict[str, tuple[str, ...]]:
    return {rule.id: rule.sources for rule in rules.rules}


def _candidate_explanation(candidate: dict | None) -> dict | None:
    if candidate is None:
        return None

    result = {
        key: candidate[key]
        for key in ("crop", "label", "rank", "score", "scoreBreakdown", "dataGaps")
    }
    for group in FINDING_GROUPS:
        result[group] = [
            {
                **finding,
                # Keep threshold and season counts without sending every season to the model.
                "trigger": {
                    key: value
                    for key, value in (finding.get("trigger") or {}).items()
                    if key != "perSeason"
                },
            }
            for finding in candidate[group]
        ]
    return result


def _sources(advice: dict, candidates: list[dict], rules: dict[str, tuple[str, ...]]) -> dict:
    data = []
    history_kind = (advice.get("historySource") or {}).get("kind")
    if history_kind == "cdl":
        data.append("USDA NASS Cropland Data Layer (satellite-estimated crop history)")
    if history_kind == "declared":
        data.append("Farmer-declared crop history")
    if advice.get("seasonsAvailable"):
        data.append("Field season summaries")
    if weather_source := (advice.get("weatherRecord") or {}).get("source"):
        data.append(weather_source)

    references = {}
    for candidate in candidates:
        for group in FINDING_GROUPS:
            for finding in candidate[group]:
                rule_id = finding["ruleId"]
                if sources := rules.get(rule_id):
                    references[rule_id] = list(sources)
    return {
        "data": data,
        "projectDocuments": ["rule_engine/README.md", "rule_engine/data/rules/README.md"],
        "ruleReferences": references,
    }


def explain(advice: dict, topics: tuple[str, ...], rules: dict[str, tuple[str, ...]]) -> dict:
    candidates = advice["candidates"]
    recommended = next(iter(candidates), None)
    intended = next((candidate for candidate in candidates if candidate["isIntended"]), None)
    result = {}

    if "why" in topics:
        result["why"] = {
            "recommended": _candidate_explanation(recommended),
            "intended": _candidate_explanation(intended),
            "historySource": advice.get("historySource"),
            "history": advice.get("history", []),
            "seasonsAvailable": advice.get("seasonsAvailable", []),
            "weatherRecord": advice.get("weatherRecord"),
            "dataGaps": advice.get("dataGaps", []),
        }
    if "method" in topics:
        result["method"] = {
            "steps": [
                "Evaluate applicable rules against the field and crop facts. Count historical "
                "threshold crossings for weather hazards when observations are available.",
                "Add risk points, subtract benefit points, and apply the selected priority "
                "weights. Advisories carry zero points. The income priority can subtract "
                "points based on gross revenue rank.",
                "Rank crops by ascending score and apply the engine's tie-break order.",
            ],
            "priorities": advice.get("priorities", []),
            "scoring": advice.get("scoring", {}),
            "limits": [
                "The score ranks relative risk. Yield and gross revenue are estimates and "
                "gross revenue excludes input costs.",
                "Missing field data can prevent some rules from being evaluated.",
            ],
            "dataGaps": advice.get("dataGaps", []),
        }
    if "sources" in topics:
        compared = [candidate for candidate in (recommended, intended) if candidate is not None]
        result["sources"] = _sources(advice, compared, rules)
    return result
