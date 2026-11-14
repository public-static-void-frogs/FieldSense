import assert from 'node:assert/strict';
import test from 'node:test';
import {
  appendSection,
  cancelSection,
  selectedSectionIds,
  sectionArea,
  sectionCenter,
  toSectionField,
  toggleSectionField,
} from '../src/features/maps/utils/sectionSelection.ts';

const outline = [
  [42, -94],
  [42, -93.99],
  [42.01, -93.99],
  [42.01, -94],
];
const field = (id, coordinates = [-93.995, 42.005]) => ({ id, coordinates });
const section = (id, fields) => ({ id, outline, fields, added: false });
const empty = () => ({ sections: [], looseFields: [], activeId: null });

test('a drawn section retains its outline and transfers loose point membership', () => {
  const previous = { ...empty(), looseFields: [field('one'), field('outside', [-90, 45])] };
  const next = appendSection(previous, section('zone', [field('one'), field('two')]));
  assert.deepEqual([...selectedSectionIds(next)], ['outside', 'one', 'two']);
  assert.deepEqual(next.sections[0].outline, outline);
  assert.deepEqual(
    next.looseFields.map((f) => f.id),
    ['outside'],
  );
  assert.equal(previous.sections.length, 0);
});

test('cancel restores section points while preserving points owned by overlapping sections', () => {
  const state = {
    sections: [
      section('first', [field('shared'), field('only-first')]),
      section('second', [field('shared'), field('only-second')]),
    ],
    looseFields: [field('loose')],
    activeId: 'first',
  };
  const next = cancelSection(state, 'first');
  assert.deepEqual([...selectedSectionIds(next)], ['loose', 'shared', 'only-second']);
  assert.equal(next.activeId, null);
  assert.equal(state.sections.length, 2);
});

test('individual point toggles update membership without deleting the persistent section', () => {
  const original = { ...empty(), sections: [section('zone', [field('one')])], activeId: 'zone' };
  const removed = toggleSectionField(original, field('one'));
  assert.equal(selectedSectionIds(removed).size, 0);
  assert.equal(removed.sections.length, 1);
  assert.deepEqual(removed.sections[0].outline, outline);
  const added = toggleSectionField(removed, field('two'));
  assert.deepEqual(
    added.sections[0].fields.map((f) => f.id),
    ['two'],
  );
  assert.equal(added.looseFields.length, 0);
  const outside = toggleSectionField(added, field('outside', [-90, 45]));
  assert.deepEqual(
    outside.looseFields.map((f) => f.id),
    ['outside'],
  );
});

test('rough area comes from the drawn zone rather than source field acreages', () => {
  const area = sectionArea(section('zone', []));
  assert.ok(area > 90 && area < 95);
  assert.equal(area, sectionArea(section('zone', [field('one'), field('two')])));
  assert.equal(area, sectionArea({ ...section('zone', []), outline: [...outline].reverse() }));
  assert.equal(sectionArea({ outline: [] }), 0);
});

test('Add marker center remains stable for small geographic loops and crossing loops', () => {
  const [lat, lon] = sectionCenter(outline);
  assert.ok(Math.abs(lat - 42.005) < 1e-9);
  assert.ok(Math.abs(lon + 93.995) < 1e-9);
  const crossing = [
    [0, 0],
    [2, 2],
    [0, 2],
    [2, 0],
  ];
  assert.deepEqual(sectionCenter(crossing), [1, 1]);
});

test('selection previews need no source acreage or backend calculations', () => {
  const raw = {
    type: 'Feature',
    id: 'one',
    geometry: { type: 'Point', coordinates: [-93.995, 42.005] },
    properties: { kind: 'field', area: 999999 },
  };
  assert.deepEqual(toSectionField(raw), field('one'));
});
