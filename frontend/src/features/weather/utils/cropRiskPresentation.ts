import type { TFunction } from 'i18next';
import type {
  CropMetricBounds,
  CropRiskAlert,
  CropRiskLevel,
  WeatherMetric,
  WeatherRecord,
  WeatherUnits,
} from '../../../types/weather/weather.types.ts';
import { getWeatherMetricConfig } from './weatherPresentation.ts';

export const cropRiskColors: Record<CropRiskLevel, string> = {
  good: '#2f7d32',
  caution: '#c37b08',
  high: '#c7362f',
  unknown: '#657b8d',
};

export function weatherReadingRisk(record: WeatherRecord, metric: WeatherMetric, low = false) {
  const result = record.cropAssessment?.metrics[metric];
  if (low) {
    return result?.lowRiskLevel ?? 'unknown';
  }
  return result?.valueRiskLevel ?? 'unknown';
}

export function formatCropAlert(
  alert: CropRiskAlert,
  units: WeatherUnits,
  t: TFunction,
  language?: string,
) {
  let label = getWeatherMetricConfig(alert.metric, t, units).title;
  if (alert.reading === 'low') {
    label = t('Daily low');
  }
  const values = {
    metric: label,
    value: formatAlertValue(alert.value, alert.unit, language),
    limit: formatAlertValue(alert.boundary, alert.unit, language),
  };
  const messages = {
    below_critical: '{{metric}}: {{value}}, at or below {{limit}}.',
    above_critical: '{{metric}}: {{value}}, at or above {{limit}}.',
    below_good: '{{metric}}: {{value}}, below {{limit}}.',
    above_good: '{{metric}}: {{value}}, above {{limit}}.',
  };
  return t(messages[alert.code], values);
}

const driverLabels = new Map([
  ['temperature', 'Daytime high'],
  ['rainfall', 'Precipitation'],
  ['moisture', 'Soil moisture'],
  ['humidity', 'Humidity'],
  ['wind', 'Wind speed'],
  ['soilType', 'Soil type'],
  ['soilPh', 'Soil pH'],
  ['organicMatter', 'Organic matter'],
  ['waterCapacity', 'Water-holding capacity'],
  ['drainage', 'Drainage'],
]);

export function formatCropAlertDrivers(alert: CropRiskAlert, t: TFunction, language?: string) {
  const factors = new Set<string>();
  for (const { input, value, unit } of alert.drivers ?? []) {
    const label = driverLabels.get(input);
    if (label) {
      factors.add(
        t('{{metric}} ({{value}})', {
          metric: t(label),
          value: formatAlertValue(value, unit, language),
        }),
      );
    }
  }
  if (!factors.size) {
    return null;
  }
  return t('The limit accounts for {{factors}}.', {
    factors: new Intl.ListFormat(language).format(factors),
  });
}

function formatAlertValue(value: string | number, unit: string | null, language?: string) {
  const display = typeof value === 'number' ? value.toLocaleString(language) : value;
  return unit ? `${display} ${unit}` : display;
}

export function cropChartDomain(
  records: WeatherRecord[],
  metric: WeatherMetric,
  bounds?: CropMetricBounds,
) {
  const values = records.flatMap((record) => {
    const readings = [record[metric]];
    if (metric === 'temperature') {
      readings.push(record.low);
    }
    const dailyBounds = record.cropAssessment?.bounds?.[metric];
    if (dailyBounds) {
      readings.push(
        dailyBounds.criticalLow,
        dailyBounds.goodLow,
        dailyBounds.ideal,
        dailyBounds.goodHigh,
        dailyBounds.criticalHigh,
      );
    }
    return readings.filter((value): value is number => value !== null);
  });
  if (bounds) {
    values.push(bounds.goodLow, bounds.ideal, bounds.goodHigh);
    if (bounds.criticalLow !== null) {
      values.push(bounds.criticalLow);
    }
    if (bounds.criticalHigh !== null) {
      values.push(bounds.criticalHigh);
    }
  }
  if (!values.length) {
    return [0, 1] as [number, number];
  }
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * 0.12, 1);
  let low = Math.floor(minimum - padding);
  if (metric !== 'temperature') {
    low = Math.max(0, low);
  }
  return [low, Math.ceil(maximum + padding)] as [number, number];
}

export const cropRiskLabelStyles: Record<
  CropRiskLevel,
  { fill: string; text: string; stroke: string }
> = {
  good: { fill: '#ffffff', text: '#203b2b', stroke: '#91ad96' },
  caution: { fill: '#fff3bd', text: '#713b08', stroke: '#a86707' },
  high: { fill: '#b42318', text: '#ffffff', stroke: '#8f1d15' },
  unknown: { fill: '#ffffff', text: '#243b4d', stroke: '#a6b5bf' },
};

export function cropZoneGradient(bounds: CropMetricBounds, minimum: number, maximum: number) {
  const stops = new Map<number, string>();
  stops.set(minimum, bounds.criticalLow === null ? '#c3d6ae' : '#f3b1aa');
  if (bounds.criticalLow !== null) {
    stops.set(bounds.criticalLow, '#f5b8ad');
    stops.set((bounds.criticalLow + bounds.goodLow) / 2, '#fae8bb');
  }
  stops.set(bounds.goodLow, '#d9e2bb');
  stops.set(bounds.ideal, '#aec99c');
  stops.set(bounds.goodHigh, '#d9e2bb');
  if (bounds.criticalHigh !== null) {
    stops.set((bounds.goodHigh + bounds.criticalHigh) / 2, '#fae8bb');
    stops.set(bounds.criticalHigh, '#f5b8ad');
  }
  stops.set(maximum, bounds.criticalHigh === null ? '#c3d6ae' : '#f3b1aa');

  return [...stops.entries()]
    .sort(([a], [b]) => b - a)
    .map(([value, color]) => ({
      offset: Math.max(0, Math.min(100, ((maximum - value) / (maximum - minimum)) * 100)),
      color,
    }));
}

export function weatherDayBounds(
  record: WeatherRecord,
  metric: WeatherMetric,
  fallback?: CropMetricBounds,
) {
  return record.cropAssessment?.bounds?.[metric] ?? fallback;
}

export function cropBoundsAtPosition(
  records: WeatherRecord[],
  metric: WeatherMetric,
  fallback: CropMetricBounds | undefined,
  position: number,
): CropMetricBounds | undefined {
  if (!records.length) {
    return fallback;
  }
  const clamped = Math.max(0, Math.min(records.length - 1, position));
  const index = Math.floor(clamped);
  const left = weatherDayBounds(records[index], metric, fallback);
  const right = weatherDayBounds(
    records[Math.min(index + 1, records.length - 1)],
    metric,
    fallback,
  );
  if (!left || !right) {
    return left ?? right;
  }
  const fraction = clamped - index;
  function blend(a: number, b: number) {
    return a + (b - a) * fraction;
  }
  function blendNullable(a: number | null, b: number | null) {
    if (fraction === 0) {
      return a;
    }
    if (a === null || b === null) {
      return null;
    }
    return blend(a, b);
  }
  return {
    unit: left.unit,
    criticalLow: blendNullable(left.criticalLow, right.criticalLow),
    goodLow: blend(left.goodLow, right.goodLow),
    ideal: blend(left.ideal, right.ideal),
    goodHigh: blend(left.goodHigh, right.goodHigh),
    criticalHigh: blendNullable(left.criticalHigh, right.criticalHigh),
  };
}
