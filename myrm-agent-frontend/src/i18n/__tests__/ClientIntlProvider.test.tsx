import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  NextIntlClientProvider: ({ children }: { children: ReactNode }) => children,
}));

import ClientIntlProvider from '@/i18n/ClientIntlProvider';
import { useDeferredLocaleReady } from '@/i18n/deferred-locale-context';
import type { Messages } from '@/i18n/locale-manifest';

function DeferredReadyProbe() {
  const ready = useDeferredLocaleReady();
  return <span data-testid="deferred-ready">{ready ? 'yes' : 'no'}</span>;
}

const shellMessages = {
  chat: { title: 'Chat' },
  settings: {
    defaultModel: { searchModels: 'Search models' },
  },
} as unknown as Messages;

describe('ClientIntlProvider deferred locale', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.stubGlobal('fetch', originalFetch);
    vi.restoreAllMocks();
  });

  it('sets deferredLocaleReady after successful fetch', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          settings: { account: { title: 'Account' } },
        }),
      })),
    );

    render(
      <ClientIntlProvider locale="en" shellMessages={shellMessages}>
        <DeferredReadyProbe />
      </ClientIntlProvider>,
    );

    expect(screen.getByTestId('deferred-ready')).toHaveTextContent('no');

    await waitFor(() => {
      expect(screen.getByTestId('deferred-ready')).toHaveTextContent('yes');
    });
  });

  it('degrades to shell messages when deferred fetch fails after retries', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 503,
      })),
    );

    render(
      <ClientIntlProvider locale="en" shellMessages={shellMessages}>
        <DeferredReadyProbe />
      </ClientIntlProvider>,
    );

    await vi.runAllTimersAsync();

    await waitFor(() => {
      expect(screen.getByTestId('deferred-ready')).toHaveTextContent('yes');
    });
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it('skips deferred fetch when e2e sessionStorage flag is set', async () => {
    sessionStorage.setItem('e2e_skip_deferred_locale', 'true');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(
      <ClientIntlProvider locale="en" shellMessages={shellMessages}>
        <DeferredReadyProbe />
      </ClientIntlProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('deferred-ready')).toHaveTextContent('yes');
    });
    expect(fetchMock).not.toHaveBeenCalled();
    sessionStorage.removeItem('e2e_skip_deferred_locale');
  });

  it('succeeds on a later retry attempt', async () => {
    let calls = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        calls += 1;
        if (calls < 2) {
          return { ok: false, status: 500 };
        }
        return {
          ok: true,
          json: async () => ({ settings: { account: { title: 'Account' } } }),
        };
      }),
    );

    render(
      <ClientIntlProvider locale="en" shellMessages={shellMessages}>
        <DeferredReadyProbe />
      </ClientIntlProvider>,
    );

    await vi.runAllTimersAsync();

    await waitFor(() => {
      expect(screen.getByTestId('deferred-ready')).toHaveTextContent('yes');
    });
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
