import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fieldInsightsApi } from '../src/api/fields/field-insights.api.ts';
import {
  m2Crops,
  m2Outcomes,
  m2Treatments,
  m2Verdicts,
} from '../src/features/fields/constants/m2Insights.constants.ts';
import { insightSigned } from '../src/features/fields/utils/fieldInsightFormats.ts';
import { m2Range } from '../src/features/fields/utils/m2Range.ts';

const readLocale = (language) =>
  JSON.parse(
    readFileSync(new URL(`../src/i18n/locales/${language}.json`, import.meta.url), 'utf8'),
  );

test('the m2 request targets the field endpoint', async (t) => {
  const previous = process.env.VITE_API_BASE_URL;
  process.env.VITE_API_BASE_URL = 'http://api.example.test/api/v1/';
  t.after(() => {
    if (previous === undefined) {
      delete process.env.VITE_API_BASE_URL;
    } else {
      process.env.VITE_API_BASE_URL = previous;
    }
  });
  t.mock.method(globalThis, 'fetch', async (url) => {
    assert.equal(url, 'http://api.example.test/api/v1/fields/f1/m2-insights');
    return Response.json({ ok: true });
  });
  assert.deepEqual(await fieldInsightsApi.m2('f1', new AbortController().signal), { ok: true });
});

test('signed values keep their sign, drop zero and handle missing data', () => {
  assert.equal(insightSigned(-0.05, 'en'), '-0.05');
  assert.equal(insightSigned(0.0123456, 'en'), '+0.012');
  assert.equal(insightSigned(0, 'en'), '0');
  assert.equal(insightSigned(null, 'en'), '—');
});

test('drought and pooled estimates use their own intervals on a scale centred on zero', () => {
  const headline = {
    gamma: 0,
    gamma_lo: -2,
    gamma_hi: 4,
    headline_effect: -6,
    headline_lo: -8,
    headline_hi: -4,
  };
  const drought = m2Range(headline);
  assert.equal(drought.estimate, 0);
  assert.equal(drought.position(0), 50);
  assert.deepEqual(drought.interval, { low: -2, high: 4 });
  assert.equal(drought.position(drought.interval.low), 25);
  assert.equal(drought.position(drought.interval.high), 100);

  const pooled = m2Range({ ...headline, gamma: null });
  assert.deepEqual(pooled.interval, { low: -8, high: -4 });
  assert.equal(pooled.position(pooled.estimate), 12.5);
});

test('normal-season gaps share the drought scale and can extend it beyond the interval', () => {
  const headline = { gamma: 2, gamma_lo: 1, gamma_hi: 3, theta_normal: -6, headline_effect: 2 };
  const drought = m2Range(headline);
  assert.equal(drought.limit, 6);
  assert.equal(drought.position(drought.normalGap), 0);
  assert.equal(drought.position(drought.interval.high), 75);
  assert.equal(m2Range({ ...headline, theta_normal: 0 }).normalGap, 0);
  assert.equal(m2Range({ ...headline, gamma: null }).normalGap, null);
});

test('incomplete intervals do not draw an invented range', () => {
  const headline = { gamma: null, headline_effect: 0, headline_lo: null, headline_hi: 0 };
  const range = m2Range(headline);
  assert.equal(range.interval, null);
  assert.equal(range.position(range.estimate), 50);
  assert.equal(m2Range({ ...headline, headline_effect: null }), null);
});

test('every phrase the evidence timeline translates dynamically exists in both catalogs', () => {
  const en = readLocale('en');
  const uk = readLocale('uk');
  const phrases = [
    ...Object.values(m2Crops),
    ...Object.values(m2Treatments),
    ...Object.values(m2Outcomes),
    ...Object.values(m2Verdicts).map((verdict) => verdict.label),
  ];
  for (const phrase of phrases) {
    assert.equal(en[phrase], phrase, `English catalog: ${phrase}`);
    assert.ok(uk[phrase]?.trim(), `Ukrainian catalog: ${phrase}`);
  }
});

test('every backend verdict has a label', () => {
  const backend = readFileSync(
    new URL('../../backend/app/services/m2_lookup.py', import.meta.url),
    'utf8',
  );
  const verdicts = backend.match(/VERDICT_RANK = \{([^}]*)\}/s)[1];
  for (const [, key] of verdicts.matchAll(/"([^"]+)":/g)) {
    assert.ok(m2Verdicts[key], key);
  }
});
