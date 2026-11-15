"""Explains a rotation recommendation: why it ranks where it does, what it rests on, how the
algorithm works and where to read more.

This sits on top of ``rotation_advice.RotationAdvice``: it only reshapes the engine's own result
(scores, findings, triggers, data gaps) and the rule sources that the rule files already carry.
It adds no agronomic logic and changes no score. The assistant turns the structured output into
wording.
"""

TRIGGER_KEYS = (
    "stage",
    "window",
    "metric",
    "metricUnit",
    "aggregate",
    "compare",
    "threshold",
    "seasonsHit",
    "seasonsTotal",
    "share",
    "worstYear",
    "worstValue",
    "levelCapped",
    "levelBasis",
    "lossWhenHit",
    "expectedLoss",
    "record",
)
COMPARED_FINDINGS = 4
LISTED_FINDINGS = 6

# How the engine works, in the order it runs. The numbers are filled from the result's own
# ``scoring`` block, so the text cannot drift from the weights actually used.
METHOD_STEPS = (
    "The field's crop history (the last few seasons) is read. Mostly it is the USDA Cropland "
    "Data Layer, a satellite classification and not a farmer record; a declared crop is used "
    "when there is no history.",
    "Every candidate crop for the state is assessed on its own: the history is read as if that "
    "crop were planted next season.",
    "Declarative rules are checked for each candidate. A rule fires when its conditions on the "
    "crop's traits, the history (for example years in a row of the same crop, or the same crop "
    "family returning too soon), the county and the field's soil or declared practices hold.",
    "Weather rules are evaluated season by season over the long weather record at the field's "
    "location: in how many past seasons the threshold (for example heat at flowering) was "
    "crossed in the crop's sensitive window. A hazard seen in fewer than 1 season in 10 is not "
    "reported. The level is the yield the hazard is expected to cost per season: the share of "
    "seasons hit times the loss in a season it hits, measured in county yields of that crop "
    "(8 % or more is high, 3 % or more is medium). Where that loss is not measured, the share of "
    "seasons alone sets the level and it stops at medium. A hazard rule is skipped where most "
    "of the crop in the county is irrigated.",
    "Each firing rule is a risk, a benefit or an advisory. A risk adds points by level, a "
    "benefit subtracts points, and an advisory adds nothing. Findings in a category the user "
    "prioritised count double.",
    "With the income priority, candidates with a revenue estimate get a bonus from -2 (best "
    "gross revenue) to 0 (worst).",
    "Candidates are ranked by total score, lower is better. Ties go to the intended crop, then "
    "to a candidate with an economic estimate, then to the one with fewer data gaps.",
    "Yield and gross revenue are separate estimates: a county yield trend adjusted by the "
    "yield factors of the firing rules, times a reference price. They do not change the score "
    "unless the income priority is set.",
)
METHOD_LIMITS = (
    "The score measures agronomic risk, not profit. Without priorities, low-input crops such as "
    "hay or pasture can rank first; read the rank among the cash crops or set the income "
    "priority.",
    "Weather rules use past seasons, not a forecast, and the record has no trend correction.",
    "Stage dates are regional medians, and sowing is the only date that can be localised.",
    "Soil, tillage, cover crop and herbicide rules fire only on soil data or practices that are "
    "provided. Soil values are survey map estimates, not a soil test.",
    "Rule thresholds were written for the Corn Belt (Iowa) and are not reviewed for other "
    "regions. Findings marked as needing local review should be checked with a local "
    "agronomist.",
)
# Data sources the engine reads. URLs are the public home pages of the programmes.
DATA_SOURCES = (
    {
        "name": "USDA NASS Cropland Data Layer (CDL)",
        "use": "crop history of the field (satellite classification)",
        "url": "https://www.nass.usda.gov/Research_and_Science/Cropland/",
    },
    {
        "name": "USDA NASS Crop Sequence Boundaries (CSB)",
        "use": "field boundaries and identifiers the crop history is matched to",
        "url": "https://www.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/",
    },
    {
        "name": "gridMET (University of California Merced)",
        "use": "30 seasons of weekly weather at the field's location for the hazard rules",
        "url": "https://www.climatologylab.org/gridmet.html",
    },
    {
        "name": "USDA NASS Quick Stats and Crop Progress",
        "use": "county yields, prices received and the regional dates of sowing and harvest",
        "url": "https://quickstats.nass.usda.gov/",
    },
    {
        "name": "USDA NRCS Soil Data Access (SSURGO)",
        "use": "slope, drainage, water storage and other soil survey estimates",
        "url": "https://sdmdataaccess.nrcs.usda.gov/",
    },
    {
        "name": "NASA SMAP root-zone soil moisture",
        "use": "soil moisture in a field's season summary",
        "url": "https://smap.jpl.nasa.gov/",
    },
    {
        "name": "U.S. Drought Monitor",
        "use": "drought class in a field's season summary",
        "url": "https://droughtmonitor.unl.edu/",
    },
    {
        "name": "USDA RMA",
        "use": "projected prices and county causes of loss (drought, excess moisture, heat)",
        "url": "https://www.rma.usda.gov/",
    },
)
PROJECT_DOCS = (
    "rule_engine/README.md: inputs, output, the off-season slot and the engine's stated limits",
    "rule_engine/data/rules/*.yaml: every rule with its thresholds and its literature sources",
    "rule_engine/data/crops.yaml: crop traits, each with its citation and whether it is verified",
)


def explanation_topics(args: dict) -> set[str]:
    """Which parts the user asked for: ``why``, ``method`` and ``sources``."""
    topics = args.get("explain")
    if isinstance(topics, str):
        topics = [topics]
    return {t for t in topics or [] if t in ("why", "method", "sources")}


def method(scoring: dict | None) -> dict:
    """How the algorithm works, with the weights this result was computed with."""
    scoring = scoring or {}
    return {
        "steps": list(METHOD_STEPS),
        "weights": {
            "riskPointsByLevel": scoring.get("levelWeight"),
            "benefitPoints": scoring.get("benefitPoints"),
            "priorityMultiplier": scoring.get("priorityMultiplier"),
            "priorityCategories": scoring.get("priorityCategories"),
            "incomeBonusMax": scoring.get("incomeBonusMax"),
            "tieBreak": scoring.get("tieBreak"),
            "lowerIsBetter": scoring.get("lowerIsBetter", True),
        },
        "limits": list(METHOD_LIMITS),
    }


def sources(rule_sources: dict[str, dict], used_rule_ids=None) -> dict:
    """Where to read more: the data sources, the project documents and the rules' references."""
    rules = [
        {"ruleId": rule_id, "title": info["title"], "references": info["sources"]}
        for rule_id, info in rule_sources.items()
        if info["sources"] and (used_rule_ids is None or rule_id in used_rule_ids)
    ]
    return {
        "dataSources": list(DATA_SOURCES),
        "projectDocuments": list(PROJECT_DOCS),
        "ruleReferences": rules,
    }


def rule_index(rule_set) -> dict[str, dict]:
    """``ruleId -> {title, sources, evidenceStrength}`` from the engine's loaded rules."""
    index = {}
    for rule in getattr(rule_set, "rules", ()) or ():
        index[rule.id] = {
            "title": rule.title,
            "sources": list(rule.sources),
            "evidenceStrength": rule.evidence_strength,
        }
    return index


def _trigger(trigger: dict | None) -> dict | None:
    """The part of a finding's trigger that says what it was based on."""
    if not trigger:
        return None
    if trigger.get("type") == "conditions":
        return {"type": "conditions", "conditions": trigger.get("conditions")}
    return {"type": "hazard", **{k: trigger[k] for k in TRIGGER_KEYS if k in trigger}}


def _findings(candidate: dict) -> dict[str, dict]:
    return {
        finding["ruleId"]: finding
        for kind in ("risks", "benefits", "advisories")
        for finding in candidate.get(kind, [])
        if finding.get("ruleId")
    }


def _part(entry: dict, findings: dict[str, dict], rules: dict[str, dict]) -> dict:
    """One line of the score: what added or removed points, and what it rests on."""
    if entry.get("source") == "income_rank":
        return {
            "source": "income_rank",
            "points": entry["points"],
            "revenueRank": entry.get("revenueRank"),
            "of": entry.get("of"),
            "basedOn": "gross revenue rank among the candidates that have an estimate",
        }
    finding = findings.get(entry.get("ruleId"), {})
    info = rules.get(entry.get("ruleId"), {})
    part = {
        "ruleId": entry.get("ruleId"),
        "title": finding.get("title") or info.get("title"),
        "kind": entry.get("kind"),
        "level": finding.get("level"),
        "category": finding.get("category"),
        "points": entry["points"],
        "evidenceStrength": finding.get("evidenceStrength") or info.get("evidenceStrength"),
        "needsLocalReview": finding.get("needsLocalReview"),
        "basedOn": _trigger(finding.get("trigger")),
        "references": info.get("sources") or [],
    }
    return {key: value for key, value in part.items() if value not in (None, [])}


def _crop_view(candidate: dict, rules: dict[str, dict], limit: int) -> dict:
    findings = _findings(candidate)
    parts = sorted(
        (_part(entry, findings, rules) for entry in candidate.get("scoreBreakdown", [])),
        key=lambda part: -abs(part["points"]),
    )
    advisories = [
        {"ruleId": f["ruleId"], "title": f.get("title"), "basedOn": _trigger(f.get("trigger"))}
        for f in candidate.get("advisories", [])
    ]
    return {
        "crop": candidate["crop"],
        "label": candidate.get("label"),
        "rank": candidate["rank"],
        "score": candidate["score"],
        "isIntended": candidate.get("isIntended", False),
        "addedRisk": [p for p in parts if p["points"] > 0][:limit],
        "reducedRisk": [p for p in parts if p["points"] < 0][:limit],
        "advisories": advisories[:limit],
        "dataGaps": [gap.get("code") for gap in candidate.get("dataGaps", [])],
    }


def _difference(best: dict, other: dict) -> list[dict]:
    """What separates two candidates: the rules whose points differ, largest gap first."""
    a = {p.get("ruleId") or p["source"]: p for p in best["addedRisk"] + best["reducedRisk"]}
    b = {p.get("ruleId") or p["source"]: p for p in other["addedRisk"] + other["reducedRisk"]}
    rows = []
    for key in a.keys() | b.keys():
        mine, theirs = a.get(key, {}).get("points", 0), b.get(key, {}).get("points", 0)
        if mine != theirs:
            label = (a.get(key) or b.get(key)).get("title") or key
            rows.append(
                {
                    "rule": label,
                    f"{best['crop']}Points": mine,
                    f"{other['crop']}Points": theirs,
                    "gap": round(theirs - mine, 2),
                }
            )
    return sorted(rows, key=lambda row: -abs(row["gap"]))[:COMPARED_FINDINGS]


def why(advice: dict, rules: dict[str, dict]) -> dict:
    """Why the top-ranked crop leads, why the intended crop ranks where it does, and what the
    ranking was based on."""
    candidates = advice.get("candidates", [])
    if not candidates:
        return {"status": "unavailable", "reason": "no candidates were assessed"}
    best = _crop_view(candidates[0], rules, LISTED_FINDINGS)
    intended = next((c for c in candidates if c.get("isIntended")), None)
    result = {
        "recommended": best,
        "intended": None,
        "differenceFromRecommended": [],
        "basedOn": {
            "history": advice.get("historySource"),
            "weatherRecord": advice.get("weatherRecord"),
            "priorities": advice.get("priorities"),
            "region": advice.get("region"),
            "calendarKind": (candidates[0].get("calendar") or {}).get("kind"),
            "yieldMethod": (candidates[0].get("yield") or {}).get("method"),
            "ruleSetVersion": advice.get("ruleSetVersion"),
            "dataGaps": [gap.get("code") for gap in advice.get("dataGaps", [])],
        },
        "reading": (
            "Lower score is better. A score is the sum of rule points, so it measures agronomic "
            "risk and not profit; the list shows which rules added or removed points."
        ),
    }
    if intended and intended["crop"] != best["crop"]:
        view = _crop_view(intended, rules, LISTED_FINDINGS)
        result["intended"] = view
        result["differenceFromRecommended"] = _difference(best, view)
    elif intended:
        result["intended"] = {"crop": intended["crop"], "sameAsRecommended": True}
    return result


def explain(advice: dict, topics: set[str], rules: dict[str, dict]) -> dict:
    """The requested parts of the explanation, as one block to add to the advice result."""
    block = {}
    if "why" in topics:
        block["why"] = why(advice, rules)
    if "method" in topics:
        block["method"] = method(advice.get("scoring"))
    if "sources" in topics:
        used = {
            part["ruleId"]
            for view in (block.get("why") or {}).values()
            if isinstance(view, dict)
            for key in ("addedRisk", "reducedRisk")
            for part in view.get(key, [])
            if "ruleId" in part
        }
        block["sources"] = sources(rules, used or None)
    return block
