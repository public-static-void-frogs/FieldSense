import type { InitOptions } from 'i18next';

export const languageStorageKey = 'frogfarmers.language';

export const i18nOptions: InitOptions = {
  supportedLngs: ['en', 'uk'],
  fallbackLng: 'en',
  load: 'languageOnly',
  detection: {
    order: ['localStorage', 'navigator'],
    lookupLocalStorage: languageStorageKey,
    caches: ['localStorage'],
  },
  // Natural language keys keep shared UI labels readable at their call sites.
  keySeparator: false,
  nsSeparator: false,
  interpolation: { escapeValue: false },
};
