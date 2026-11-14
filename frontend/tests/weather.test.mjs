import assert from 'node:assert/strict';
import test from 'node:test';
import { weatherApi } from '../src/api/weather/weather.api.ts';
import {
  weatherColor,
  summarizeWeather,
  weatherHighlights,
} from '../src/features/weather/utils/weatherVisuals.ts';

import { getWeatherScene } from '../src/features/weather/utils/weatherScene.ts';

import { getWeatherDayInsight } from '../src/features/weather/utils/weatherDayInsight.ts';

const units = { temperature: '°C', rainfall: 'mm', wind: 'km/h', humidity: '%', moisture: '%' };
const record = (date, values) => ({
  date,
  temperature: null,
  low: null,
  rainfall: null,
  moisture: null,
  humidity: null,
  wind: null,
  ...values,
});

test('temperature palette is cold blue and warm red, with the same colors in Fahrenheit', () => {
  const rgb = (color) => color.match(/\d+/g).map(Number);
  const cold = rgb(weatherColor(0, 'temperature', units));
  const hot = rgb(weatherColor(35, 'temperature', units));
  assert.ok(cold[2] > cold[0] && cold[2] > cold[1]);
  assert.ok(hot[0] > hot[1] && hot[0] > hot[2]);
  assert.equal(
    weatherColor(0, 'temperature', units),
    weatherColor(32, 'temperature', { ...units, temperature: '°F' }),
  );
  assert.equal(
    weatherColor(35, 'temperature', units),
    weatherColor(95, 'temperature', { ...units, temperature: '°F' }),
  );
  assert.equal(weatherColor(null, 'temperature', units), '#e5e9e1');
});

test('weather summaries preserve missing values and do not invent zero readings', () => {
  const records = [
    record('2026-10-30', { temperature: 10, rainfall: 2 }),
    record('2026-10-31', { temperature: null, rainfall: null }),
    record('2026-11-01', { temperature: 20, rainfall: 4 }),
  ];
  const summary = summarizeWeather(records, 'temperature');
  assert.equal(summary.low.date, '2026-10-30');
  assert.equal(summary.high.date, '2026-11-01');
  assert.equal(summary.average, 15);
  assert.equal(summary.count, 2);
  assert.equal(summarizeWeather(records, 'moisture'), null);
  assert.equal(summarizeWeather(records, 'rainfall').total, 6);
});

test('farm outlook uses only the next seven days and actual low temperatures', () => {
  const records = Array.from({ length: 8 }, (_, index) =>
    record(`2026-11-${String(index + 1).padStart(2, '0')}`, {
      temperature: 20,
      low: index - 2,
      rainfall: 1,
    }),
  );
  records[7].low = -50;
  assert.equal(weatherHighlights(records).rainTotal, 7);
  assert.equal(weatherHighlights(records).coolestNight.date, '2026-11-01');
  assert.equal(weatherHighlights([record('2026-11-01', { rainfall: 2 })]).rainTotal, null);
  assert.equal(weatherHighlights([]).rainTotal, null);
  assert.equal(weatherHighlights([]).coolestNight, undefined);
});

test('daily insight responds to the selected day and prioritizes frost, wind, then rain', () => {
  const day = record('2026-10-30', {
    temperature: 26.7,
    low: 14.5,
    rainfall: 0,
    rainChance: 18,
    wind: 11.7,
  });
  assert.equal(getWeatherDayInsight(day, units).title, 'A mostly dry day ahead.');
  assert.equal(
    getWeatherDayInsight({ ...day, rainfall: 21.8, rainChance: 77 }, units).title,
    'Rain shapes the day ahead.',
  );
  assert.equal(
    getWeatherDayInsight({ ...day, wind: 40, rainChance: 80 }, units).title,
    'Wind stands out today.',
  );
  assert.equal(
    getWeatherDayInsight({ ...day, low: 0, wind: 40, rainChance: 80 }, units).title,
    'A freezing night ahead.',
  );
});

test('daily insight gives the same result for equivalent metric and imperial readings', () => {
  const imperial = { ...units, temperature: '°F', wind: 'mph', rainfall: 'in' };
  const day = record('2026-10-30', {
    temperature: 20,
    low: 10,
    rainfall: 0,
    rainChance: 30,
    wind: 10,
  });
  const cases = [
    [
      { ...day, low: -1 },
      { ...day, temperature: 68, low: 30.2 },
    ],
    [
      { ...day, wind: 50 },
      { ...day, temperature: 68, low: 50, wind: 50 / 1.609344 },
    ],
    [
      { ...day, rainfall: 12 },
      { ...day, temperature: 68, low: 50, rainfall: 12 / 25.4 },
    ],
    [
      { ...day, temperature: 31 },
      { ...day, temperature: 87.8, low: 50 },
    ],
  ];
  for (const [metricDay, imperialDay] of cases) {
    assert.deepEqual(
      getWeatherDayInsight(metricDay, units),
      getWeatherDayInsight(imperialDay, imperial),
    );
  }
});

test('daily insight does not infer dry or calm weather from missing readings', () => {
  const missing = record('2026-10-30', { rainChance: null });
  assert.equal(getWeatherDayInsight(missing, units).title, 'More readings are needed.');
  assert.equal(
    getWeatherDayInsight({ ...missing, temperature: 20, rainfall: 0 }, units).title,
    'Your day’s weather outlook.',
  );
});

test('every condition returned by the weather service has its own background scene', () => {
  const conditions = [
    'Clear sky',
    'Partly cloudy',
    'Overcast',
    'Fog',
    'Drizzle',
    'Rain',
    'Snow',
    'Thunderstorm',
    'Unknown conditions',
  ];
  const scenes = conditions.map((condition) => getWeatherScene(condition));
  assert.equal(new Set(scenes.map((scene) => scene.name)).size, conditions.length);
  assert.equal(getWeatherScene('Rain').precipitation, 'rain');
  assert.equal(getWeatherScene('Snow').precipitation, 'snow');
  assert.ok(getWeatherScene('Drizzle').particles < getWeatherScene('Rain').particles);
  assert.ok(getWeatherScene('Drizzle').duration > getWeatherScene('Rain').duration);
});

test('unrecognized conditions use a neutral background without invented weather effects', () => {
  for (const condition of ['', 'New weather condition', 'constructor', '__proto__']) {
    const scene = getWeatherScene(condition);
    assert.equal(scene.name, 'unknown');
    assert.equal(scene.precipitation, null);
    assert.equal(scene.sun, false);
  }
});

test('chart domains include backend risk boundaries and missing values never become zero', async () => {
  const { cropChartDomain, weatherReadingRisk } =
    await import('../src/features/weather/utils/cropRiskPresentation.ts');
  const rows = [record('2026-10-30', { temperature: 18, low: 8 })];
  const bounds = {
    criticalLow: -4,
    goodLow: 8,
    ideal: 18,
    goodHigh: 25,
    criticalHigh: 32,
    unit: '°C',
  };
  const domain = cropChartDomain(rows, 'temperature', bounds);
  assert.ok(domain[0] < -4 && domain[1] > 32);
  assert.equal(weatherReadingRisk(rows[0], 'temperature'), 'unknown');
  const assessed = {
    ...rows[0],
    cropAssessment: { metrics: { temperature: { valueRiskLevel: 'good', lowRiskLevel: 'high' } } },
  };
  assert.equal(weatherReadingRisk(assessed, 'temperature'), 'good');
  assert.equal(weatherReadingRisk(assessed, 'temperature', true), 'high');
});

test('risk gradients follow backend bounds and have continuous, ordered stops', async () => {
  const { cropZoneGradient } =
    await import('../src/features/weather/utils/cropRiskPresentation.ts');
  const bounds = {
    criticalLow: 0,
    goodLow: 8,
    ideal: 18,
    goodHigh: 24,
    criticalHigh: 30,
    unit: '°C',
  };
  const stops = cropZoneGradient(bounds, -4, 34);
  assert.equal(stops[0].offset, 0);
  assert.equal(stops.at(-1).offset, 100);
  assert.ok(stops.every((stop, index) => index === 0 || stop.offset > stops[index - 1].offset));
  assert.equal(
    stops.find((stop) => Math.abs(stop.offset - ((34 - 18) / 38) * 100) < 0.001).color,
    '#aec99c',
  );
  const rainfall = cropZoneGradient(
    {
      ...bounds,
      criticalLow: null,
      goodLow: 0,
      ideal: 2,
      goodHigh: 8,
      criticalHigh: 16,
      unit: 'mm',
    },
    0,
    20,
  );
  assert.equal(rainfall.at(-1).color, '#d9e2bb');
});

test('gradient samples use each day’s backend limits with exact endpoints and interpolated transitions', async () => {
  const { cropBoundsAtPosition, weatherDayBounds, cropChartDomain } =
    await import('../src/features/weather/utils/cropRiskPresentation.ts');
  const normal = {
    unit: '°C',
    criticalLow: 0,
    goodLow: 8,
    ideal: 18,
    goodHigh: 24,
    criticalHigh: 30,
  };
  const humid = {
    ...normal,
    criticalLow: 2,
    goodLow: 9,
    ideal: 17,
    goodHigh: 22,
    criticalHigh: 26,
  };
  const rows = [
    record('2026-10-30', { temperature: 20 }),
    record('2026-10-31', { temperature: 20 }),
  ];
  rows[0].cropAssessment = { bounds: { temperature: normal } };
  rows[1].cropAssessment = { bounds: { temperature: humid } };
  assert.deepEqual(cropBoundsAtPosition(rows, 'temperature', normal, 0), normal);
  assert.deepEqual(cropBoundsAtPosition(rows, 'temperature', normal, 1), humid);
  assert.deepEqual(cropBoundsAtPosition(rows, 'temperature', normal, -1), normal);
  assert.deepEqual(cropBoundsAtPosition(rows, 'temperature', normal, 2), humid);
  const midpoint = cropBoundsAtPosition(rows, 'temperature', normal, 0.5);
  assert.equal(midpoint.criticalHigh, 28);
  assert.equal(midpoint.goodHigh, 23);
  assert.equal(midpoint.criticalLow, 1);
  assert.equal(weatherDayBounds(rows[1], 'temperature', normal).criticalHigh, 26);
  assert.deepEqual(cropBoundsAtPosition([record('2026-10-30')], 'temperature', normal, 0), normal);
  assert.equal(cropBoundsAtPosition([], 'temperature', undefined, 0), undefined);
  assert.equal(
    cropBoundsAtPosition(
      rows.map((row) => ({
        ...row,
        cropAssessment: { bounds: { rainfall: { ...normal, criticalLow: null } } },
      })),
      'rainfall',
      undefined,
      0.5,
    ).criticalLow,
    null,
  );
  const cold = {
    ...rows[1],
    cropAssessment: { bounds: { temperature: { ...humid, criticalLow: -12 } } },
  };
  const domain = cropChartDomain([rows[0], cold], 'temperature', normal);
  assert.ok(domain[0] < -12 && domain[1] > 30);
});

test('crop warnings describe inclusive critical limits and retain backend driver units', async () => {
  const { formatCropAlert, formatCropAlertDrivers } =
    await import('../src/features/weather/utils/cropRiskPresentation.ts');
  const translate = (key, args = {}) => key.replace(/{{(\w+)}}/g, (_, arg) => args[arg]);
  const warning = {
    metric: 'temperature',
    reading: 'value',
    code: 'above_critical',
    value: 86.25,
    boundary: 86.25,
    unit: '°F',
    drivers: [
      { input: 'humidity', value: 95, unit: '%' },
      { input: 'soilPh', value: 7.4, unit: null },
    ],
  };
  assert.match(
    formatCropAlert(warning, units, translate, 'en'),
    /86\.25 °F, at or above 86\.25 °F/,
  );
  assert.equal(
    formatCropAlertDrivers(warning, translate, 'en'),
    'The limit accounts for Humidity (95 %) and Soil pH (7.4).',
  );
  assert.equal(formatCropAlertDrivers({ ...warning, drivers: undefined }, translate, 'en'), null);
});

test('the day outlook renders fragmented deltas and rejects incomplete streams', async (context) => {
  const previousBase = process.env.VITE_API_BASE_URL;
  process.env.VITE_API_BASE_URL = 'http://example.test/api/v1';
  context.after(() => {
    if (previousBase === undefined) {
      delete process.env.VITE_API_BASE_URL;
    } else {
      process.env.VITE_API_BASE_URL = previousBase;
    }
  });

  let complete = true;
  context.mock.method(globalThis, 'fetch', async (url) => {
    assert.equal(new URL(url).searchParams.get('locale'), 'uk-UA');
    const payload = new TextEncoder().encode(
      '{"delta":"Холод."}\n' + (complete ? '{"done":true}\n' : ''),
    );
    return new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(payload.subarray(0, 11));
          controller.enqueue(payload.subarray(11));
          controller.close();
        },
      }),
    );
  });

  const signal = new AbortController().signal;
  const fragments = [];
  await weatherApi.streamInsight('2026-11-10', 'uk-UA', undefined, signal, (text) => {
    fragments.push(text);
  });
  assert.deepEqual(fragments, ['Холод.']);
  complete = false;
  await assert.rejects(
    weatherApi.streamInsight('2026-11-10', 'uk-UA', undefined, signal, () => {}),
    /ended before completion/,
  );
});
