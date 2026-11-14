import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';
import { filterFields, filterLandHistory } from '../src/features/fields/utils/fieldFilters.ts';
import { getNitrogenAssessment } from '../src/features/fields/utils/fieldPresentation.ts';
import { parcelStyle } from '../src/features/maps/utils/mapStyles.ts';
import { getFarmSummary } from '../src/features/overview/utils/farmSummary.ts';
import {
  countEventDecisions,
  filterCalendarEvents,
  getEventUrgencyColor,
  getStrategyDecision,
} from '../src/features/planning/utils/eventPresentation.ts';
import { eventFingerprint } from '../src/features/planning/utils/eventResponses.ts';
import {
  getWeatherChange,
  selectWeatherReading,
} from '../src/features/weather/utils/weatherPresentation.ts';
import { getPagination } from '../src/utils/pagination.ts';

const fields = [
  {
    id: '00000000-0000-4000-8000-000000000001',
    parcelId: 1,
    name: 'North Meadow',
    crop: 'Corn',
    area: 25,
    health: 70,
    moisture: 40,
    nitrogen: 30,
    status: 'Healthy',
  },
  {
    id: '00000000-0000-4000-8000-000000000002',
    parcelId: 2,
    name: 'East Ridge',
    crop: 'Soybeans',
    area: 30,
    health: 50,
    moisture: 39,
    nitrogen: 19,
    status: 'Critical',
  },
  {
    id: '00000000-0000-4000-8000-000000000003',
    parcelId: 3,
    name: 'South Field',
    crop: 'Corn',
    area: 10,
    health: 69,
    moisture: 60,
    nitrogen: 29,
    status: 'Needs attention',
  },
];
const filters = {
  overview: false,
  query: '',
  status: 'All fields',
  crop: 'All crops',
  filters: [],
};
const ids = (values) => values.map((value) => value.id);

test('field search, attention tabs and combined filters preserve their distinct rules', () => {
  assert.deepEqual(ids(filterFields(fields, { ...filters, query: '  FIELD02 ' })), [fields[1].id]);
  assert.deepEqual(ids(filterFields(fields, { ...filters, status: 'Needs attention' })), [
    fields[1].id,
    fields[2].id,
  ]);
  assert.deepEqual(ids(filterFields(fields, { ...filters, status: 'Critical' })), [fields[1].id]);
  assert.deepEqual(
    ids(
      filterFields(fields, {
        ...filters,
        filters: ['crop:Corn', 'crop:Soybeans', 'health:low', 'area:large'],
      }),
    ),
    [fields[1].id],
  );
  assert.deepEqual(ids(filterFields(fields, { ...filters, filters: ['moisture:low'] })), [
    fields[1].id,
  ]);
  assert.deepEqual(ids(filterFields(fields, { ...filters, filters: ['area:large'] })), [
    fields[0].id,
    fields[1].id,
  ]);
});

test('overview searches names and uses its single crop selector', () => {
  assert.deepEqual(ids(filterFields(fields, { ...filters, overview: true, crop: 'Corn' })), [
    fields[0].id,
    fields[2].id,
  ]);
  assert.deepEqual(filterFields(fields, { ...filters, overview: true, query: 'Soybeans' }), []);
  assert.deepEqual(ids(filterFields(fields, { ...filters, overview: true, query: 'meadow' })), [
    fields[0].id,
  ]);
});

test('land history combines category, year and measurement search without reordering events', () => {
  const events = [
    {
      id: 'a',
      date: '2026-05-23',
      category: 'Soil conditions',
      title: 'Sample',
      description: 'Topsoil',
      measurements: ['Nitrogen 19 mg/kg'],
    },
    {
      id: 'b',
      date: '2025-05-23',
      category: 'Soil conditions',
      title: 'Sample',
      description: 'Topsoil',
    },
    { id: 'c', date: '2026-04-23', category: 'Field work', title: 'Planted', description: 'Corn' },
  ];
  assert.deepEqual(ids(filterLandHistory(events, 'Soil conditions', '2026', 'NITROGEN')), ['a']);
  assert.deepEqual(ids(filterLandHistory(events, 'All activities', 'All years', '')), [
    'a',
    'b',
    'c',
  ]);
});

test('pagination clamps a stale page after filtering and reports empty and partial pages', () => {
  assert.deepEqual(getPagination(0, 4, 10), { currentPage: 1, first: 0, last: 0 });
  assert.deepEqual(getPagination(12, 4, 10), { currentPage: 2, first: 11, last: 12 });
  assert.deepEqual(getPagination(20, 2, 10), { currentPage: 2, first: 11, last: 20 });
});

test('field presentation uses the original nitrogen and map moisture thresholds', () => {
  assert.equal(getNitrogenAssessment(19).label, 'Very low');
  assert.equal(getNitrogenAssessment(20).label, 'Low');
  assert.equal(getNitrogenAssessment(30).label, 'Adequate');
  assert.equal(parcelStyle(fields[1], 'Soil moisture').color, '#dbe5b2');
  assert.equal(parcelStyle(fields[0], 'Soil moisture').color, '#9bcdd9');
  assert.equal(parcelStyle(fields[2], 'Soil moisture').color, '#61b4d4');
  assert.equal(parcelStyle(fields[1], 'Crop health').color, '#e7aa66');
  assert.equal(parcelStyle(fields[1], 'Field locations').fillOpacity, 0.8);
  assert.equal(parcelStyle(undefined, 'Crop health').fillOpacity, 0.65);
});

const events = [
  {
    id: 'soil',
    fieldId: fields[0].id,
    date: '2026-05-25',
    title: 'Soil review',
    fieldName: 'North Meadow',
    category: 'Soil check',
    description: 'Inspect nutrients',
    priority: 'Routine',
  },
  {
    id: 'water',
    fieldId: fields[1].id,
    date: '2026-06-15',
    title: 'Water review',
    fieldName: 'East Ridge',
    category: 'Irrigation',
    description: 'Inspect water',
    priority: 'High priority',
  },
];

test('strategy totals handle mixed, stale and absent responses', () => {
  const accepted = {
    [events[0].id]: { status: 'accepted', fingerprint: eventFingerprint(events[0]) },
  };
  const mixed = {
    ...accepted,
    [events[1].id]: { status: 'declined', fingerprint: eventFingerprint(events[1]) },
  };
  assert.equal(getStrategyDecision([], {}), 'proposed');
  assert.equal(getStrategyDecision(events, mixed), 'proposed');
  assert.equal(getStrategyDecision([events[0]], mixed), 'accepted');
  assert.deepEqual(countEventDecisions(events, mixed), { accepted: 1, declined: 1, proposed: 0 });
  assert.equal(getStrategyDecision([{ ...events[0], date: '2026-05-26' }], mixed), 'proposed');
});

test('calendar filters intersect field, category and search; urgency prefers high priority', () => {
  assert.deepEqual(ids(filterCalendarEvents(events, fields[0].id, 'Soil check', 'NUTRIENTS')), [
    'soil',
  ]);
  assert.deepEqual(filterCalendarEvents(events, fields[1].id, 'Soil check', ''), []);
  assert.equal(getEventUrgencyColor(events[0], '2026-05-24'), 'warning');
  assert.equal(getEventUrgencyColor(events[1], '2026-05-24'), 'error');
  assert.equal(
    getEventUrgencyColor({ ...events[1], priority: 'Routine' }, '2026-05-24'),
    'default',
  );
});

test('weather selection falls back after a range change and compares the previous day', () => {
  const records = [
    { key: 0, rainfall: 0 },
    { key: 1, rainfall: 6.4 },
  ];
  assert.equal(selectWeatherReading(records, 40), records[0]);
  assert.equal(selectWeatherReading(records, 1), records[1]);
  assert.equal(getWeatherChange(records, records[0], 'rainfall'), -6.4);
  assert.equal(getWeatherChange(records, records[1], 'rainfall'), null);
});

test('farm summary counts critical fields within the attention total', () => {
  assert.deepEqual(getFarmSummary(fields), { totalArea: 65, attentionCount: 2, criticalCount: 1 });
  assert.deepEqual(getFarmSummary([]), { totalArea: 0, attentionCount: 0, criticalCount: 0 });
});

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const paths = await Promise.all(
    entries.map((entry) => {
      const path = `${directory}/${entry.name}`;
      return entry.isDirectory() ? sourceFiles(path) : [path];
    }),
  );
  return paths.flat().filter((path) => /\.tsx?$/.test(path));
}

test('application source has no nested or chained ternary expressions', async () => {
  const violations = [];
  for (const file of await sourceFiles(new URL('../src', import.meta.url).pathname)) {
    const source = ts.createSourceFile(
      file,
      await readFile(file, 'utf8'),
      ts.ScriptTarget.Latest,
      true,
    );
    function visit(node, insideConditional = false) {
      const conditional = ts.isConditionalExpression(node);
      if (conditional && insideConditional) {
        const { line } = source.getLineAndCharacterOfPosition(node.getStart());
        violations.push(`${file}:${line + 1}`);
      }
      ts.forEachChild(node, (child) => visit(child, insideConditional || conditional));
    }
    visit(source);
  }
  assert.deepEqual(violations, []);
});
