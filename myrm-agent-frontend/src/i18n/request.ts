import { getRequestConfig } from 'next-intl/server';

import deMessages from '#locales/de.json';
import enMessages from '#locales/en.json';
import jaMessages from '#locales/ja.json';
import koMessages from '#locales/ko.json';
import zhMessages from '#locales/zh.json';

import type { Locale } from './config';
import { getLocale } from './index';

type Messages = typeof zhMessages;

const messagesByLocale: Record<Locale, Messages> = {
  de: deMessages as unknown as Messages,
  en: enMessages as unknown as Messages,
  ja: jaMessages as unknown as Messages,
  ko: koMessages as unknown as Messages,
  zh: zhMessages,
};

export default getRequestConfig(async () => {
  const locale = (await getLocale()) as Locale;

  return {
    locale,
    messages: messagesByLocale[locale],
  };
});
