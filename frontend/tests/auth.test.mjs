import './support/backend.mjs';
import assert from 'node:assert/strict';
import test from 'node:test';
import { authApi } from '../src/api/auth/auth.api.ts';
import { authMutations } from '../src/api/auth/auth.mutations.ts';
import { authQueries, authQueryKeys } from '../src/api/auth/auth.queries.ts';
import { createQueryClient } from '../src/api/core/query-client.ts';
import { ApiError, request } from '../src/api/core/http.ts';
import { farmApi } from '../src/api/farm/farm.api.ts';
import { farmQueryKeys } from '../src/api/farm/farm.queries.ts';
import { settingsApi } from '../src/api/settings/settings.api.ts';
import { settingsMutations } from '../src/api/settings/settings.mutations.ts';
import { settingsQueryKeys } from '../src/api/settings/settings.queries.ts';
import { returnPath } from '../src/features/auth/utils/auth.ts';

const credentials = { email: 'frontend-test@example.com', password: 'Test-password-123' };

test('authenticated profile and per-user settings cross the real HTTP boundary', async () => {
  const profile = await farmApi.getProfile();
  assert.equal(profile.fullName, 'Frontend Test');
  assert.equal(profile.email, credentials.email);
  const client = createQueryClient();
  try {
    client.setQueryData(farmQueryKeys.profile(), profile);
    const original = await settingsApi.get();
    const updated = {
      ...original,
      farmName: 'Saved farm',
      sessionLifetimeHours: 48,
      language: 'uk',
    };
    await client
      .getMutationCache()
      .build(client, settingsMutations.update(client))
      .execute(updated);
    assert.deepEqual(client.getQueryData(settingsQueryKeys.current()), updated);
    assert.equal(client.getQueryState(farmQueryKeys.profile()).isInvalidated, true);
    assert.deepEqual(await settingsApi.get(), updated);
    assert.equal((await farmApi.getProfile()).farmName, 'Saved farm');
    await settingsApi.update(original);
  } finally {
    client.clear();
  }
});

test('account switches and logout clear cached private data; settings remain isolated', async () => {
  const client = createQueryClient();
  try {
    client.setQueryData(['private', 'previous-user'], { secret: true });
    const second = await client
      .getMutationCache()
      .build(client, authMutations.register(client))
      .execute({
        email: 'second-frontend@example.com',
        password: 'Other-password-123',
        fullName: 'Second Farmer',
        farmName: 'Second farm',
        location: '',
        language: 'en',
      });
    assert.equal(client.getQueryData(['private', 'previous-user']), undefined);
    assert.deepEqual(client.getQueryData(authQueryKeys.me()), second);
    await settingsApi.update({ ...(await settingsApi.get()), farmName: 'Second private farm' });
    await client.getMutationCache().build(client, authMutations.login(client)).execute(credentials);
    assert.equal((await settingsApi.get()).farmName, 'Test farm');
    assert.equal((await client.fetchQuery(authQueries.me())).email, credentials.email);
    await client.getMutationCache().build(client, authMutations.logout(client)).execute();
    assert.equal(client.getQueryCache().getAll().length, 0);
    await assert.rejects(
      authApi.me(),
      (error) => error instanceof ApiError && error.status === 401,
    );
    await authApi.login(credentials);
  } finally {
    client.clear();
  }
});

test('invalid login and duplicate registration preserve explicit API errors', async () => {
  await assert.rejects(
    authApi.login({ ...credentials, password: 'wrong-password' }),
    (error) => error.status === 401,
  );
  await assert.rejects(
    authApi.register({
      ...credentials,
      fullName: 'Duplicate',
      farmName: 'Duplicate',
      location: '',
      language: 'en',
    }),
    (error) => error.status === 409,
  );
});

test('HTTP transport includes browser credentials without exposing a token', async () => {
  const previous = globalThis.fetch;
  try {
    globalThis.fetch = async (_url, options) => {
      assert.equal(options.credentials, 'include');
      assert.equal(options.headers.has('Authorization'), false);
      return Response.json({ ok: true });
    };
    assert.deepEqual(await request('/auth/me'), { ok: true });
  } finally {
    globalThis.fetch = previous;
  }
});

test('post-login redirects preserve internal paths and reject external destinations', () => {
  assert.equal(returnPath('?next=%2Fsettings'), '/settings');
  assert.equal(returnPath('?next=%2Fcalendar%3Ffield%3Dabc'), '/calendar?field=abc');
  for (const path of ['https://evil.example', '//evil.example', '/\\evil.example']) {
    assert.equal(returnPath(`?next=${encodeURIComponent(path)}`), '/');
  }
});

test('registration accepts omitted farm name and persists a selected map point', async () => {
  await authApi.register({
    email: 'mapped-frontend@example.com',
    password: 'Map-password-123',
    fullName: 'Map Farmer',
    location: '50.45010, 30.52340',
    latitude: 50.4501,
    longitude: 30.5234,
    language: 'en',
  });
  const saved = await settingsApi.get();
  assert.equal(saved.farmName, '');
  assert.equal(saved.latitude, 50.4501);
  assert.equal(saved.longitude, 30.5234);
  await authApi.login(credentials);
});
