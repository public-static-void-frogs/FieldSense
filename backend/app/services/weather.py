"""Open-Meteo adapter. No demo fallback, per-process bounded TTL cache and single flight."""

import math
from collections import OrderedDict, defaultdict
from concurrent.futures import Future
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from threading import RLock
from time import monotonic
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

DAILY = (
    "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "wind_speed_10m_max,wind_direction_10m_dominant"
)
CURRENT = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,"
    "weather_code,wind_speed_10m,wind_direction_10m"
)


def condition(code):
    if code == 0:
        return "Clear sky"
    if code in (1, 2):
        return "Partly cloudy"
    if code == 3:
        return "Overcast"
    if code in (45, 48):
        return "Fog"
    if code in (51, 53, 55, 56, 57):
        return "Drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "Snow"
    if code in (95, 96, 99):
        return "Thunderstorm"
    return "Unknown conditions"


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return round(value, 2)
    return None


def average(values, scale=1):
    present = [v for v in values if number(v) is not None]
    return number(sum(present) / len(present) * scale) if present else None


class WeatherService:
    def __init__(self, config, client=None, clock=monotonic):
        self.config = config
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(config.weather_timeout_seconds, connect=2),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={"User-Agent": "FieldShiftNASA/1.0"},
            follow_redirects=False,
        )
        self.clock = clock
        self._cache = OrderedDict()
        self._pending = {}
        self._lock = RLock()

    def close(self):
        self.client.close()

    def today(self, preferences):
        return datetime.now(ZoneInfo(preferences.time_zone)).date()

    def _location(self, preferences):
        if preferences.latitude is None or preferences.longitude is None:
            raise HTTPException(422, "Choose your farm location on the map in Settings.")
        return {
            "latitude": preferences.latitude,
            "longitude": preferences.longitude,
            "timezone": preferences.time_zone,
            "temperature_unit": "fahrenheit" if preferences.units == "imperial" else "celsius",
            "wind_speed_unit": "mph" if preferences.units == "imperial" else "kmh",
            "precipitation_unit": "inch" if preferences.units == "imperial" else "mm",
        }

    def _fetch(self, url, params, ttl):
        key = (url, tuple(sorted(params.items())))
        with self._lock:
            cached = self._cache.get(key)
            if cached and cached[0] > self.clock():
                self._cache.move_to_end(key)
                return deepcopy(cached[1])
            if cached:
                del self._cache[key]
            pending = self._pending.get(key)
            owner = pending is None
            if owner:
                pending = Future()
                self._pending[key] = pending
        if not owner:
            return deepcopy(pending.result())
        try:
            response = self.client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("error"):
                raise ValueError("Invalid weather response")
            payload["fetchedAt"] = datetime.now(timezone.utc).isoformat()
            # Validate the provider boundary before caching an apparently successful response.
            self._validate(payload, params)
            with self._lock:
                self._cache[key] = (self.clock() + ttl, payload)
                while len(self._cache) > self.config.weather_cache_size:
                    self._cache.popitem(last=False)
            pending.set_result(payload)
            return deepcopy(payload)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            failure = HTTPException(
                503, "Weather provider is unavailable. Please try again shortly."
            )
            pending.set_exception(failure)
            raise failure from error
        finally:
            with self._lock:
                self._pending.pop(key, None)

    @staticmethod
    def _validate(payload, params):
        for key in ("latitude", "longitude"):
            if number(payload.get(key)) is None:
                raise ValueError("Missing grid coordinates")
        for group in ("daily", "hourly"):
            values = payload[group]
            times = values["time"]
            if not isinstance(times, list) or not times:
                raise ValueError("Missing weather dates")
            for timestamp in times:
                datetime.fromisoformat(timestamp)
            for variable in params[group].split(","):
                column = values[variable]
                if not isinstance(column, list) or len(column) != len(times):
                    raise ValueError("Mismatched weather arrays")
                if any(value is not None and number(value) is None for value in column):
                    raise ValueError("Invalid weather value")
        if "current" in params:
            current = payload["current"]
            datetime.fromisoformat(current["time"])
            for variable in params["current"].split(","):
                if variable not in current:
                    raise ValueError("Missing current weather variable")
                if current[variable] is not None and number(current[variable]) is None:
                    raise ValueError("Invalid current weather value")

    def _forecast_payload(self, preferences):
        params = self._location(preferences)
        params.update(
            current=CURRENT,
            daily=DAILY + ",precipitation_probability_max",
            hourly="relative_humidity_2m,soil_moisture_0_to_1cm",
            forecast_days=14,
        )
        return self._fetch(
            self.config.weather_forecast_url, params, self.config.weather_forecast_ttl_seconds
        )

    def _metadata(self, preferences, payload, historical=False):
        imperial = preferences.units == "imperial"
        return dict(
            location=preferences.location or f"{preferences.latitude}, {preferences.longitude}",
            latitude=preferences.latitude,
            longitude=preferences.longitude,
            gridLatitude=payload["latitude"],
            gridLongitude=payload["longitude"],
            timeZone=payload.get("timezone", preferences.time_zone),
            fetchedAt=payload["fetchedAt"],
            units=dict(
                temperature="°F" if imperial else "°C",
                rainfall="in" if imperial else "mm",
                wind="mph" if imperial else "km/h",
            ),
            soilDepth="0–7 cm" if historical else "0–1 cm",
            dataKind="historical_model" if historical else "forecast",
        )

    def _records(self, preferences, payload, historical=False):
        daily = payload["daily"]
        hourly = payload["hourly"]
        moisture_key = "soil_moisture_0_to_7cm" if historical else "soil_moisture_0_to_1cm"
        samples = defaultdict(lambda: defaultdict(list))
        for index, timestamp in enumerate(hourly["time"]):
            day = timestamp[:10]
            for variable in ("relative_humidity_2m", moisture_key):
                samples[day][variable].append(hourly[variable][index])
        records = []
        today = self.today(preferences).isoformat()
        for index, day in enumerate(daily["time"]):

            def value(variable):
                column = daily.get(variable)
                return number(column[index]) if column else None

            code = value("weather_code")
            records.append(
                dict(
                    key=index,
                    date=day,
                    today=day == today,
                    conditions=condition(code),
                    weatherCode=code,
                    temperature=value("temperature_2m_max"),
                    low=value("temperature_2m_min"),
                    rainfall=value("precipitation_sum"),
                    humidity=average(samples[day]["relative_humidity_2m"]),
                    wind=value("wind_speed_10m_max"),
                    windDirection=value("wind_direction_10m_dominant"),
                    moisture=average(samples[day][moisture_key], 100),
                    rainChance=value("precipitation_probability_max"),
                )
            )
        if historical:
            records.reverse()
            for index, record in enumerate(records):
                record["key"] = index
        return records

    def current(self, preferences):
        payload = self._forecast_payload(preferences)
        records = self._records(preferences, payload)
        current = payload["current"]
        code = current.get("weather_code")
        label = condition(code)
        icon = "cloudy"
        if code == 0:
            icon = "sunny"
        elif label in ("Rain", "Drizzle", "Thunderstorm"):
            icon = "rain"
        elif label == "Snow":
            icon = "snow"
        elif label == "Fog":
            icon = "fog"
        return dict(
            self._metadata(preferences, payload),
            observedAt=current["time"],
            condition=icon,
            conditions=label,
            temperature=number(current.get("temperature_2m")),
            feelsLike=number(current.get("apparent_temperature")),
            high=records[0]["temperature"],
            low=records[0]["low"],
            humidity=number(current.get("relative_humidity_2m")),
            wind=number(current.get("wind_speed_10m")),
            windDirection=number(current.get("wind_direction_10m")),
            rainChance=records[0]["rainChance"],
            forecast=records[1:6],
        )

    def forecast(self, preferences):
        payload = self._forecast_payload(preferences)
        return dict(
            self._metadata(preferences, payload), records=self._records(preferences, payload)
        )

    def history(self, preferences, days=30, start=None, end=None):
        params = self._location(preferences)
        today = self.today(preferences)
        if (start is None) != (end is None):
            raise HTTPException(422, "Provide both start_date and end_date.")
        end = end or today - timedelta(days=1)
        start = start or end - timedelta(days=days - 1)
        if start < date(1940, 1, 1) or start > end or end >= today or (end - start).days >= 366:
            raise HTTPException(422, "Choose 1–366 historical days from 1940 through yesterday.")
        params.update(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            daily=DAILY,
            hourly="relative_humidity_2m,soil_moisture_0_to_7cm",
        )
        payload = self._fetch(
            self.config.weather_archive_url, params, self.config.weather_history_ttl_seconds
        )
        return dict(
            self._metadata(preferences, payload, historical=True),
            records=self._records(preferences, payload, historical=True),
        )
