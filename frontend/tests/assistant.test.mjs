import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import ts from 'typescript';
import { ApiError, ApiUnavailableError } from '../src/api/core/http.ts';
import { assistantApi, ChatInterruptedError } from '../src/api/assistant/assistant.api.ts';
import {
  assistantErrorMessages,
  assistantSuggestions,
  MAX_HISTORY_MESSAGES,
  MAX_MESSAGE_CHARS,
  toolProgressLabels,
} from '../src/features/assistant/constants/assistant.constants.ts';
import { classifyChatError } from '../src/features/assistant/utils/chatErrors.ts';
import { buildHistory } from '../src/features/assistant/utils/chatHistory.ts';
import { progressLabel } from '../src/features/assistant/utils/chatProgress.ts';
import { i18nOptions } from '../src/i18n/options.ts';
import {
  calendarAssistantIntro,
  calendarAssistantPlaceholder,
  calendarAssistantPrompt,
  calendarAssistantSuggestions,
} from '../src/features/planning/constants/calendarAssistant.constants.ts';

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
const { ChatMessageList } =
  await import('../src/features/assistant/components/ChatMessageList.tsx');

const readLocale = (language) =>
  JSON.parse(
    readFileSync(new URL(`../src/i18n/locales/${language}.json`, import.meta.url), 'utf8'),
  );

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

function stream(...chunks) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) {
          controller.enqueue(encoder.encode(chunk));
        }
        controller.close();
      },
    }),
  );
}

function chat(overrides = {}) {
  const seen = { deltas: [], tools: [] };
  const promise = assistantApi.streamChat({
    messages: [{ role: 'user', content: 'Frost?' }],
    fieldId: 'field-1',
    locale: 'uk',
    signal: new AbortController().signal,
    onDelta: (delta) => seen.deltas.push(delta),
    onTool: (tool) => seen.tools.push(tool),
    ...overrides,
  });
  return { seen, promise };
}

test('chat posts the conversation and streams deltas and tool events across chunk boundaries', async (t) => {
  configure(t);
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'http://api.example.test/api/v1/assistant/chat');
    assert.equal(options.method, 'POST');
    assert.equal(options.credentials, 'include');
    assert.equal(options.headers.get('Content-Type'), 'application/json');
    assert.deepEqual(JSON.parse(options.body), {
      messages: [{ role: 'user', content: 'Frost?' }],
      field_id: 'field-1',
      locale: 'uk',
    });
    // The first line is split in the middle of a JSON string.
    return stream(
      '{"tool":"get_weather_forecast"}\n{"delta":"Fro',
      'st "}\n\n{"delta":"tonight."}\n{"done":true}\n',
    );
  });
  const { seen, promise } = chat();
  await promise;
  assert.deepEqual(seen.tools, ['get_weather_forecast']);
  assert.deepEqual(seen.deltas, ['Frost ', 'tonight.']);
});

test('field_id is omitted when no field is given', async (t) => {
  configure(t);
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.deepEqual(Object.keys(JSON.parse(options.body)), ['messages', 'locale']);
    return stream('{"done":true}\n');
  });
  await chat({ fieldId: undefined }).promise;
});

test('a stream that ends without done is an interrupted answer, even after text arrived', async (t) => {
  configure(t);
  t.mock.method(globalThis, 'fetch', async () => stream('{"delta":"Part"}\n'));
  const { seen, promise } = chat();
  await assert.rejects(promise, ChatInterruptedError);
  assert.deepEqual(seen.deltas, ['Part']);
  t.mock.method(globalThis, 'fetch', async () => stream());
  await assert.rejects(chat().promise, ChatInterruptedError);
});

test('server errors map to unavailable, client errors keep their message, abort passes through', async (t) => {
  configure(t);
  t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 503 }));
  await assert.rejects(chat().promise, ApiUnavailableError);
  t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ detail: 'Unknown tools: nope' }, { status: 422 }),
  );
  await assert.rejects(chat().promise, (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.message, 'Unknown tools: nope');
    return true;
  });
  const abort = new AbortController();
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    abort.abort(new DOMException('stopped', 'AbortError'));
    options.signal.throwIfAborted();
    return stream('{"done":true}\n');
  });
  await assert.rejects(chat({ signal: abort.signal }).promise, { name: 'AbortError' });
});

test('chat errors are classified for the user', () => {
  assert.equal(classifyChatError(new ApiUnavailableError()), 'unavailable');
  assert.equal(classifyChatError(new ChatInterruptedError()), 'interrupted');
  assert.equal(classifyChatError(new ApiError(422, 'bad')), 'failed');
  assert.equal(classifyChatError(new Error('x')), 'failed');
});

test('history keeps what the server accepts: user-first, bounded, without failed or empty entries', () => {
  const entry = (id, role, content, status = 'done') => ({ id, role, content, status });
  assert.deepEqual(
    buildHistory([
      entry(1, 'user', 'Q1'),
      entry(2, 'assistant', 'Cut off', 'failed'),
      entry(3, 'assistant', '  '),
      entry(4, 'user', 'Q2'),
    ]),
    [
      { role: 'user', content: 'Q1' },
      { role: 'user', content: 'Q2' },
    ],
  );
  assert.deepEqual(buildHistory([entry(1, 'assistant', 'Hello'), entry(2, 'user', 'Hi')]), [
    { role: 'user', content: 'Hi' },
  ]);
  const long = [];
  for (let id = 0; id < 30; id += 1) {
    long.push(entry(id, id % 2 ? 'assistant' : 'user', `m${id}`));
  }
  long.push(entry(30, 'user', 'x'.repeat(MAX_MESSAGE_CHARS + 50)));
  const history = buildHistory(long);
  assert.ok(history.length <= MAX_HISTORY_MESSAGES);
  assert.equal(history[0].role, 'user');
  assert.equal(history.at(-1).role, 'user');
  assert.equal(history.at(-1).content.length, MAX_MESSAGE_CHARS);
});

test('progress labels cover every backend tool and fall back for unknown ones', () => {
  assert.equal(progressLabel(null), 'Thinking…');
  assert.equal(progressLabel('get_soil_depletion'), 'Checking soil depletion…');
  assert.equal(progressLabel('get_crop_zones'), 'Looking up field data…');
});

test('every phrase the assistant translates dynamically exists in both catalogs', () => {
  const en = readLocale('en');
  const uk = readLocale('uk');
  const phrases = [
    ...assistantSuggestions,
    ...Object.values(toolProgressLabels),
    ...Object.values(assistantErrorMessages),
    'Thinking…',
    'Looking up field data…',
  ];
  for (const phrase of phrases) {
    assert.equal(en[phrase], phrase, `English catalog: ${phrase}`);
    assert.ok(uk[phrase]?.trim() && uk[phrase] !== phrase, `Ukrainian catalog: ${phrase}`);
  }
});

async function render(props, language = 'en') {
  const i18n = createInstance();
  await i18n.init({
    ...structuredClone(i18nOptions),
    lng: language,
    resources: { [language]: { translation: language === 'uk' ? readLocale('uk') : {} } },
  });
  const noop = () => {};
  return renderToStaticMarkup(
    createElement(
      I18nextProvider,
      { i18n },
      createElement(ChatMessageList, {
        entries: [],
        activeTool: null,
        isStreaming: false,
        error: null,
        onAsk: noop,
        onRetry: noop,
        ...props,
      }),
    ),
  );
}

test('an empty conversation offers suggestions and the disclaimer', async () => {
  const html = await render({});
  for (const question of assistantSuggestions) {
    assert.ok(html.includes(question), question);
  }
  assert.match(html, /AI answers can be wrong/);
  assert.doesNotMatch(html, /role="log"/);
  assert.match(await render({}, 'uk'), /Чи є цього тижня ризик заморозків\?/);
});

test('messages render as escaped plain text; empty answers, progress and errors show correctly', async () => {
  const entries = [
    { id: 1, role: 'user', content: 'Frost <b>tonight</b>?', status: 'done' },
    { id: 2, role: 'assistant', content: 'Low risk.\n- Cover crops', status: 'done' },
    { id: 3, role: 'user', content: 'Soil?', status: 'done' },
    { id: 4, role: 'assistant', content: '', status: 'done' },
  ];
  const html = await render({ entries, isStreaming: true, activeTool: 'get_soil_depletion' });
  assert.match(html, /role="log"/);
  assert.match(html, /Frost &lt;b&gt;tonight&lt;\/b&gt;\?/);
  assert.doesNotMatch(html, /<b>tonight/);
  assert.match(html, /Low risk\.\n- Cover crops/);
  assert.equal(html.match(/assistant-message--assistant/g).length, 1); // the empty answer is hidden
  assert.match(html, /role="status"/);
  assert.match(html, /Checking soil depletion…/);

  assert.match(await render({ entries, isStreaming: true }), /Thinking…/);
  const idle = await render({ entries: entries.slice(0, 2), isStreaming: false });
  assert.doesNotMatch(idle, /role="status"/);
  // Text is already streaming and no tool runs: no progress line.
  assert.doesNotMatch(
    await render({ entries: entries.slice(0, 2), isStreaming: true }),
    /role="status"/,
  );

  const failed = await render({ entries: entries.slice(0, 3), error: 'unavailable' });
  assert.match(failed, /The assistant is unavailable right now/);
  assert.match(failed, /Try again/);
  assert.match(failed, /role="alert"/);
});

test('a selected calendar day is sent as calendar_date and omitted otherwise', async (t) => {
  configure(t);
  const bodies = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    bodies.push(JSON.parse(options.body));
    return stream('{"done":true}\n');
  });
  await chat({ fieldId: undefined, calendarDate: '2026-11-20' }).promise;
  await chat({ fieldId: undefined }).promise;
  assert.equal(bodies[0].calendar_date, '2026-11-20');
  assert.equal('field_id' in bodies[0], false);
  assert.equal('calendar_date' in bodies[1], false);
  assert.equal(progressLabel('get_calendar_events'), 'Reading calendar events…');
});

test('calendar assistant phrases exist in both catalogs and the chat list can show its own intro', async () => {
  const en = readLocale('en');
  const uk = readLocale('uk');
  const phrases = [
    calendarAssistantPrompt,
    calendarAssistantIntro,
    calendarAssistantPlaceholder,
    ...calendarAssistantSuggestions,
    toolProgressLabels.get_calendar_events,
  ];
  for (const phrase of phrases) {
    assert.equal(en[phrase], phrase, `English catalog: ${phrase}`);
    assert.ok(uk[phrase]?.trim() && uk[phrase] !== phrase, `Ukrainian catalog: ${phrase}`);
  }
  const html = await render({
    intro: calendarAssistantIntro,
    suggestions: calendarAssistantSuggestions,
  });
  assert.match(html, /Ask about the actions and warnings planned for this day\./);
  assert.match(html, /What could delay these actions\?/);
  assert.doesNotMatch(html, /Is there a frost risk this week\?/);
});
