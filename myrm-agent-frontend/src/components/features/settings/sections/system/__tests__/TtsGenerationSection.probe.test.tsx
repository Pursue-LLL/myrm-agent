import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';

import TtsGenerationSection from '../TtsGenerationSection';

const kit = vi.hoisted(() => ({
  fetch: vi.fn<(url: string, init: RequestInit) => Promise<{ json: () => Promise<unknown> }>>(),
  providers: [] as unknown[],
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/lib/api', () => ({
  apiRequest: async () => ({ value: { ttsApiKey: 'sk-stored' }, meta: { version: 'v1' } }),
}));
vi.mock('@/store/useProviderStore', () => ({
  default: (select: (state: { providers: unknown[] }) => unknown) => select({ providers: kit.providers }),
}));
vi.mock('@/hooks/shared/useToast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/utils/media', () => ({ providerHasActiveApiKey: () => false }));
vi.mock('@/lib/utils/apiConfig', () => ({ getBackendUrl: () => 'http://backend' }));
vi.mock('@/lib/utils/authHeaders', () => ({ getAuthHeaders: () => ({ Authorization: 'Bearer token' }) }));

const testButton = () => screen.getByRole('button', { name: 'Test Connection' });

async function renderSection() {
  render(<TtsGenerationSection />);
  await act(async () => undefined);
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal('fetch', kit.fetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TtsGenerationSection connection test', () => {
  it('probes the chosen provider and model with the auth headers', async () => {
    kit.fetch.mockResolvedValue({ json: async () => ({ success: true }) });
    const user = userEvent.setup();
    await renderSection();

    await user.click(testButton());

    expect(kit.fetch).toHaveBeenCalledExactlyOnceWith('http://backend/api/v1/agents/test-media-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer token' },
      body: JSON.stringify({ mediaType: 'tts', provider: 'openai', model: 'tts-1' }),
    });
    expect(testButton().querySelector('.text-green-500')).not.toBeNull();
  });

  it('accepts the nested status answer as success', async () => {
    kit.fetch.mockResolvedValue({ json: async () => ({ data: { status: 'ok' } }) });
    const user = userEvent.setup();
    await renderSection();

    await user.click(testButton());

    expect(testButton().querySelector('.text-green-500')).not.toBeNull();
    expect(testButton().querySelector('.text-red-500')).toBeNull();
  });

  it('shows the server message when the probe fails, then clears it after a moment', async () => {
    kit.fetch.mockResolvedValue({ json: async () => ({ success: false, message: 'bad key' }) });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      await renderSection();

      await user.click(testButton());
      expect(screen.getByText('bad key')).toBeInTheDocument();

      await act(async () => vi.advanceTimersByTimeAsync(3000));
      expect(screen.queryByText('bad key')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it.each([
    ['the server sends no message', () => kit.fetch.mockResolvedValue({ json: async () => ({ success: false }) })],
    ['the request itself fails', () => kit.fetch.mockRejectedValue(new Error('offline'))],
  ])('marks the probe as failed when %s', async (_case, arrange) => {
    arrange();
    const user = userEvent.setup();
    await renderSection();

    await user.click(testButton());

    expect(testButton().querySelector('.text-red-500')).not.toBeNull();
  });

  it('disables the button while the probe runs', async () => {
    const pending = deferred<{ json: () => Promise<unknown> }>();
    kit.fetch.mockReturnValue(pending.promise);
    const user = userEvent.setup();
    await renderSection();

    await user.click(testButton());
    expect(testButton()).toBeDisabled();

    await act(async () => pending.resolve({ json: async () => ({ success: true }) }));
    expect(testButton()).toBeEnabled();
  });
});
