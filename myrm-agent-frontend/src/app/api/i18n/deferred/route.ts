/**
 * [INPUT]
 * - getLocale (POS: cookie locale)
 * - loadDeferredMessages (POS: server-only namespace loader)
 *
 * [OUTPUT]
 * GET /api/i18n/deferred — JSON partial messages (channels, memory, settings)
 *
 * [POS]
 * Client-side deferred locale hydration endpoint for LazyLocaleHydrator.
 */
import { NextResponse } from 'next/server';

import type { Locale } from '@/i18n/config';
import { getLocale } from '@/i18n/index';
import { loadDeferredMessages } from '@/i18n/load-messages';

export async function GET() {
  const locale = (await getLocale()) as Locale;
  const messages = await loadDeferredMessages(locale);

  return NextResponse.json(messages, {
    headers: {
      'Cache-Control': 'private, max-age=3600, stale-while-revalidate=86400',
    },
  });
}
