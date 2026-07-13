/**
 * [INPUT]
 * - next-intl useMessages (POS: SSR shell messages from LocalizedProviders)
 * - GET /api/i18n/deferred (POS: channels/memory/settings JSON)
 *
 * [OUTPUT]
 * Nested NextIntlClientProvider with merged shell + deferred messages
 *
 * [POS]
 * Client mount hook: completes locale hydration without bloating RSC HTML.
 */
'use client';

import { NextIntlClientProvider, useMessages } from 'next-intl';
import { useLayoutEffect, useMemo, useState } from 'react';

import type { Locale } from '@/i18n/config';
import type { Messages } from '@/i18n/locale-manifest';

interface LazyLocaleHydratorProps {
  locale: Locale;
}

function mergeMessages(base: Messages, extra: Partial<Messages>): Messages {
  return {
    ...base,
    ...extra,
    settings: {
      ...base.settings,
      ...extra.settings,
    },
  } as Messages;
}

/**
 * Fetches deferred locale namespaces after mount so SSR/RSC only ships shell messages.
 */
export default function LazyLocaleHydrator({ locale }: LazyLocaleHydratorProps) {
  const shellMessages = useMessages() as Messages;
  const [deferredMessages, setDeferredMessages] = useState<Partial<Messages> | null>(null);

  useLayoutEffect(() => {
    let cancelled = false;

    void fetch('/api/i18n/deferred', { credentials: 'same-origin' })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Deferred locale fetch failed: ${response.status}`);
        }
        return (await response.json()) as Partial<Messages>;
      })
      .then((loaded) => {
        if (!cancelled) {
          setDeferredMessages(loaded);
        }
      })
      .catch((error: unknown) => {
        console.error('Failed to load deferred locale messages', error);
      });

    return () => {
      cancelled = true;
    };
  }, [locale]);

  const mergedMessages = useMemo(() => {
    if (!deferredMessages) {
      return null;
    }
    return mergeMessages(shellMessages, deferredMessages);
  }, [deferredMessages, shellMessages]);

  if (!mergedMessages) {
    return null;
  }

  return (
    <NextIntlClientProvider locale={locale} messages={mergedMessages}>
      {null}
    </NextIntlClientProvider>
  );
}
