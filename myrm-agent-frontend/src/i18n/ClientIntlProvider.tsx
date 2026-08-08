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
const DEFERRED_FETCH_TIMEOUT_MS = 8_000;

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
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), DEFERRED_FETCH_TIMEOUT_MS);
  try {
    const response = await fetch('/api/i18n/deferred', {
      credentials: 'same-origin',
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Deferred locale fetch failed: ${response.status}`);
    }
    return (await response.json()) as Partial<Messages>;
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`Deferred locale fetch timed out after ${DEFERRED_FETCH_TIMEOUT_MS}ms`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
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
      if (
        typeof sessionStorage !== 'undefined' &&
        sessionStorage.getItem('e2e_skip_deferred_locale') === 'true'
      ) {
        if (!cancelled) {
          setDeferredLocaleReady(true);
        }
        return;
      }

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
            // Degrade to shell messages — settings must not infinite-skeleton on fetch blips.
            if (!cancelled) {
              setDeferredLocaleReady(true);
            }
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
