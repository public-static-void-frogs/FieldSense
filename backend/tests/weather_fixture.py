"""Test-only Open-Meteo contract responses; never imported by production code."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def provider_payload(params):
    start = date.fromisoformat(
        params.get("start_date") or datetime.now(ZoneInfo(params["timezone"])).date().isoformat()
    )
    count = int(params.get("forecast_days", 7))
    if "end_date" in params:
        count = (date.fromisoformat(params["end_date"]) - start).days + 1
    days = [(start + timedelta(days=i)).isoformat() for i in range(count)]
    values = {
        "weather_code": 61,
        "temperature_2m": 12,
        "apparent_temperature": 11,
        "temperature_2m_max": 16,
        "temperature_2m_min": -2,
        "relative_humidity_2m": 72,
        "precipitation_sum": 4.5,
        "precipitation_probability_max": 80,
        "wind_speed_10m": 12,
        "wind_speed_10m_max": 20,
        "wind_direction_10m": 90,
        "wind_direction_10m_dominant": 90,
        "soil_moisture_0_to_1cm": 0.23,
        "soil_moisture_0_to_7cm": 0.25,
    }
    result = {
        "latitude": float(params["latitude"]),
        "longitude": float(params["longitude"]),
        "timezone": params["timezone"],
    }
    for group in ("daily", "hourly", "current"):
        if group not in params:
            continue
        if group == "current":
            result[group] = {
                "time": f"{days[0]}T12:00",
                **{key: values.get(key) for key in params[group].split(",")},
            }
        else:
            times = (
                days
                if group == "daily"
                else [f"{day}T{hour:02}:00" for day in days for hour in range(24)]
            )
            result[group] = {
                "time": times,
                **{key: [values.get(key)] * len(times) for key in params[group].split(",")},
            }
    return result
