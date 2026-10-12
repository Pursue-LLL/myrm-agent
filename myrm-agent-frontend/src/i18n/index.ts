'use server';

import { cookies } from 'next/headers';

import { defaultLocale, Locale } from '@/i18n/config';
import { NEXT_LOCALE_COOKIE_NAME, parseLocaleQueryParam } from '@/lib/utils/locale';

export async function getLocale(): Promise<Locale> {
  // A stale or foreign cookie value (e.g. `zh-CN`) has no namespace directory; fall back instead of 500-ing the page.
  const cookieValue = (await cookies()).get(NEXT_LOCALE_COOKIE_NAME)?.value ?? null;
  return parseLocaleQueryParam(cookieValue) ?? defaultLocale;
}

export async function setLocale(locale: Locale) {
  (await cookies()).set(NEXT_LOCALE_COOKIE_NAME, locale);
}
