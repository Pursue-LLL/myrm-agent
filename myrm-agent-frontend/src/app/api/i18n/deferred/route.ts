/**
 * [INPUT]
 * - ?lang= and ?v= query (POS: cache-key discriminators chosen by the client)
 * - getLocale (POS: cookie locale fallback)
 * - loadDeferredMessages (POS: server-only namespace loader)
 *
 * [OUTPUT]
 * GET /api/i18n/deferred — JSON partial messages (deferred namespaces + remaining settings sections)
 *
 * [POS]
 * Client-side deferred locale hydration endpoint for ClientIntlProvider.
 */
import { NextResponse, type NextRequest } from 'next/server';

import { locales, type Locale } from '@/i18n/config';
import { getLocale } from '@/i18n/index';
import { loadDeferredMessages } from '@/i18n/load-messages';

function isLocale(value: string | null): value is Locale {
  return value !== null && (locales as readonly string[]).includes(value);
}

export async function GET(request: NextRequest) {
  // The language lives in the URL so the browser's max-age cache is keyed per language; a
  // cookie-only response would be replayed in the old language after a switch. (`locale` is
  // reserved by the marketing-relay middleware, hence `lang`.)
  const requested = request.nextUrl.searchParams.get('lang');
  const locale = isLocale(requested) ? requested : ((await getLocale()) as Locale);
  const messages = await loadDeferredMessages(locale);

  // The URL carries a content version (`v`), so production may cache long; dev edits locale files live.
  const cacheControl =
    process.env.NODE_ENV === 'development'
      ? 'no-store'
      : 'private, max-age=3600, stale-while-revalidate=86400';
  return NextResponse.json(messages, { headers: { 'Cache-Control': cacheControl } });
}
