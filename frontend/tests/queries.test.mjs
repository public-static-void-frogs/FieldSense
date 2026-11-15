import { testFields } from './support/backend.mjs';
import assert from 'node:assert/strict';
import test from 'node:test';
import { readdir, readFile } from 'node:fs/promises';
import { farmQueries } from '../src/api/farm/farm.queries.ts';
import { settingsMutations } from '../src/api/settings/settings.mutations.ts';
import { hashKey, QueryObserver } from '@tanstack/react-query';
import { createQueryClient } from '../src/api/core/query-client.ts';
import { fieldsApi } from '../src/api/fields/fields.api.ts';
import { cropHistoryQueries } from '../src/api/fields/crop-history.queries.ts';
import { fieldQueries, fieldQueryKeys } from '../src/api/fields/fields.queries.ts';
import { fieldMutations } from '../src/api/fields/fields.mutations.ts';
import { mapQueries, mapQueryKeys } from '../src/api/maps/maps.queries.ts';
import { mapsApi } from '../src/api/maps/maps.api.ts';
import { rotationMutations } from '../src/api/rotation/rotation.mutations.ts';
import { rotationQueries } from '../src/api/rotation/rotation.queries.ts';
import { weatherQueries, weatherQueryKeys } from '../src/api/weather/weather.queries.ts';
import { settingsApi } from '../src/api/settings/settings.api.ts';
import {
  clusterView,
  normalizeViewport,
  parseMapPosition,
} from '../src/features/maps/utils/catalogViewport.ts';

const viewport = { bounds: [-93.76, 42.03, -93.72, 42.06], zoom: 15 };
const [first, second] = testFields;
const weatherLocation = await settingsApi.get();
function client() {
  const cache = createQueryClient();
  cache.setDefaultOptions({
    queries: { retry: false, staleTime: 60_000 },
    mutations: { retry: false },
  });
  return cache;
}

test('map keys include bounds and zoom; normalized requests are stable and clamped', () => {
  const keys = [
    mapQueryKeys.summary(),
    mapQueryKeys.geojson(viewport),
    mapQueryKeys.geojson({ ...viewport, zoom: 10 }),
    mapQueryKeys.geojson({ ...viewport, bounds: [30, 50, 31, 51] }),
    fieldQueryKeys.catalogById(first.id),
    fieldQueryKeys.byId(first.id),
  ];
  assert.equal(new Set(keys.map(hashKey)).size, keys.length);
  assert.deepEqual(normalizeViewport(-200, -100, 200, 100, 14.9), {
    bounds: [-180, -90, 180, 90],
    zoom: 14,
  });
  assert.equal(
    hashKey(
      mapQueryKeys.geojson(
        normalizeViewport(-93.76000001, 42.03000001, -93.72000001, 42.06000001, 15),
      ),
    ),
    hashKey(mapQueryKeys.geojson(viewport)),
  );
});

test('concurrent map consumers deduplicate requests and reuse fresh data', async () => {
  const cache = client();
  let requests = 0;
  const options = {
    ...mapQueries.geojson(viewport),
    queryFn: () => {
      requests++;
      return mapsApi.getGeoJson(viewport);
    },
  };
  const [a, b] = await Promise.all([cache.fetchQuery(options), cache.fetchQuery(options)]);
  assert.deepEqual(a, b);
  await cache.fetchQuery(options);
  assert.equal(requests, 1);
  cache.clear();
});

test('viewport changes keep the previous map while the next area loads', async () => {
  const cache = client();
  const options = mapQueries.geojson(viewport);
  const previous = await cache.fetchQuery(options);
  const observer = new QueryObserver(cache, options);
  const unsubscribe = observer.subscribe(() => {});
  let finish;
  const pending = new Promise((resolve) => {
    finish = resolve;
  });
  try {
    const next = {
      ...mapQueries.geojson({ bounds: [30, 50, 31, 51], zoom: 12 }),
      queryFn: () => pending,
    };
    observer.setOptions(next);
    assert.strictEqual(observer.getCurrentResult().data, previous);
    assert.equal(observer.getCurrentResult().isPlaceholderData, true);
    finish({ type: 'FeatureCollection', mode: 'fields', total: 0, features: [] });
    await cache.fetchQuery(next);
    assert.equal(observer.getCurrentResult().data.features.length, 0);
  } finally {
    unsubscribe();
    cache.clear();
  }
});

test('canceled viewport reads reject; valid empty areas do not fall back to a full catalog', async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    mapsApi.getGeoJson(viewport, controller.signal),
    (error) => error.name === 'AbortError',
  );
  const empty = await mapsApi.getGeoJson({ bounds: [0, 0, 1, 1], zoom: 15 });
  assert.deepEqual(empty.features, []);
});

test('select/remove mutations refresh map and selected-field caches while preserving the catalog', async () => {
  const cache = client();
  await fieldsApi.remove(first.id);
  await Promise.all([
    cache.fetchQuery(mapQueries.geojson(viewport)),
    cache.fetchQuery(fieldQueries.list()),
  ]);
  const unsubscribe = cache.getQueryCache().subscribe(() => {});
  try {
    await cache.getMutationCache().build(cache, fieldMutations.select(cache)).execute(first.id);
    assert.equal(cache.getQueryState(mapQueryKeys.geojson(viewport)).isInvalidated, true);
    assert.equal(cache.getQueryState(fieldQueryKeys.list()).isInvalidated, true);
    const selectedMap = await cache.fetchQuery(mapQueries.geojson(viewport));
    assert.equal(
      selectedMap.features.find((feature) => feature.id === first.id).properties.fieldId,
      first.id,
    );
    await cache.getMutationCache().build(cache, fieldMutations.remove(cache)).execute(first.id);
    assert.equal(await fieldsApi.getById(first.id), null);
    assert.equal((await fieldsApi.getCatalogById(first.id)).id, first.id);
    const removedMap = await cache.fetchQuery(mapQueries.geojson(viewport));
    assert.equal(
      removedMap.features.find((feature) => feature.id === first.id).properties.fieldId,
      undefined,
    );
    await fieldsApi.select(first.id);
  } finally {
    unsubscribe();
    cache.clear();
  }
});

test('field-scoped weather uses supplied soil and crop data in independent caches', async () => {
  const cache = client();
  try {
    const [a, b] = await Promise.all([
      cache.fetchQuery(weatherQueries.forecast(weatherLocation, first.id)),
      cache.fetchQuery(weatherQueries.forecast(weatherLocation, second.id)),
    ]);
    assert.equal(a.cropAssessment.context.fieldId, first.id);
    assert.equal(b.cropAssessment.context.fieldId, second.id);
    assert.notEqual(a.cropAssessment.context.crop, b.cropAssessment.context.crop);
    assert.notEqual(
      hashKey(weatherQueryKeys.forecast(weatherLocation, first.id)),
      hashKey(weatherQueryKeys.forecast(weatherLocation, second.id)),
    );
  } finally {
    cache.clear();
  }
});

test('saving prices and costs keeps calculator defaults available throughout the refresh', async () => {
  const cache = client();
  const options = rotationQueries.economics(first.id);
  const adviceOptions = rotationQueries.advice({ fieldId: first.id, priorities: [], seasons: 1 });
  const initial = await cache.fetchQuery(options);
  cache.setQueryData(adviceOptions.queryKey, null);
  const snapshots = [];
  const observer = new QueryObserver(cache, options);
  const unsubscribe = observer.subscribe(({ data }) => snapshots.push(data));
  const inputs = { crops: [{ crop: 'corn', priceUsd: 6.25, costUsdPerAcre: 510 }] };

  try {
    const mutation = cache
      .getMutationCache()
      .build(cache, rotationMutations.saveEconomics(cache, first.id));
    await mutation.execute({ fieldId: first.id, inputs });
    assert.ok(snapshots.length > 0);
    for (const snapshot of snapshots) {
      assert.deepEqual(snapshot.defaults, initial.defaults);
    }
    assert.deepEqual(observer.getCurrentResult().data.inputs.crops, inputs.crops);
    assert.equal(cache.getQueryState(adviceOptions.queryKey).isInvalidated, true);
  } finally {
    unsubscribe();
    cache.clear();
  }
});

test('canceling custom metrics clears all saved inputs for that field and invalidates its advice', async () => {
  const cache = client();
  const fieldId = second.id;
  const execute = (options, input) => cache.getMutationCache().build(cache, options).execute(input);
  const adviceOptions = rotationQueries.advice({ fieldId, priorities: [], seasons: 1 });

  try {
    await execute(rotationMutations.saveSeasonResults(cache, fieldId), {
      fieldId,
      results: [{ year: 2025, crop: 'corn', yieldPerAcre: 200 }],
    });
    await execute(rotationMutations.saveSoilSurvey(cache, fieldId), { fieldId, survey: { ph: 6 } });
    await execute(rotationMutations.saveEconomics(cache, fieldId), {
      fieldId,
      inputs: { landRentUsdPerAcre: 0, crops: [] },
    });
    cache.setQueryData(adviceOptions.queryKey, null);

    await execute(rotationMutations.resetInputs(cache, fieldId), fieldId);

    assert.equal(cache.getQueryState(adviceOptions.queryKey).isInvalidated, true);
    const [seasons, soil, economics] = await Promise.all([
      cache.fetchQuery(rotationQueries.seasonResults(fieldId)),
      cache.fetchQuery(rotationQueries.soilSurvey(fieldId)),
      cache.fetchQuery(rotationQueries.economics(fieldId)),
    ]);
    assert.deepEqual(seasons.results, []);
    assert.equal(soil, null);
    assert.equal(economics.inputs, null);
    assert.ok(economics.defaults.crops.length > 0);
  } finally {
    cache.clear();
  }
});

test('map links restore valid positions while invalid query values use the default view', () => {
  assert.deepEqual(parseMapPosition(new URLSearchParams('lat=42.05&lon=-93.87&zoom=14')), {
    center: [42.05, -93.87],
    zoom: 14,
  });
  for (const value of [
    '',
    'lat=42&lon=1',
    'lat=&lon=0&zoom=14',
    'lat=nan&lon=1&zoom=14',
    'lat=90&lon=0&zoom=14',
    'lat=0&lon=181&zoom=14',
    'lat=0&lon=0&zoom=25',
  ]) {
    assert.equal(parseMapPosition(new URLSearchParams(value)), null);
  }
});

test('weather ranges have independent caches and failed queries can be retried', async () => {
  const cache = client();
  const [week, month] = await Promise.all([
    cache.fetchQuery(weatherQueries.history(weatherLocation, { range: '7 days' })),
    cache.fetchQuery(weatherQueries.history(weatherLocation, { range: '30 days' })),
  ]);
  assert.equal(week.records.length, 7);
  assert.equal(month.records.length, 30);
  await assert.rejects(
    cache.fetchQuery({
      queryKey: ['test', 'recovery'],
      queryFn: () => Promise.reject(new Error('Unavailable')),
    }),
  );
  assert.equal(
    await cache.fetchQuery({
      queryKey: ['test', 'recovery'],
      queryFn: () => Promise.resolve('recovered'),
    }),
    'recovered',
  );
  cache.clear();
});

async function sourceFiles(directory) {
  const paths = await Promise.all(
    (await readdir(directory, { withFileTypes: true })).map((entry) =>
      entry.isDirectory()
        ? sourceFiles(`${directory}/${entry.name}`)
        : [`${directory}/${entry.name}`],
    ),
  );
  return paths.flat().filter((path) => /\.tsx?$/.test(path));
}

test('UI does not import mock implementations', async () => {
  for (const file of await sourceFiles(new URL('../src', import.meta.url).pathname)) {
    const source = await readFile(file, 'utf8');
    if (!file.includes('/api/')) {
      assert.doesNotMatch(source, /(?:from\s*|import\s*\()['"][^'"]*\/mocks\//, file);
    }
  }
});

test('weather caches isolate coordinates, dates and units; settings changes clear old weather', async () => {
  assert.notEqual(
    hashKey(weatherQueryKeys.current(weatherLocation)),
    hashKey(weatherQueryKeys.current({ ...weatherLocation, longitude: 10 })),
  );
  assert.notEqual(
    hashKey(weatherQueryKeys.forecast(weatherLocation)),
    hashKey(weatherQueryKeys.forecast({ ...weatherLocation, units: 'imperial' })),
  );
  const cache = client();
  await cache.fetchQuery(weatherQueries.current(weatherLocation));
  await cache.fetchQuery(farmQueries.profile());
  const history = await cache.fetchQuery(
    weatherQueries.history(weatherLocation, { startDate: '2025-07-01', endDate: '2025-07-07' }),
  );
  assert.equal(history.records[0].date, '2025-07-07');
  const updated = { ...weatherLocation, longitude: 20, location: 'New location' };
  try {
    await cache.getMutationCache().build(cache, settingsMutations.update(cache)).execute(updated);
    assert.equal(cache.getQueryData(weatherQueryKeys.current(weatherLocation)), undefined);
    const result = await cache.fetchQuery(weatherQueries.current(updated));
    assert.equal(result.longitude, 20);
    assert.equal(result.location, 'New location');
  } finally {
    await settingsApi.update(weatherLocation);
    cache.clear();
  }
});

test('history observer keeps its data while a different date range is fetching', async () => {
  const cache = client();
  const weekOptions = weatherQueries.history(weatherLocation, { range: '7 days' }, first.id);
  const week = { records: [{ date: '2026-10-29' }] };
  cache.setQueryData(weekOptions.queryKey, week);
  const observer = new QueryObserver(cache, weekOptions);
  const unsubscribe = observer.subscribe(() => {});
  try {
    for (const period of [
      { range: '30 days' },
      { startDate: '2026-09-01', endDate: '2026-09-15' },
    ]) {
      const previous = observer.getCurrentResult().data;
      let resolve;
      const pending = new Promise((done) => {
        resolve = done;
      });
      const options = {
        ...weatherQueries.history(weatherLocation, period, first.id),
        queryFn: () => pending,
      };
      observer.setOptions(options);
      assert.strictEqual(observer.getCurrentResult().data, previous);
      assert.equal(observer.getCurrentResult().isPlaceholderData, true);
      assert.equal(observer.getCurrentResult().fetchStatus, 'fetching');
      const replacement = { records: [{ date: '2026-09-15' }], period };
      resolve(replacement);
      await cache.fetchQuery(options);
      assert.deepEqual(observer.getCurrentResult().data, replacement);
      assert.equal(observer.getCurrentResult().isPlaceholderData, false);
    }
  } finally {
    unsubscribe();
    cache.clear();
  }
});

test('history placeholder never carries readings into a different field, location or unit system', () => {
  const cache = client();
  const options = weatherQueries.history(weatherLocation, { range: '7 days' }, first.id);
  cache.setQueryData(options.queryKey, { records: [{ date: '2026-10-29' }] });
  const observer = new QueryObserver(cache, options);
  const unsubscribe = observer.subscribe(() => {});
  try {
    for (const [location, fieldId] of [
      [weatherLocation, second.id],
      [{ ...weatherLocation, latitude: weatherLocation.latitude + 1 }, first.id],
      [{ ...weatherLocation, units: 'imperial' }, first.id],
    ]) {
      observer.setOptions(options);
      observer.setOptions({
        ...weatherQueries.history(location, { range: '30 days' }, fieldId),
        queryFn: () => new Promise(() => {}),
      });
      assert.equal(observer.getCurrentResult().data, undefined);
      assert.equal(observer.getCurrentResult().isPlaceholderData, false);
    }
  } finally {
    unsubscribe();
    cache.clear();
  }
});

test('field responses are detached and canceled field reads reject', async () => {
  const fields = await fieldsApi.getAll();
  fields[0].name = 'Modified outside the API';
  assert.equal((await fieldsApi.getById(first.id)).name, first.name);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(fieldsApi.getAll(controller.signal), (error) => error.name === 'AbortError');
});

test('a dense group always drills down even when its full bounds would fit the current zoom', () => {
  const group = [-93.95, 42.0, -93.86, 42.044];
  assert.equal(clusterView(group, 13).zoom, 15);
  assert.deepEqual(clusterView(group, 11).center, [42.022, -93.905]);
  assert.equal(clusterView(group, 18).zoom, 19);
});

test('crop history retains the previous parcel as placeholder while fetching the next parcel', async () => {
  const cache = client();
  const previous = cropHistoryQueries.point(first.id, 0, 'first-parcel', null);
  const next = cropHistoryQueries.point(first.id, 1, 'second-parcel', null);
  const previousData = { coordinates: [-93.75, 42.04], years: [{ year: 2025, crop: null }] };
  const nextData = { ...previousData, coordinates: [-93.7, 42.02] };
  cache.setQueryData(previous.queryKey, previousData);
  const observer = new QueryObserver(cache, previous);
  const unsubscribe = observer.subscribe(() => {});
  try {
    let finish;
    observer.setOptions({
      ...next,
      queryFn: () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    });
    assert.equal(observer.getCurrentResult().isPlaceholderData, true);
    assert.deepEqual(observer.getCurrentResult().data, previousData);
    assert.equal(cache.getQueryData(next.queryKey), undefined);
    finish(nextData);
    await cache.getQueryCache().find({ queryKey: next.queryKey }).promise;
    assert.equal(observer.getCurrentResult().isPlaceholderData, false);
    assert.deepEqual(observer.getCurrentResult().data, nextData);
  } finally {
    unsubscribe();
    cache.clear();
  }
});
