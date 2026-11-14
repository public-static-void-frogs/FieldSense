import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { createInstance } from 'i18next';
import resourcesToBackend from 'i18next-resources-to-backend';
import { i18nOptions, languageStorageKey } from '../src/i18n/options.ts';

const readLocale = async (language) =>
  JSON.parse(
    await readFile(new URL(`../src/i18n/locales/${language}.json`, import.meta.url), 'utf8'),
  );

function browser(languages, saved) {
  const values = new Map(saved ? [[languageStorageKey, saved]] : []);
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: { languages, language: languages[0] },
  });
  globalThis.window = { localStorage: storage };
  return storage;
}

let browserSession = 0;
async function initialize() {
  // A fresh detector resets its storage-support cache for each simulated page load.
  const { default: LanguageDetector } = await import(
    `${import.meta.resolve('i18next-browser-languagedetector')}?session=${browserSession++}`
  );
  const loaded = [];
  const i18n = createInstance();
  await i18n
    .use(LanguageDetector)
    .use(
      resourcesToBackend(async (language) => {
        loaded.push(language);
        return readLocale(language);
      }),
    )
    .init(structuredClone(i18nOptions));
  return { i18n, loaded };
}

test('catalogs contain the same keys, nonempty values and matching interpolation variables', async () => {
  const en = await readLocale('en');
  const uk = await readLocale('uk');
  assert.deepEqual(Object.keys(uk).sort(), Object.keys(en).sort());
  const variables = (value) => [...value.matchAll(/{{(.*?)}}/g)].map((match) => match[1]).sort();
  for (const [key, value] of Object.entries(en)) {
    assert.ok(uk[key].trim(), `Empty Ukrainian translation: ${key}`);
    assert.deepEqual(variables(uk[key]), variables(value), `Interpolation mismatch: ${key}`);
  }
});

test('English starts without loading Ukrainian; switching saves and reuses the locale', async () => {
  const storage = browser(['en-US']);
  const { i18n, loaded } = await initialize();
  assert.equal(i18n.resolvedLanguage, 'en');
  assert.deepEqual(loaded, ['en']);
  await i18n.changeLanguage('uk');
  assert.equal(i18n.t('Settings'), 'Налаштування');
  assert.equal(storage.getItem(languageStorageKey), 'uk');
  await i18n.changeLanguage('en');
  await i18n.changeLanguage('uk');
  assert.deepEqual(loaded, ['en', 'uk']);
  assert.equal(
    i18n.t('Farm summary', { count: 2, area: 20, attention: 1, critical: 0 }).includes('20 га'),
    true,
  );
});

test('Ukrainian regional browser language is detected and a saved setting overrides it', async () => {
  browser(['uk-UA', 'en-US']);
  assert.equal((await initialize()).i18n.resolvedLanguage, 'uk');
  browser(['uk-UA'], 'en');
  assert.equal((await initialize()).i18n.resolvedLanguage, 'en');
});

test('unsupported browser languages fall back to English', async () => {
  browser(['fr-FR']);
  const { i18n, loaded } = await initialize();
  assert.equal(i18n.resolvedLanguage, 'en');
  assert.deepEqual(loaded, ['en']);
});

test('blocked browser storage does not prevent detecting or switching languages', async () => {
  browser(['uk-UA']);
  Object.defineProperty(window, 'localStorage', {
    get() {
      throw new Error('Storage is blocked');
    },
  });
  const { i18n } = await initialize();
  assert.equal(i18n.resolvedLanguage, 'uk');
  await i18n.changeLanguage('en');
  assert.equal(i18n.t('Settings'), 'Settings');
});
