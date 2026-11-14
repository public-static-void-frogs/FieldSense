import assert from 'node:assert/strict';
import test from 'node:test';
import {
  addFieldSelection,
  getLassoFieldIds,
  isPointInLasso,
  isValidLasso,
  toggleFieldSelection,
} from '../src/features/maps/utils/lassoSelection.ts';
import { catalogPointStyle } from '../src/features/maps/utils/catalogPointStyle.ts';

const square = [
  [0, 0],
  [20, 0],
  [20, 20],
  [0, 20],
];
const field = (id, x, y, kind = 'field') => ({
  type: 'Feature',
  id,
  geometry: { type: 'Point', coordinates: [x, y] },
  properties: { kind, area: 1 },
});
const project = (longitude, latitude) => [longitude, latitude];

test('lasso includes interior and edge points in either drawing direction', () => {
  for (const points of [square, [...square].reverse(), [...square, square[0]]]) {
    for (const point of [
      [10, 10],
      [0, 10],
      [20, 20],
      [0, 0],
    ]) {
      assert.equal(isPointInLasso(point, points), true);
    }
    for (const point of [
      [-1, 10],
      [21, 20],
      [10, 21],
      [NaN, 10],
    ]) {
      assert.equal(isPointInLasso(point, points), false);
    }
  }
});

test('concave lasso excludes points inside its bounding box but outside the loop', () => {
  const concave = [
    [0, 0],
    [30, 0],
    [30, 10],
    [10, 10],
    [10, 30],
    [0, 30],
  ];
  assert.equal(isPointInLasso([5, 25], concave), true);
  assert.equal(isPointInLasso([25, 5], concave), true);
  assert.equal(isPointInLasso([25, 25], concave), false);
});

test('lasso uses projected field positions, deduplicates IDs and never selects clusters', () => {
  const features = [
    field('one', 1, 1),
    field('one', 1, 1),
    field('two', 2, 2),
    field('outside', 8, 8),
    field('cluster', 1, 1, 'cluster'),
  ];
  assert.deepEqual(
    getLassoFieldIds(features, square, (x, y) => [x * 5, y * 5]),
    ['one', 'two'],
  );
});

test('clicks, tiny loops, line strokes and empty areas do not select fields', () => {
  const features = [field('one', 5, 5)];
  for (const points of [
    [],
    [[5, 5]],
    [
      [0, 0],
      [10, 10],
    ],
    [
      [0, 0],
      [10, 10],
      [20, 20],
    ],
    [
      [4, 4],
      [6, 4],
      [5, 6],
    ],
  ]) {
    assert.deepEqual(getLassoFieldIds(features, points, project), []);
  }
  assert.deepEqual(getLassoFieldIds([field('far', 30, 30)], square, project), []);
});

test('self-crossing lassos use even-odd containment rather than canceling their area', () => {
  const bowtie = [
    [0, 0],
    [20, 20],
    [0, 20],
    [20, 0],
  ];
  assert.deepEqual(
    getLassoFieldIds(
      [field('top', 10, 2), field('bottom', 10, 18), field('outside', 1, 10)],
      bowtie,
      project,
    ),
    ['top', 'bottom'],
  );
});

test('click toggles preserve other selections and never mutate the previous set', () => {
  const original = new Set(['first', 'second']);
  const removed = toggleFieldSelection(original, 'first');
  assert.deepEqual([...removed], ['second']);
  const added = toggleFieldSelection(removed, 'third');
  assert.deepEqual([...added], ['second', 'third']);
  assert.deepEqual([...original], ['first', 'second']);
});

test('multiple lassos add fields idempotently while preserving offscreen selections', () => {
  const original = new Set(['offscreen']);
  const first = addFieldSelection(original, ['one', 'two', 'one']);
  const repeated = addFieldSelection(first, ['two', 'three']);
  assert.deepEqual([...repeated], ['offscreen', 'one', 'two', 'three']);
  assert.deepEqual([...original], ['offscreen']);
  assert.deepEqual([...addFieldSelection(repeated, [])], [...repeated]);
});

test('draft selection overrides farm membership styling and clearing restores it', () => {
  assert.deepEqual(catalogPointStyle(true, true), catalogPointStyle(false, true));
  assert.notEqual(
    catalogPointStyle(false, true).fillColor,
    catalogPointStyle(false, false).fillColor,
  );
  assert.notEqual(
    catalogPointStyle(true, false).fillColor,
    catalogPointStyle(false, false).fillColor,
  );
});

test('only completed area gestures can be retained as outlines, including empty selection areas', () => {
  assert.equal(isValidLasso(square), true);
  assert.equal(
    isValidLasso([
      [0, 0],
      [20, 20],
      [0, 20],
      [20, 0],
    ]),
    true,
  );
  assert.deepEqual(getLassoFieldIds([], square, project), []);
  for (const points of [
    [],
    [[1, 1]],
    [
      [0, 0],
      [10, 10],
      [20, 20],
    ],
    [
      [0, 0],
      [1, 0],
      [1, 1],
    ],
  ]) {
    assert.equal(isValidLasso(points), false);
  }
});
