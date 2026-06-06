'use server';

import { cookies } from 'next/headers';

import { defaultLocale, Locale } from '@/i18n/config';
import { NEXT_LOCALE_COOKIE_NAME } from '@/lib/utils/localeUtils';

export async function getLocale() {
  return (await cookies()).get(NEXT_LOCALE_COOKIE_NAME)?.value || defaultLocale;
}

export async function setLocale(locale: Locale) {
  (await cookies()).set(NEXT_LOCALE_COOKIE_NAME, locale);
}
