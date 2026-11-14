import dayjs from 'dayjs';
import 'dayjs/locale/uk';
import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import resourcesToBackend from 'i18next-resources-to-backend';
import { initReactI18next } from 'react-i18next';

import { i18nOptions } from './options.ts';

// Explicit imports give Vite one independently loaded JSON chunk per locale.
const locales = {
  en: () => import('./locales/en.json'),
  uk: () => import('./locales/uk.json'),
};

i18n
  .use(resourcesToBackend((language: string) => locales[language as keyof typeof locales]()))
  .use(LanguageDetector)
  .use(initReactI18next);

i18n.on('languageChanged', (language) => {
  const locale = language === 'uk' ? 'uk' : 'en';
  document.documentElement.lang = locale;
  dayjs.locale(locale);
  document.title = i18n.t('App title');
  document
    .querySelector('meta[name="description"]')
    ?.setAttribute('content', i18n.t('App description'));
});

export const i18nReady = i18n.init(i18nOptions);

export default i18n;
