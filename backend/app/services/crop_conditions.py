"""Deterministic growing-season crop weather rules with auditable alert evidence."""

from copy import deepcopy
from dataclasses import dataclass
from math import ceil, floor
from statistics import mean
from types import SimpleNamespace
from typing import Protocol

from app.schemas.crop_conditions import CropAssessmentContext, CropMetricBounds

METRICS = ("temperature", "rainfall", "moisture", "humidity", "wind")
BOUND_KEYS = ("criticalLow", "goodLow", "ideal", "goodHigh", "criticalHigh")
SOIL_UNITS = {
    "soilType": None,
    "soilPh": None,
    "organicMatter": "%",
    "waterCapacity": "mm/m",
    "drainage": None,
}
ORDER = {"unknown": -1, "good": 0, "caution": 1, "high": 2}


@dataclass(frozen=True)
class CropProfile:
    # Critical low, good low, ideal, good high and critical high in Celsius.
    temperature: tuple[int, int, int, int, int]
    damp_sensitivity: float
    dry_soil_offset: float


# General active-growth screening ranges. The mixed pasture class uses cool-season forage.
CROP_PROFILES = {
    "Winter wheat": CropProfile((0, 8, 18, 24, 30), 1.0, 0),
    "Corn": CropProfile((8, 16, 24, 30, 36), 0.7, 2),
    "Soybeans": CropProfile((6, 14, 23, 29, 35), 0.9, 1),
    "Alfalfa": CropProfile((-4, 10, 22, 26, 32), 0.8, -1),
    "Grassland/Pasture": CropProfile((-5, 8, 19, 24, 30), 0.6, 0.5),
}
CROP_NAMES = {crop.casefold(): crop for crop in CROP_PROFILES}
ALERT_RULES = {
    "temperature": ("cold_stress", "heat_stress"),
    "rainfall": ("low_precipitation", "heavy_precipitation"),
    "moisture": ("dry_soil", "wet_soil"),
    "humidity": ("dry_air", "humid_air"),
    "wind": ("low_wind", "strong_wind"),
}


class CropConditionModel(Protocol):
    def predict(self, series: dict, context: CropAssessmentContext) -> dict: ...


def field_location(preferences, field):
    longitude, latitude = field["geometry"]["coordinates"]
    return SimpleNamespace(
        latitude=latitude,
        longitude=longitude,
        time_zone=preferences.time_zone,
        units=preferences.units,
        location=field["name"],
    )


def _si(value, metric, units):
    if value is None:
        return None
    if metric == "temperature" and units[metric] == "°F":
        return (value - 32) * 5 / 9
    if metric == "rainfall" and units[metric] == "in":
        return value * 25.4
    if metric == "wind" and units[metric] == "mph":
        return value * 1.609344
    return value


def _display(value, metric, units, bound):
    if value is None:
        return None
    if metric == "temperature" and units[metric] == "°F":
        value = value * 9 / 5 + 32
    elif metric == "rainfall" and units[metric] == "in":
        value /= 25.4
    elif metric == "wind" and units[metric] == "mph":
        value /= 1.609344
    # On the provider's 0.01 reading grid, round each cutoff to preserve its inequality.
    grid_value = round(value * 100, 8)
    if bound in ("criticalLow", "goodHigh"):
        return floor(grid_value) / 100
    if bound in ("goodLow", "criticalHigh"):
        return ceil(grid_value) / 100
    return round(value, 2)


def _average(records, key):
    values = [row[key] for row in records if row[key] is not None]
    return round(mean(values), 2) if values else None


def assessment_context(series, field) -> CropAssessmentContext | None:
    records = series["records"]
    crop = CROP_NAMES.get((field.get("crop") or "").strip().casefold())
    if crop is None or not records:
        return None
    source_soil = (field.get("properties") or {}).get("soil") or {}
    soil = {key: source_soil.get(key) for key in SOIL_UNITS}
    for key in ("soilType", "drainage"):
        soil[key] = (soil[key] or "").strip() or None
    present = sum(value is not None for value in soil.values())
    coverage = "complete" if present == len(soil) else "partial" if present else "unavailable"
    dates = [row["date"] for row in records]
    return CropAssessmentContext(
        fieldId=field["id"],
        fieldName=field["name"],
        crop=crop,
        latitude=series["latitude"],
        longitude=series["longitude"],
        soil=soil,
        soilCoverage=coverage,
        climate=dict(
            source="history_window"
            if series["dataKind"] == "historical_model"
            else "forecast_window",
            startDate=min(dates),
            endDate=max(dates),
            sampleDays=len(records),
            meanHigh=_average(records, "temperature"),
            meanLow=_average(records, "low"),
            meanHumidity=_average(records, "humidity"),
            meanDailyRainfall=_average(records, "rainfall"),
        ),
    )


def _evaluate(reading, display_bounds, bounds, metric, units):
    if reading is None:
        return "unknown", None, None, None
    value = _si(reading, metric, units)
    if display_bounds["criticalLow"] is not None and reading <= display_bounds["criticalLow"]:
        return "high", 10.0, "below_critical", "criticalLow"
    if display_bounds["criticalHigh"] is not None and reading >= display_bounds["criticalHigh"]:
        return "high", 10.0, "above_critical", "criticalHigh"
    if reading < display_bounds["goodLow"]:
        span = bounds.goodLow - (
            bounds.criticalLow if bounds.criticalLow is not None else bounds.goodLow - 1
        )
        score = 70 - 50 * (bounds.goodLow - value) / span
        return "caution", round(max(20, score), 1), "below_good", "goodLow"
    if reading > display_bounds["goodHigh"]:
        span = (
            bounds.criticalHigh if bounds.criticalHigh is not None else bounds.goodHigh + 1
        ) - bounds.goodHigh
        score = 70 - 50 * (value - bounds.goodHigh) / span
        return "caution", round(max(20, score), 1), "above_good", "goodHigh"
    span = max(bounds.ideal - bounds.goodLow, bounds.goodHigh - bounds.ideal, 1)
    return "good", round(100 - 25 * abs(value - bounds.ideal) / span, 1), None, None


def _pressure(value, start, span):
    """A bounded illustrative interaction; absent inputs contribute no adjustment."""
    if value is None:
        return 0.0
    return max(0.0, min(1.0, (value - start) / span))


def _mean_si(series, key, metric):
    values = [
        _si(row[key], metric, series["units"]) for row in series["records"] if row[key] is not None
    ]
    return round(mean(values), 4) if values else None


def _metric_bounds(series, context):
    """Apply bounded weather and soil adjustments, recording which cutoffs they affect."""
    profile = CROP_PROFILES[context.crop]
    soil = context.soil
    units = series["units"]
    observations = {metric: _average(series["records"], metric) for metric in METRICS}
    observations.update(soil.model_dump())
    heat = _mean_si(series, "temperature", "temperature")
    humidity = _mean_si(series, "humidity", "humidity")
    water = _mean_si(series, "moisture", "moisture")
    rain = _mean_si(series, "rainfall", "rainfall")
    wind = _mean_si(series, "wind", "wind")

    dry_soil_offset = profile.dry_soil_offset
    bounds = {
        "temperature": list(profile.temperature),
        "moisture": [7 + dry_soil_offset / 2, 15 + dry_soil_offset, 25 + dry_soil_offset, 35, 48],
        "rainfall": [None, 0, 2, 8.5, 17],
        "humidity": [20, 40, 60, 80, 95],
        "wind": [None, 0, 8, 20, 35],
    }
    drivers = {metric: {key: [] for key in BOUND_KEYS} for metric in METRICS}

    def evidence(rule_id, input_key):
        return dict(
            ruleId=rule_id,
            input=input_key,
            value=observations[input_key],
            unit=units.get(input_key, SOIL_UNITS.get(input_key, "%")),
        )

    def apply(rule_id, input_key, strength, adjustments):
        if not strength:
            return
        driver = evidence(rule_id, input_key)
        for metric, weights in adjustments.items():
            for index, weight in enumerate(weights):
                if weight:
                    bounds[metric][index] += weight * strength
                    drivers[metric][BOUND_KEYS[index]].append(driver)

    texture = (soil.soilType or "").lower()
    if "sand" in texture:
        apply("soil_texture", "soilType", 1, {"moisture": (-3, -7, -8, -8, -10)})
    elif "clay" in texture:
        apply("soil_texture", "soilType", 1, {"moisture": (3, 5, 5, 7, 7)})

    # Dryness and saturation are relative to the texture-adjusted baseline.
    _, moisture_low, _, moisture_high, moisture_critical_high = bounds["moisture"]
    dry_soil = _pressure(None if water is None else moisture_low - water, 0, moisture_low)
    wet_soil = _pressure(water, moisture_high, moisture_critical_high - moisture_high)
    humid_air = _pressure(humidity, 70, 25)
    dry_air = _pressure(None if humidity is None else 45 - humidity, 0, 25)
    hot_weather = _pressure(heat, 25, 10)
    windy_weather = _pressure(wind, 15, 20)
    heavy_rain = _pressure(rain, 4, 12)
    drainage = (soil.drainage or "").lower()
    poor_drainage = "poor" in drainage

    if soil.waterCapacity is not None:
        capacity_limit = max(6, min(12, soil.waterCapacity / 20))
        apply(
            "water_capacity", "waterCapacity", capacity_limit - 8.5, {"rainfall": (0, 0, 0, 1, 2)}
        )
    if "drained" in drainage and "moderately" not in drainage and not poor_drainage:
        apply("good_drainage", "drainage", 1, {"rainfall": (0, 0, 0, 1, 2)})
    rainfall_limit = bounds["rainfall"][3]

    # Keep both buffering inputs independently optional and cap the combined effect.
    capacity = 0 if soil.waterCapacity is None else (soil.waterCapacity - 170) / 60
    organic_matter = 0 if soil.organicMatter is None else (soil.organicMatter - 3.5) / 3
    total_buffer = capacity + organic_matter
    if total_buffer:
        bounds["temperature"][4] += max(-1, min(1, total_buffer))
        if capacity:
            drivers["temperature"]["criticalHigh"].append(
                evidence("water_capacity", "waterCapacity")
            )
        if organic_matter:
            drivers["temperature"]["criticalHigh"].append(
                evidence("organic_matter", "organicMatter")
            )
    if soil.soilPh is not None:
        ph_stress = max(_pressure(6 - soil.soilPh, 0, 1.5), _pressure(soil.soilPh, 7.5, 1.5))
        apply("soil_ph_stress", "soilPh", ph_stress, {"temperature": (0, 0, 0, 0, -1)})

    adaptation = 0 if heat is None else max(-1.5, min(1.5, (heat - 20) / 10))
    damp_sensitivity = profile.damp_sensitivity
    apply("temperature_adaptation", "temperature", adaptation, {"temperature": (0, 0, 1, 1, 0)})
    apply(
        "dry_soil",
        "moisture",
        dry_soil,
        {
            "temperature": (0, 0, 0, -1.5, -2.5),
            "humidity": (3, 2, 0, 0, 0),
            "wind": (0, 0, 0, -3, -5),
        },
    )
    apply(
        "wet_soil",
        "moisture",
        wet_soil,
        {
            "temperature": (1.5, 0.8, 0, 0, 0),
            "humidity": (0, 0, -2, -4 * damp_sensitivity, -5 * damp_sensitivity),
            "rainfall": (
                0,
                0,
                0,
                -0.2 * damp_sensitivity * rainfall_limit,
                -0.4 * damp_sensitivity * rainfall_limit,
            ),
        },
    )
    apply(
        "humid_air",
        "humidity",
        humid_air,
        {
            "temperature": (0, 0, -0.6, -1.2, -2),
            "moisture": (0, 0, -1, -2, -3),
            "rainfall": (0, 0, 0, -0.1 * rainfall_limit, -0.2 * rainfall_limit),
        },
    )
    apply(
        "dry_air",
        "humidity",
        dry_air,
        {
            "temperature": (0, 0, 0, -0.5, -0.8),
            "moisture": (1, 1, 0, 0, 0),
            "wind": (0, 0, 0, 0, -3),
        },
    )
    apply(
        "hot_weather",
        "temperature",
        hot_weather,
        {
            "humidity": (0, 0, 0, -2, -2),
            "moisture": (2, 3, 1, 0, 0),
            "wind": (0, 0, 0, -2, -2),
        },
    )
    apply(
        "windy_weather",
        "wind",
        windy_weather,
        {
            "temperature": (0.5, 0, 0, 0, 0),
            "moisture": (1, 2, 0, 0, 0),
        },
    )
    apply(
        "heavy_rain",
        "rainfall",
        heavy_rain,
        {
            "humidity": (0, 0, 0, -2 * damp_sensitivity, -2.5 * damp_sensitivity),
            "moisture": (0, 0, 0, 0, -2),
        },
    )
    apply(
        "poor_drainage",
        "drainage",
        poor_drainage,
        {
            "humidity": (0, 0, 0, 0, -2),
            "moisture": (0, 0, 0, -2, -2),
            "rainfall": (0, 0, 0, -0.15 * rainfall_limit, -0.3 * rainfall_limit),
        },
    )

    return {
        metric: CropMetricBounds(unit=units.get(metric, "%"), **dict(zip(BOUND_KEYS, values)))
        for metric, values in bounds.items()
    }, drivers


def _display_bounds(bounds, units):
    return {
        metric: dict(
            unit=value.unit,
            **{key: _display(getattr(value, key), metric, units, key) for key in BOUND_KEYS},
        )
        for metric, value in bounds.items()
    }


class CropWeatherRuleEngine:
    """Assess each date using that day's measurements and the selected crop profile."""

    def predict(self, series, context):
        result = deepcopy(series)
        units = series["units"]
        reference_bounds, _ = _metric_bounds(series, context)
        for record in result["records"]:
            bounds, drivers = _metric_bounds({**series, "records": [record]}, context)
            display_bounds = _display_bounds(bounds, units)
            alerts, metrics, scores = [], {}, []
            available = 0
            for metric in METRICS:
                risk, score, code, bound = _evaluate(
                    record[metric], display_bounds[metric], bounds[metric], metric, units
                )
                value_risk = risk
                low_risk = None
                readings = [("value", record[metric], risk, code, bound)]
                if metric == "temperature":
                    low_risk, low_score, low_code, low_bound = _evaluate(
                        record["low"], display_bounds[metric], bounds[metric], metric, units
                    )
                    readings.append(("low", record["low"], low_risk, low_code, low_bound))
                    risk = max((risk, low_risk), key=ORDER.get)
                    if risk == "good" and "unknown" in (value_risk, low_risk):
                        risk = "unknown"
                    present = [value for value in (score, low_score) if value is not None]
                    score = min(present) if present else None
                if score is not None:
                    scores.append(score)
                if record[metric] is not None and (
                    metric != "temperature" or record["low"] is not None
                ):
                    available += 1
                metrics[metric] = dict(
                    riskLevel=risk,
                    valueRiskLevel=value_risk,
                    lowRiskLevel=low_risk,
                    suitabilityScore=score,
                )
                for reading, value, severity, reason, bound in readings:
                    if reason:
                        alerts.append(
                            dict(
                                metric=metric,
                                reading=reading,
                                severity=severity,
                                code=reason,
                                value=value,
                                boundary=display_bounds[metric][bound],
                                unit=units.get(metric, "%"),
                                ruleId=ALERT_RULES[metric][int(reason.startswith("above"))],
                                drivers=drivers[metric][bound],
                            )
                        )
            level = max((value["riskLevel"] for value in metrics.values()), key=ORDER.get)
            if available < len(METRICS) and level == "good":
                level = "unknown"
            coverage = "complete" if available == len(METRICS) else "partial"
            if not scores:
                coverage = "unavailable"
            record["cropAssessment"] = dict(
                bounds=display_bounds,
                suitabilityScore=min(scores) if scores else None,
                riskLevel=level,
                coverage=coverage,
                metrics=metrics,
                alerts=alerts,
            )
        result["cropAssessment"] = dict(
            model=dict(id="crop-weather-rules", version="2.0.0", kind="rule_engine"),
            context=context.model_dump(mode="json"),
            bounds=_display_bounds(reference_bounds, units),
        )
        return result
