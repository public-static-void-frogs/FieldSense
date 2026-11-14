import assert from 'node:assert/strict';
import test from 'node:test';
import {
  formValuesFrom,
  isSectionDirty,
  settingsForSection,
} from '../src/features/settings/utils/settingsForm.ts';

const profile = {
  fullName: 'Test Farmer',
  email: 'farmer@example.com',
  initials: 'TF',
  role: 'Farm owner',
  farmName: 'Saved farm',
  season: '2026',
  availableSeasons: ['2026', '2025'],
  location: '50.45010, 30.52340',
  locationLabel: '50.45010, 30.52340',
  latitude: 50.4501,
  longitude: 30.5234,
  timeZone: 'Europe/Kyiv',
  units: 'metric',
  theme: 'light',
  language: 'en',
  sessionLifetimeHours: 24,
};
const sections = ['account', 'preferences', 'farm', 'location'];

test('sections start clean and reverting a field makes its section clean again', () => {
  const saved = formValuesFrom(profile);
  const values = { ...saved };
  for (const section of sections) {
    assert.equal(isSectionDirty(section, values, saved), false);
  }
  values.fullName = 'Changed Farmer';
  assert.equal(isSectionDirty('account', values, saved), true);
  for (const section of ['preferences', 'farm', 'location']) {
    assert.equal(isSectionDirty(section, values, saved), false);
  }
  values.fullName = saved.fullName;
  assert.equal(isSectionDirty('account', values, saved), false);
});

test('map selection dirties only location, including zero coordinates', () => {
  const saved = formValuesFrom({ ...profile, latitude: null, longitude: null, location: '' });
  const changed = { ...saved, latitude: 0, longitude: 0, location: '0.00000, 0.00000' };
  assert.equal(isSectionDirty('location', changed, saved), true);
  assert.equal(isSectionDirty('farm', changed, saved), false);
  assert.equal(isSectionDirty('preferences', changed, saved), false);
});

test('saving location excludes unsaved farm and application changes from the request', () => {
  const changed = {
    ...formValuesFrom(profile),
    farmName: 'Unsaved farm',
    units: 'imperial',
    latitude: 49.8397,
    longitude: 24.0297,
    location: '49.83970, 24.02970',
  };
  const request = settingsForSection('location', changed, profile);
  assert.equal(request.farmName, profile.farmName);
  assert.equal(request.units, profile.units);
  assert.equal(request.latitude, changed.latitude);
  assert.equal(request.longitude, changed.longitude);
  const savedProfile = { ...profile, ...request };
  const baseline = formValuesFrom(savedProfile);
  assert.equal(isSectionDirty('location', changed, baseline), false);
  assert.equal(isSectionDirty('farm', changed, baseline), true);
  assert.equal(isSectionDirty('preferences', changed, baseline), true);
});

test('saving farm details preserves saved coordinates and leaves unsaved location separate', () => {
  const changed = {
    ...formValuesFrom(profile),
    farmName: 'New farm',
    latitude: 0,
    longitude: 0,
    location: '0.00000, 0.00000',
  };
  const request = settingsForSection('farm', changed, profile);
  assert.equal(request.farmName, 'New farm');
  assert.equal(request.latitude, profile.latitude);
  assert.equal(request.longitude, profile.longitude);
  assert.equal(request.location, profile.location);
});
