import assert from 'node:assert/strict';
import { access, readFile, readdir } from 'node:fs/promises';
import test from 'node:test';
import { createMemoryRouter, matchRoutes } from 'react-router-dom';
import { appRoutes } from '../src/app/routes.ts';
import { fieldLoader, calendarLoader } from '../src/app/route-loaders.ts';
import { calendarPath } from '../src/features/planning/utils/planningRoutes.ts';

const fieldOne = '00000000-0000-4000-8000-000000000001';
const fieldTwo = '00000000-0000-4000-8000-000000000002';
const eventId = '00000000-0000-4000-8000-000000000003';

const args = (params) => ({ params, request: new Request('http://localhost/'), context: {} });

test('the real route tree matches static, dynamic, optional and fallback routes', () => {
  for (const [path, id] of [
    ['/', 'overview'],
    ['/login', 'login'],
    ['/register', 'register'],
    ['/fields', 'fields'],
    [`/fields/${fieldOne}`, 'field'],
    [`/fields/${fieldTwo}/strategy`, 'strategy'],
    [`/fields/${fieldTwo}/recommendation`, 'recommendation'],
    ['/map', 'map'],
    ['/map/add', 'map-add'],
    [`/map/add/${fieldOne}`, 'catalog-field'],
    ['/calendar', 'calendar'],
    ['/calendar/2026-05-24?field=2', 'calendar'],
    ['/calendar/actions/field-2-inspection', 'action'],
    ['/history', 'history'],
    ['/help', 'help'],
    ['/settings', 'settings'],
    ['/notifications', 'notifications'],
    ['/missing/page', 'not-found'],
  ]) {
    assert.equal(matchRoutes(appRoutes, path).at(-1).route.id, id, path);
  }
  assert.equal(
    matchRoutes(appRoutes, '/login').some((match) => match.route.id === 'farm'),
    false,
  );
  assert.equal(
    matchRoutes(appRoutes, `/fields/${fieldOne}`).some((match) => match.route.id === 'farm'),
    true,
  );
});

test('route loaders validate IDs and dates before pages request data', () => {
  assert.deepEqual(fieldLoader(args({ fieldId: fieldOne.toUpperCase() })), { fieldId: fieldOne });
  for (const id of ['', '0', '-1', '1.5', '1e2', 'abc', '9007199254740992']) {
    assert.throws(
      () => fieldLoader(args({ fieldId: id })),
      (error) => error.status === 404,
    );
  }
  assert.equal(calendarLoader(args({})), null);
  assert.equal(calendarLoader(args({ date: '2026-05-24' })), null);
  for (const date of ['2026-02-30', '2026-13-01', '2026-5-24', 'invalid']) {
    assert.throws(
      () => calendarLoader(args({ date })),
      (error) => error.status === 404,
    );
  }
});

// Use the production route definitions/loaders without importing TSX in Node's test runner.
function withoutViews(routes) {
  return routes.map(({ lazy: _lazy, children, ...route }) => ({
    ...route,
    Component: () => null,
    ...(children ? { children: withoutViews(children) } : {}),
  }));
}
function idle(router) {
  if (router.state.navigation.state === 'idle') {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const unsubscribe = router.subscribe((state) => {
      if (state.navigation.state === 'idle') {
        unsubscribe();
        resolve();
      }
    });
  });
}

test('router navigation preserves params, search state, and back/forward history', async () => {
  const router = createMemoryRouter(withoutViews(appRoutes), { initialEntries: ['/fields'] });
  try {
    await router.navigate(`/fields/${fieldOne}`);
    assert.deepEqual(router.state.loaderData.field, { fieldId: fieldOne });
    await router.navigate(`/fields/${fieldTwo}/strategy`);
    assert.deepEqual(router.state.loaderData.strategy, { fieldId: fieldTwo });
    await router.navigate(-1);
    await idle(router);
    assert.equal(router.state.location.pathname, `/fields/${fieldOne}`);
    assert.deepEqual(router.state.loaderData.field, { fieldId: fieldOne });
    await router.navigate(1);
    await idle(router);
    assert.equal(router.state.location.pathname, `/fields/${fieldTwo}/strategy`);
    const path = calendarPath('2026-05-24', fieldOne, eventId);
    await router.navigate(path, { preventScrollReset: true });
    assert.equal(router.state.location.pathname, '/calendar/2026-05-24');
    assert.equal(new URLSearchParams(router.state.location.search).get('field'), fieldOne);
    assert.equal(new URLSearchParams(router.state.location.search).get('event'), eventId);
    assert.equal(router.state.preventScrollReset, true);
    await router.navigate('/fields/invalid');
    assert.equal(Object.values(router.state.errors)[0].status, 404);
  } finally {
    router.dispose();
  }
});

async function sources(directory) {
  return (
    await Promise.all(
      (await readdir(directory, { withFileTypes: true })).map((entry) =>
        entry.isDirectory()
          ? sources(`${directory}/${entry.name}`)
          : [`${directory}/${entry.name}`],
      ),
    )
  )
    .flat()
    .filter((path) => /\.tsx?$/.test(path));
}

test('custom hash navigation and navigation prop plumbing are removed', async () => {
  await assert.rejects(access(new URL('../src/hooks/useRoute.ts', import.meta.url)));
  for (const path of await sources(new URL('../src', import.meta.url).pathname)) {
    const source = await readFile(path, 'utf8');
    assert.doesNotMatch(
      source,
      /window\.location\.hash|hashchange|navigate=\{navigate\}|navigate:\s*Navigate/,
      path,
    );
    // In-page fragment anchors are valid; hash-based application routes are not.
    assert.doesNotMatch(source, /href=["']#\/|`#\//, path);
  }
});
