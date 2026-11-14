import type { TFunction } from 'i18next';
import { CloudRain, Thermometer, Droplets, Sprout, Wind } from 'lucide-react';
import type {
  WeatherMetric,
  WeatherRecord,
  WeatherUnits,
} from '../../../types/weather/weather.types.ts';
import { weatherMetrics } from '../constants/weather.constants.ts';

export function getWeatherMetricIcon(metric: WeatherMetric) {
  const icons = {
    temperature: Thermometer,
    rainfall: CloudRain,
    moisture: Sprout,
    humidity: Droplets,
    wind: Wind,
  };
  return icons[metric];
}

export function selectWeatherReading(records: WeatherRecord[], key: number) {
  return records.find((record) => record.key === key) ?? records[0];
}

export function getWeatherChange(
  records: WeatherRecord[],
  selected: WeatherRecord,
  metric: WeatherMetric,
) {
  const previous = records.find((record) => record.key === selected.key + 1);
  if (!previous || selected[metric] === null || previous[metric] === null) {
    return null;
  }
  return Number((selected[metric] - previous[metric]).toFixed(2));
}

export function getWeatherMetricConfig(metric: WeatherMetric, t: TFunction, units?: WeatherUnits) {
  const config = weatherMetrics[metric];

  return {
    ...config,
    title: t(config.title),
    description: t(config.description),
    unit: units?.[metric] ?? config.unit,
  };
}

export function formatWeatherValue(value: number | null, unit = '') {
  if (value === null) {
    return '—';
  }
  return `${Number(value.toFixed(1))}${unit ? ` ${unit}` : ''}`;
}

export function formatWeatherDate(date: string, language?: string) {
  return new Intl.DateTimeFormat(language, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${date}T12:00:00Z`));
}

export function windDirection(degrees: number | null, t: TFunction) {
  if (degrees === null) {
    return '—';
  }
  const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  return t(directions[Math.round(degrees / 45) % 8]);
}
