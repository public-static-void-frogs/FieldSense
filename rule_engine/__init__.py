"""Crop-rotation rule engine: catalog, declarative rules, reference tables, facts and advisor.

Standalone package (no web framework). Entry point:

    from rule_engine import build_advisor
    advisor = build_advisor(summary_root="../data/local/season_summary")
    result = advisor.advise(field, "corn", ["water"], "imperial")
"""

from pathlib import Path

from rule_engine.catalog import load_catalog
from rule_engine.engine import RotationAdvisor
from rule_engine.reference import load_reference
from rule_engine.rules import load_rules
from rule_engine.summary import ClimateRecordStore, SeasonSummaryStore
from rule_engine.yield_model import CountyTrendYieldModel


def build_advisor(
    summary_root: str | Path | None = None,
    region: str = "IA",
    climate_root: str | Path | None = None,
) -> RotationAdvisor:
    """`climate_root` is the long weather record built by scripts/build_climate_record.py."""
    return RotationAdvisor(
        catalog=load_catalog(),
        rules=load_rules(),
        reference=load_reference(),
        summaries=SeasonSummaryStore(summary_root),
        yield_model=CountyTrendYieldModel(),
        region=region,
        climate=ClimateRecordStore(climate_root),
    )


__all__ = ["RotationAdvisor", "build_advisor"]
