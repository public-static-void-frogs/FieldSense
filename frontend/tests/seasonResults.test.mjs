import assert from 'node:assert/strict';
import test from 'node:test';
import { rotationAdvicePath } from '../src/api/rotation/rotation.api.ts';
import { rotationQueryKeys } from '../src/api/rotation/rotation.queries.ts';
import { parseSeasons } from '../src/features/rotation/utils/planPresentation.ts';
import {
  formatSeasonResults,
  parseSeasonResults,
  validSeasonResults,
} from '../src/features/rotation/utils/seasonResultsText.ts';

const crops = [
  { id: 'corn', names: ['Corn (grain)', 'Кукурудза (зерно)'] },
  { id: 'soybeans', names: ['Soybeans', 'Соя'] },
  { id: 'winter_wheat', names: ['Winter wheat', 'Озима пшениця'] },
  { id: 'spring_wheat', names: ['Spring wheat', 'Яра пшениця'] },
];
const read = (text) => validSeasonResults(parseSeasonResults(text, crops));

test('pasted seasons are read from spreadsheet rows, commas or spaces, in any column order', () => {
  assert.deepEqual(
    read('Year\tCrop\tYield\n2024\tCorn (grain)\t221\n2023\tsoybean\t70.5\n\n2022;winter wheat;61'),
    [
      { year: 2022, crop: 'winter_wheat', yieldPerAcre: 61 },
      { year: 2023, crop: 'soybeans', yieldPerAcre: 70.5 },
      { year: 2024, crop: 'corn', yieldPerAcre: 221 },
    ],
  );
  assert.deepEqual(read('2025, Соя, 62\ncorn 2024 221 bu/ac\n2023 soybeans 70,5\n2022 corn'), [
    { year: 2022, crop: 'corn' },
    { year: 2023, crop: 'soybeans', yieldPerAcre: 70.5 },
    { year: 2024, crop: 'corn', yieldPerAcre: 221 },
    { year: 2025, crop: 'soybeans', yieldPerAcre: 62 },
  ]);
});

test('rows that cannot be read are reported by line and never saved', () => {
  const rows = parseSeasonResults(
    [
      '2024, corn, 221',
      '1975, corn, 180',
      '2023, wheat, 60',
      '2022, corn, 0',
      '2024, soybeans, 60',
      '2021, corn, 200, 5',
    ].join('\n'),
    crops,
  );
  assert.deepEqual(
    rows.map(({ line, error }) => [line, error]),
    [
      [1, undefined],
      [2, 'year'],
      [3, 'crop'],
      [4, 'yield'],
      [5, 'duplicate'],
      [6, 'yield'],
    ],
  );
  assert.deepEqual(validSeasonResults(rows), [{ year: 2024, crop: 'corn', yieldPerAcre: 221 }]);
});

test('stored seasons are shown as text that reads back to the same seasons', () => {
  const stored = [
    { year: 2024, crop: 'corn', yieldPerAcre: 221.5 },
    { year: 2023, crop: 'soybeans' },
  ];
  const label = (crop) => crops.find(({ id }) => id === crop).names[1];
  const text = formatSeasonResults(stored, label);
  assert.equal(text, '2023, Соя\n2024, Кукурудза (зерно), 221.5');
  assert.deepEqual(read(text), [stored[1], stored[0]]);
});

test('the plan length is part of the advice request and of its cache key', () => {
  assert.equal(
    rotationAdvicePath({ fieldId: 'f1', crop: 'corn', priorities: ['soil'], seasons: 4 }),
    '/fields/f1/rotation-advice?crop=corn&priorities=soil&seasons=4',
  );
  assert.equal(rotationAdvicePath({ fieldId: 'f1', priorities: [] }), '/fields/f1/rotation-advice');
  assert.equal(parseSeasons('4'), 4);
  assert.equal(parseSeasons('9'), undefined);
  assert.equal(parseSeasons(null), undefined);
  const three = rotationQueryKeys.advice({ fieldId: 'f1', priorities: [], seasons: 3 });
  const four = rotationQueryKeys.advice({ fieldId: 'f1', priorities: [], seasons: 4 });
  assert.notDeepEqual(three, four);
  // Saving the farmer's results or soil test invalidates this prefix, and with it the advice.
  assert.deepEqual(
    three.slice(0, rotationQueryKeys.field('f1').length),
    rotationQueryKeys.field('f1'),
  );
});
