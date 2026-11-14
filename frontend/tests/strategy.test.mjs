import { testFields } from './support/backend.mjs';
import assert from 'node:assert/strict';
import test from 'node:test';
import { planningApi } from '../src/api/planning/planning.api.ts';
import { calendarEventPath } from '../src/features/planning/utils/planningRoutes.ts';
import {
  eventFingerprint,
  getCalendarEvents,
  getEventDecision,
} from '../src/features/planning/utils/eventResponses.ts';

const event = {
  id: '00000000-0000-4000-8000-000000000001',
  fieldId: testFields[0].id,
  date: '2027-05-01',
  title: 'Test work order',
  description: 'Explicit test input',
  duration: '1 hour',
};
const accepted = { [event.id]: { status: 'accepted', fingerprint: eventFingerprint(event) } };

test('unsupplied strategies, rotations and events stay absent instead of creating mock plans', async () => {
  for (const field of testFields) {
    assert.equal(await planningApi.getStrategy(field.id), null);
    assert.equal(await planningApi.getRotation(field.id), null);
    assert.deepEqual(await planningApi.getFieldEvents(field.id), []);
    await assert.rejects(
      planningApi.respondToStrategy({ fieldId: field.id, status: 'accepted' }),
      (error) => error.status === 404,
    );
  }
  assert.deepEqual(await planningApi.getResponses(), {});
});

test('calendar event links preserve the field, date and work order', () => {
  const path = calendarEventPath(event);
  assert.ok(path.startsWith(`/calendar/${event.date}?`));
  const parameters = new URLSearchParams(path.split('?')[1]);
  assert.equal(parameters.get('field'), event.fieldId);
  assert.equal(parameters.get('event'), event.id);
});

test('unanswered events are proposed; reviewed fingerprints accept only unchanged work', () => {
  assert.equal(getEventDecision(event, {}), 'proposed');
  assert.equal(getEventDecision(event, accepted), 'accepted');
  for (const changed of [
    { ...event, date: '2027-06-01' },
    { ...event, title: 'Revised' },
    { ...event, description: 'Changed scope' },
    { ...event, duration: '2 hours' },
  ]) {
    assert.equal(getEventDecision(changed, accepted), 'proposed');
  }
});

test('declines hide only the reviewed event and never suppress another field', () => {
  const other = { ...event, id: '00000000-0000-4000-8000-000000000002', fieldId: testFields[1].id };
  const declined = { [event.id]: { ...accepted[event.id], status: 'declined' } };
  assert.deepEqual(getCalendarEvents([event, other], declined), [other]);
  assert.deepEqual(getCalendarEvents([event, other], {}), [event, other]);
});
