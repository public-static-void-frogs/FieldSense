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
