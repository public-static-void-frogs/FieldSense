"""Local sowing windows and heat / frost risk for a field, from the M3 batch outputs.

M3 (`m3_window_forecaster.py`, run offline by its owners) writes parquet tables per ~50 km
weather cell; `m3_lookup.py` is their reader and is used unchanged. This module only picks the
values the recommendation shows and renames them to the API contract. It adds no modelling.

The values are climatology over past years, not a forecast for one season: every date is a
range (early / typical / late year = 10% / 50% / 90% of years).
"""

import threading
from datetime import date
from pathlib import Path

SCENARIOS = ("ssp245", "ssp585")
STAGES = {"firstWorkable": "first_ready", "sow": "sow", "flower": "flower", "mature": "mature"}
# NASS stage names in M3's validation table -> the stage keys above
VALIDATED = {"planted": "sow", "flower": "flower", "mature": "mature"}


class SeasonTiming:
    def __init__(self, out_dir: str | Path | None, reader=None):
        self.out_dir = Path(out_dir) if out_dir else None
        self._shared = reader  # the app's M3Advice for the same folder, to load the tables once
        self._lock = threading.Lock()
        self._reader = None
        self._checked = False

    def _m3(self):
        with self._lock:
            if not self._checked:
                self._checked = True
                if self.out_dir and (self.out_dir / "field_index.parquet").exists():
                    from app.services.m3_lookup import M3Advice

                    self._reader = self._shared or M3Advice(self.out_dir)
            return self._reader

    def for_field(self, field: dict) -> dict | None:
        """The timing block for a stored field, or None outside M3 coverage."""
        reader = self._m3()
        if reader is None:
            return None
        try:
            longitude, latitude = field["geometry"]["coordinates"]
            found = reader.lookup(latitude, longitude)
        except (KeyError, TypeError, ValueError, OSError, ImportError):
            return None
        if not found.get("ok"):
            return None
        windows, risk, match = found["windows"], found["risk"], found["match"]
        errors = found["meta"].get("nass_validation_mae_days") or {}
        crops = {}
        for crop, now in risk["now"].items():
            stages = {
                key: _window(windows["now"].get(f"{crop}:{event}")) for key, event in STAGES.items()
            }
            crops[crop] = {
                "stages": {key: value for key, value in stages.items() if value},
                "dateErrorDays": {
                    VALIDATED[stage]: round(days, 1)
                    for stage, days in errors.get(crop, {}).items()
                    if stage in VALIDATED and days is not None
                },
                "heatAtFlowering": {
                    "probability": now.get("p_heat_overlap"),
                    "low80": now.get("p_heat_lo80"),
                    "high80": now.get("p_heat_hi80"),
                    "meanHotDays": now.get("mean_heat_days_in_window"),
                    "vulnerable": bool(now.get("flag_vulnerable_m5")),
                },
                "frostBeforeMaturity": now.get("p_frost_before_maturity"),
                # None means no safe delay: frost risk is already above M3's limit
                "sowingDelayMarginDays": now.get("adaptation_margin_days"),
                "workableDays": {
                    "low": now.get("workable_days_q10"),
                    "typical": now.get("workable_days_q50"),
                    "high": now.get("workable_days_q90"),
                },
                "years": now.get("n_years"),
                "outlook2040": [
                    {
                        "scenario": scenario,
                        "heatMedian": future.get("p_heat_median"),
                        "heatMin": future.get("p_heat_min"),
                        "heatMax": future.get("p_heat_max"),
                        "marginMinDays": future.get("margin_min"),
                        "marginMaxDays": future.get("margin_max"),
                        "models": future.get("n_models"),
                        "sowTypical": (
                            windows["future"].get(scenario, {}).get(f"{crop}:sow") or {}
                        ).get("date_q50_median"),
                    }
                    for scenario in SCENARIOS
                    if (future := risk["future"].get(scenario, {}).get(crop))
                ],
            }
        return {
            "source": "m3",
            "matchLevel": match["level"],
            "distanceKm": match["distance_km"],
            "cellId": match["cell_id"],
            "lastSpringFrost": _window(windows["now"].get("last_spring_frost")),
            "firstAutumnFrost": _window(windows["now"].get("first_autumn_frost")),
            "crops": crops,
            "waterAtSowing": _water_at_sowing(found.get("fallow_zero")),
        }


def local_calendar(timing: dict | None) -> dict:
    """Local stage dates the rule engine may use: {crop: {"stages": {stage: day of year}}}.

    Only the sowing date is passed on. M3 times flowering and maturity with one heat requirement
    for the whole state, while farmers further north grow earlier hybrids, so its local flowering
    and maturity dates run later in the north than crops really do (corn maturity 247 -> 277 from
    south to north Iowa). The sowing date depends on weather and soil workability alone.
    """
    calendars = {}
    for crop, block in ((timing or {}).get("crops") or {}).items():
        sow = (block.get("stages") or {}).get("sow")
        if not sow:
            continue
        month, day = (int(part) for part in sow["typical"].split("-"))
        calendars[crop] = {
            "stages": {"planted": date(2025, month, day).timetuple().tm_yday},
            "source": "m3_sowing_window",
        }
    return calendars


def _water_at_sowing(fallow: dict | None) -> dict:
    """Soil water at the next crop's sowing, with and without a winter rye cover crop.

    Keyed by the crop just harvested. `shortfall` is the share of past years in which the water a
    plant can use at sowing was below `thresholdMm`.
    """
    blocks = {}
    for key, block in (fallow or {}).items():
        bare, cover = block.get("bare"), block.get("cover") if key.startswith("after_") else None
        if not bare or not cover:
            continue
        blocks[key.removeprefix("after_")] = {
            "nextCrop": block["next_crop"],
            "years": bare["n_years"],
            "thresholdMm": bare["shortfall_threshold_mm"],
            "bare": _branch(bare),
            "cover": _branch(cover),
            "coverOk": block.get("cover_ok"),
            # autumn rain from which the cover crop is safe; 0: any year, None: no such level
            "safeAutumnRainMm": cover["safe_autumn_rain_mm"],
            "autumnRainTypicalMm": _round(cover["autumn_rain_mm"]["q50"]),
        }
    return blocks


def _branch(row: dict) -> dict:
    return {
        "shortfall": _round(row["p_shortfall"], 3),
        "low80": _round(row["p_shortfall_lo80"], 3),
        "high80": _round(row["p_shortfall_hi80"], 3),
        "typicalMm": _round(row["paw_sow_mm"]["q50"]),
    }


def _round(value, digits: int = 0):
    return None if value is None else round(float(value), digits)


def _window(row: dict | None) -> dict | None:
    """Month-day strings ("MM-DD") of a 365-day year."""
    if not row or not row.get("date_q50"):
        return None
    years = row.get("n_years_fit")
    return {
        "early": row["date_q10"],
        "typical": row["date_q50"],
        "late": row["date_q90"],
        "method": row.get("method"),
        "yearsFit": int(years) if years is not None else None,
        "censoredShare": row.get("censored_share"),
    }
