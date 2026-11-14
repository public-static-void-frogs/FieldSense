"""Modelled soil moisture at the same point as the parcel's soil assessment."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from math import isfinite
from statistics import fmean
from threading import BoundedSemaphore

from fastapi import HTTPException

from app.schemas.soil_moisture import (
    CurrentSoilMoisture,
    SoilMoistureComparison,
    SoilMoistureHistory,
)

LIVE_LAYERS = {
    "soil_moisture_0_to_1cm": 1,
    "soil_moisture_1_to_3cm": 2,
    "soil_moisture_3_to_9cm": 6,
    "soil_moisture_9_to_27cm": 18,
    "soil_moisture_27_to_81cm": 54,
}
ARCHIVE_PROFILE = {
    "soil_moisture_0_to_7cm": 7,
    "soil_moisture_7_to_28cm": 21,
    "soil_moisture_28_to_100cm": 72,
}
ARCHIVE_LAYERS = (*ARCHIVE_PROFILE, "soil_moisture_100_to_255cm")
POWER_LAYERS = ("GWETTOP", "GWETROOT", "GWETPROF")
COMPARISON_SLOTS = BoundedSemaphore(2)


def coordinates_params(coordinates):
    lon, lat = coordinates
    return {"longitude": lon, "latitude": lat}


def moisture(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
        return float(value)
    return None


def profile(values, weights):
    # A missing horizon leaves the advertised profile incomplete.
    if any(values.get(key) is None for key in weights):
        return None
    return round(
        sum(values[key] * weight for key, weight in weights.items()) / sum(weights.values()), 4
    )


def validate_hourly(payload, params):
    hourly = payload["hourly"]
    times = hourly["time"]
    if not isinstance(times, list):
        raise ValueError("Invalid hourly times")
    for value in times:
        datetime.fromisoformat(value)
    for key in params["hourly"].split(","):
        column = hourly[key]
        if not isinstance(column, list) or len(column) != len(times):
            raise ValueError("Mismatched soil moisture arrays")


def validate_power(payload, _params):
    columns = payload["properties"]["parameter"]
    for key in POWER_LAYERS:
        if not isinstance(columns[key], dict):
            raise ValueError("Invalid NASA POWER series")
        for day in columns[key]:
            datetime.strptime(day, "%Y%m%d")


def utc_time(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def hourly_values(payload, keys):
    hourly = payload["hourly"]
    for i, stamp in enumerate(hourly["time"]):
        yield utc_time(stamp), {key: moisture(hourly[key][i]) for key in keys}


def current(weather, coordinates, now=None):
    config = weather.config
    now = now or datetime.now(timezone.utc)
    params = {
        **coordinates_params(coordinates),
        "hourly": ",".join(LIVE_LAYERS),
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "UTC",
    }
    payload = weather.fetch_provider(
        config.weather_forecast_url, params, config.weather_forecast_ttl_seconds, validate_hourly
    )
    available = (
        (stamp, values)
        for stamp, values in hourly_values(payload, LIVE_LAYERS)
        if stamp <= now and any(value is not None for value in values.values())
    )
    stamp, values = max(available, key=lambda item: item[0], default=(None, {}))
    grid = (payload.get("longitude"), payload.get("latitude"))
    return CurrentSoilMoisture(
        coordinates=coordinates,
        time_utc=stamp,
        layers=values,
        grid_point=grid if all(isinstance(v, (int, float)) and isfinite(v) for v in grid) else None,
        profile_mean=profile(values, LIVE_LAYERS),
    )


def daily_means(observations, keys):
    grouped = defaultdict(lambda: defaultdict(list))
    for stamp, values in observations:
        day = grouped[stamp.date()]
        for key, value in values.items():
            if value is not None:
                day[key].append(value)
    for day, columns in sorted(grouped.items()):
        yield day, {key: round(fmean(columns[key]), 4) if columns[key] else None for key in keys}


def stats(rows, keys):
    result = {}
    for key in keys:
        values = sorted(row["values"][key] for row in rows if row["values"].get(key) is not None)
        if not values:
            continue

        def quantile(fraction):
            index = (len(values) - 1) * fraction
            low = int(index)
            high = min(low + 1, len(values) - 1)
            return round(values[low] + (values[high] - values[low]) * (index - low), 4)

        result[key] = dict(
            n=len(values),
            mean=round(fmean(values), 4),
            min=values[0],
            max=values[-1],
            p10=quantile(0.1),
            p50=quantile(0.5),
            p90=quantile(0.9),
        )
    return result


def history(weather, coordinates, start, end, source, frequency):
    config = weather.config
    params = coordinates_params(coordinates)
    ttl = config.weather_history_ttl_seconds
    if source == "power":
        params.update(
            parameters=",".join(POWER_LAYERS),
            community="AG",
            format="JSON",
            start=start.strftime("%Y%m%d"),
            end=end.strftime("%Y%m%d"),
            **{"time-standard": "UTC"},
        )
        payload = weather.fetch_provider(
            config.soil_moisture_power_url, params, ttl, validate_power
        )
        columns = payload["properties"]["parameter"]
        days = sorted(set().union(*(columns[key] for key in POWER_LAYERS)))
        rows = [
            {
                "date": datetime.strptime(day, "%Y%m%d").date(),
                "values": {key: moisture(columns[key].get(day)) for key in POWER_LAYERS},
            }
            for day in days
        ]
        keys = POWER_LAYERS
        unit = "fraction_of_saturation"
    else:
        params.update(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            hourly=",".join(ARCHIVE_LAYERS),
            timezone="UTC",
            models="era5_land",
        )
        payload = weather.fetch_provider(config.weather_archive_url, params, ttl, validate_hourly)
        observations = hourly_values(payload, ARCHIVE_LAYERS)
        if frequency == "hourly":
            rows = [
                {"date": stamp.date(), "time_utc": stamp, "values": values}
                for stamp, values in observations
            ]
        else:
            rows = [
                {"date": day, "values": values}
                for day, values in daily_means(observations, ARCHIVE_LAYERS)
            ]
        for row in rows:
            row["values"]["profile_mean"] = profile(row["values"], ARCHIVE_PROFILE)
        keys = (*ARCHIVE_LAYERS, "profile_mean")
        unit = "m3/m3"
    rows = [
        row
        for row in rows
        if start <= row["date"] <= end
        and any(value is not None for value in row["values"].values())
    ]
    return SoilMoistureHistory(
        coordinates=coordinates,
        source=source,
        frequency=frequency,
        start=start,
        end=end,
        series=rows,
        stats=stats(rows, keys),
        unit=unit,
    )


def compare_to_history(weather, coordinates, snapshot, years=10, window_days=7):
    values = {}
    unavailable = []
    today = snapshot.profile_mean
    if today is not None and snapshot.time_utc is not None:
        observed = snapshot.time_utc.date()

        def baseline(year):
            try:
                center = observed.replace(year=year)
            except ValueError:
                center = observed.replace(year=year, day=28)
            try:
                series = history(
                    weather,
                    coordinates,
                    center - timedelta(days=window_days),
                    center,
                    "openmeteo",
                    "daily",
                )
            except HTTPException:
                return year, None
            summary = series.stats.get("profile_mean")
            return year, summary.mean if summary else None

        if not COMPARISON_SLOTS.acquire(blocking=False):
            raise HTTPException(
                503, "Soil moisture comparisons are busy. Please try again shortly."
            )
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                for year, value in pool.map(baseline, range(observed.year - years, observed.year)):
                    if value is None:
                        unavailable.append(year)
                    else:
                        values[year] = value
        finally:
            COMPARISON_SLOTS.release()
    mean = fmean(values.values()) if len(values) >= 3 else None
    return SoilMoistureComparison(
        current=snapshot,
        window_days=window_days,
        years=values,
        unavailable_years=unavailable,
        past_mean=round(mean, 4) if mean is not None else None,
        anomaly=round(today - mean, 4) if mean is not None else None,
        percentile=round(100 * sum(value < today for value in values.values()) / len(values))
        if mean is not None
        else None,
    )
