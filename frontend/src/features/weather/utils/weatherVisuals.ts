import type {
  WeatherMetric,
  WeatherRecord,
  WeatherUnits,
} from '../../../types/weather/weather.types.ts';

const clamp = (value: number) => Math.max(0, Math.min(1, value));

export function weatherColor(value: number | null, metric: WeatherMetric, units: WeatherUnits) {
  if (value === null) {
    return '#e5e9e1';
  }
  let amount = value;
  if (metric === 'temperature') {
    if (units.temperature === '°F') {
      amount = ((value - 32) * 5) / 9;
    }
    // Familiar weather-map palette: cold blue, mild neutral, warm amber/red.
    const stops = [
      { at: -20, rgb: [59, 77, 155] },
      { at: 0, rgb: [55, 126, 184] },
      { at: 12, rgb: [120, 171, 204] },
      { at: 18, rgb: [214, 210, 191] },
      { at: 25, rgb: [232, 169, 73] },
      { at: 35, rgb: [213, 89, 56] },
      { at: 45, rgb: [153, 43, 45] },
    ];
    const upper = stops.findIndex((stop) => amount <= stop.at);
    if (upper === 0) {
      return `rgb(${stops[0].rgb.join(', ')})`;
    }
    if (upper === -1) {
      return `rgb(${stops[stops.length - 1].rgb.join(', ')})`;
    }
    const before = stops[upper - 1];
    const after = stops[upper];
    const position = (amount - before.at) / (after.at - before.at);
    const rgb = before.rgb.map((channel, index) =>
      Math.round(channel + (after.rgb[index] - channel) * position),
    );
    return `rgb(${rgb.join(', ')})`;
  }
  if (metric === 'rainfall') {
    if (units.rainfall === 'in') {
      amount = value * 25.4;
    }
    return `hsl(204 65% ${94 - Math.sqrt(clamp(amount / 20)) * 52}%)`;
  }
  if (metric === 'moisture') {
    return `hsl(${35 + clamp(amount / 50) * 135} 42% ${68 - clamp(amount / 50) * 28}%)`;
  }
  if (metric === 'wind') {
    if (units.wind === 'mph') {
      amount = value * 1.609344;
    }
    return `hsl(258 35% ${88 - clamp(amount / 60) * 44}%)`;
  }
  return `hsl(180 37% ${91 - clamp(amount / 100) * 50}%)`;
}

export function summarizeWeather(records: WeatherRecord[], metric: WeatherMetric) {
  const available = records.filter((record) => record[metric] !== null);
  if (!available.length) {
    return null;
  }
  const sorted = [...available].sort((a, b) => a[metric]! - b[metric]!);
  return {
    low: sorted[0],
    high: sorted[sorted.length - 1],
    average: available.reduce((sum, record) => sum + record[metric]!, 0) / available.length,
    total: available.reduce((sum, record) => sum + record[metric]!, 0),
    count: available.length,
  };
}

export function weatherHighlights(records: WeatherRecord[]) {
  const week = records.slice(0, 7);
  const rain = summarizeWeather(week, 'rainfall');
  const nights = week.filter((record) => record.low !== null);
  const coolestNight = [...nights].sort((a, b) => a.low! - b.low!)[0];
  return { rainTotal: rain && rain.count === 7 ? rain.total : null, coolestNight };
}
