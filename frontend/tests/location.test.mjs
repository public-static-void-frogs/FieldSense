import assert from 'node:assert/strict';
import test from 'node:test';
import { formatLocation, locationPoint } from '../src/features/maps/utils/location.ts';

test('map points wrap longitude to the persisted coordinate range', () => {
  assert.deepEqual(locationPoint(50, 390), { latitude: 50, longitude: 30 });
  assert.deepEqual(locationPoint(-50, -390), { latitude: -50, longitude: -30 });
  assert.equal(locationPoint(0, 180).longitude, -180);
});

test('coordinate labels retain signed latitude and longitude', () => {
  assert.equal(formatLocation({ latitude: -50.4501, longitude: 30.5234 }), '-50.45010, 30.52340');
});
