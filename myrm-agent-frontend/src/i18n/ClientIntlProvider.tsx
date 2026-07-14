/**
 * [INPUT]
 * - SSR shell messages from LocalizedProviders
 * - GET /api/i18n/deferred (channels + remaining settings sections)
 *
 * [OUTPUT]
 * NextIntlClientProvider wrapping the app with shell + deferred messages
 *
 * [POS]
 * Client i18n root: starts with SSR shell, merges deferred namespaces after mount.
 */
'use client';

import { NextIntlClientProvider } from 'next-intl';
import { useLayoutEffect, useState, type ReactNode } from 'react';

import type { Locale } from '@/i18n/config';
import { DeferredLocaleProvider } from '@/i18n/deferred-locale-context';
import type { Messages } from '@/i18n/locale-manifest';
import { mergeMessages } from '@/i18n/merge-messages';

const DEFERRED_FETCH_MAX_ATTEMPTS = 3;
const DEFERRED_FETCH_RETRY_BASE_MS = 400;

interface ClientIntlProviderProps {
  locale: Locale;
  shellMessages: Messages;
  children: ReactNode;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function fetchDeferredMessages(): Promise<Partial<Messages>> {
  const response = await fetch('/api/i18n/deferred', { credentials: 'same-origin' });
  if (!response.ok) {
    throw new Error(`Deferred locale fetch failed: ${response.status}`);
  }
  return (await response.json()) as Partial<Messages>;
}

export default function ClientIntlProvider({ locale, shellMessages, children }: ClientIntlProviderProps) {
  const [messages, setMessages] = useState<Messages>(shellMessages);
  const [deferredLocaleReady, setDeferredLocaleReady] = useState(false);

  useLayoutEffect(() => {
    setMessages(shellMessages);
    setDeferredLocaleReady(false);
  }, [shellMessages]);

  useLayoutEffect(() => {
    let cancelled = false;

    const loadDeferredWithRetry = async (): Promise<void> => {
      for (let attempt = 0; attempt < DEFERRED_FETCH_MAX_ATTEMPTS; attempt += 1) {
        if (cancelled) {
          return;
        }

        try {
          const loaded = await fetchDeferredMessages();
          if (!cancelled) {
            setMessages(mergeMessages(shellMessages, loaded));
            setDeferredLocaleReady(true);
          }
          return;
        } catch (error: unknown) {
          const isLastAttempt = attempt >= DEFERRED_FETCH_MAX_ATTEMPTS - 1;
          if (isLastAttempt) {
            console.error('Failed to load deferred locale messages after retries', error);
            return;
          }

          await sleep(DEFERRED_FETCH_RETRY_BASE_MS * 2 ** attempt);
        }
      }
    };

    void loadDeferredWithRetry();

    return () => {
      cancelled = true;
    };
  }, [locale, shellMessages]);

  return (
    <DeferredLocaleProvider deferredLocaleReady={deferredLocaleReady}>
      <NextIntlClientProvider locale={locale} messages={messages}>
        {children}
      </NextIntlClientProvider>
    </DeferredLocaleProvider>
  );
}
