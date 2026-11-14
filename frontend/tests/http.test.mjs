import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import ts from 'typescript';
import { ApiError, ApiUnavailableError, request } from '../src/api/core/http.ts';
import { createQueryClient } from '../src/api/core/query-client.ts';

// Compile the real JSX components for Node's test runner, using the same JSX runtime as Vite.
registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith('.tsx')) {
      return {
        format: 'module',
        shortCircuit: true,
        source: ts.transpileModule(readFileSync(new URL(url), 'utf8'), {
          compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext },
        }).outputText,
      };
    }
    return nextLoad(url, context);
  },
});
const { QueryBoundary } = await import('../src/components/common/QueryBoundary.tsx');

function configure(t) {
  const previous = process.env.VITE_API_BASE_URL;
  process.env.VITE_API_BASE_URL = 'http://api.example.test/api/v1/';
  t.after(() => {
    if (previous === undefined) {
      delete process.env.VITE_API_BASE_URL;
    } else {
      process.env.VITE_API_BASE_URL = previous;
    }
  });
}

test('requests use the entire configured API URL and preserve JSON headers', async (t) => {
  configure(t);
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'http://api.example.test/api/v1/fields');
    assert.equal(options.headers.get('Content-Type'), 'application/json');
    assert.equal(options.headers.get('X-Request-ID'), 'test');
    return Response.json({ id: 6 });
  });
  assert.deepEqual(
    await request('/fields', {
      method: 'POST',
      body: '{}',
      headers: new Headers({ 'X-Request-ID': 'test' }),
    }),
    { id: 6 },
  );
});

test('missing or relative API configuration is rejected before making a request', async (t) => {
  configure(t);
  const fetch = t.mock.method(globalThis, 'fetch');
  for (const value of ['', '/api/v1']) {
    process.env.VITE_API_BASE_URL = value;
    await assert.rejects(request('/fields'), /full HTTP API URL/);
  }
  assert.equal(fetch.mock.callCount(), 0);
});

test('network failures and server errors become API-unavailable errors', async (t) => {
  configure(t);
  const fetch = t.mock.method(globalThis, 'fetch', async () => {
    throw new TypeError('Failed to fetch');
  });
  await assert.rejects(request('/fields'), ApiUnavailableError);
  for (const status of [408, 500, 502, 503, 504]) {
    fetch.mock.mockImplementation(async () => new Response('', { status }));
    await assert.rejects(request('/fields'), ApiUnavailableError);
  }
});

test('an unresponsive API times out; caller cancellation remains cancellation', async (t) => {
  configure(t);
  t.mock.method(AbortSignal, 'timeout', (milliseconds) => {
    assert.equal(milliseconds, 10_000);
    return AbortSignal.abort(new DOMException('Timed out', 'TimeoutError'));
  });
  t.mock.method(globalThis, 'fetch', async (_url, { signal }) => {
    signal.throwIfAborted();
  });
  await assert.rejects(request('/fields'), ApiUnavailableError);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    request('/fields', { signal: controller.signal }),
    (error) => error.name === 'AbortError' && !(error instanceof ApiUnavailableError),
  );
});

test('validation failures and nullable 404s retain their existing behavior', async (t) => {
  configure(t);
  const fetch = t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ detail: [{ msg: 'Invalid crop' }] }, { status: 422 }),
  );
  await assert.rejects(
    request('/fields'),
    (error) =>
      error instanceof ApiError && error.status === 422 && error.message === 'Invalid crop',
  );
  fetch.mock.mockImplementation(async () => new Response('', { status: 404 }));
  assert.equal(await request('/fields/999', { allowMissing: true }), null);
});

test('unavailable queries stop automatic retries and recover when retried explicitly', async () => {
  const client = createQueryClient();
  let attempts = 0;
  const options = {
    queryKey: ['test', 'outage'],
    queryFn: async () => {
      attempts++;
      throw new ApiUnavailableError();
    },
  };
  await assert.rejects(client.fetchQuery(options), ApiUnavailableError);
  assert.equal(attempts, 1);
  assert.equal(
    await client.fetchQuery({ ...options, queryFn: async () => 'recovered' }),
    'recovered',
  );
  client.clear();
});

test('query boundary displays the translated unavailable page and resets on retry', async () => {
  const i18n = createInstance();
  await i18n.init({ lng: 'en', resources: { en: { translation: {} } }, keySeparator: false });
  let resets = 0;
  const boundary = new QueryBoundary({
    children: 'content',
    onReset: () => {
      resets++;
    },
  });
  boundary.state = QueryBoundary.getDerivedStateFromError(new ApiUnavailableError());
  const html = renderToStaticMarkup(createElement(I18nextProvider, { i18n }, boundary.render()));
  assert.match(html, /API is unavailable/);
  assert.match(html, /Try again/);
  assert.match(html, /role="alert"/);
  boundary.setState = (state) => {
    boundary.state = state;
  };
  boundary.retry();
  assert.equal(resets, 1);
  assert.equal(boundary.render(), 'content');
});
