import type { WeatherMetric } from '../../../types/weather/weather.types.ts';

export const historyRanges = ['7 days', '30 days', '90 days'] as const;
type WeatherMetricConfig = {
  title: string;
  unit: string;
  color: string;
  description: string;
};

export const weatherMetrics: Record<WeatherMetric, WeatherMetricConfig> = {
  temperature: {
    title: 'Air temperature',
    unit: '°C',
    color: '#b8954d',
    description: 'Daily high air temperature',
  },
  rainfall: {
    title: 'Precipitation',
    unit: 'mm',
    color: '#345865',
    description: 'Daily accumulated precipitation (rain and snow)',
  },
  moisture: {
    title: 'Soil moisture',
    unit: '%',
    color: '#476b3c',
    description: 'Modelled surface soil water content',
  },
  humidity: {
    title: 'Humidity',
    unit: '%',
    color: '#7a9b63',
    description: 'Relative air humidity',
  },
  wind: {
    title: 'Wind speed',
    unit: 'km/h',
    color: '#656f82',
    description: 'Daily maximum wind speed',
  },
};
