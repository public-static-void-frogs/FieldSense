import assert from 'node:assert/strict';
import test from 'node:test';

const planningToday = '2026-05-24'; // Explicit unit-test reference date, not the live planning clock.
import { getEventStatus, isPlanDate } from '../src/features/planning/utils/planningDates.ts';

test('calendar date validation rejects impossible or incomplete dates', () => {
  assert.equal(isPlanDate('2027-05-02'), true);
  assert.equal(isPlanDate('2027-02-30'), false);
  assert.equal(isPlanDate('2027-13-01'), false);
  assert.equal(isPlanDate('2027-5-2'), false);
  assert.equal(isPlanDate(undefined), false);
});

test('action statuses use the shared planning clock and seven-day window', () => {
  assert.equal(getEventStatus('2026-05-23', planningToday), 'Completed');
  assert.equal(getEventStatus('2026-05-25', planningToday), 'Due soon');
  assert.equal(getEventStatus('2026-05-31', planningToday), 'Due soon');
  assert.equal(getEventStatus('2026-06-01', planningToday), 'Planned');
});

test('the calendar opens on today when this month has actions, else on the next upcoming one', async () => {
  const { defaultCalendarDate } = await import('../src/features/planning/utils/planningDates.ts');
  assert.equal(defaultCalendarDate(['2026-11-20'], '2026-11-15'), '2026-11-15');
  assert.equal(
    defaultCalendarDate(['2026-03-02', '2027-02-01', '2027-01-10'], '2026-11-15'),
    '2027-01-10',
  );
  assert.equal(defaultCalendarDate(['2026-03-02'], '2026-11-15'), '2026-11-15');
  assert.equal(defaultCalendarDate([], '2026-11-15'), '2026-11-15');
});
