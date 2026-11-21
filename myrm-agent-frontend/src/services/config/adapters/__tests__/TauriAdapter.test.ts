import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { markLocalBackendUnreachable } from '@/lib/backend-health';
import { TauriConfigAdapter } from '@/services/config/adapters/TauriAdapter';
import { ConfigSyncError, DEFAULT_PERSONAL_SETTINGS, type ConfigChange } from '@/services/config/types';

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => '/api/v1',
}));

vi.mock('@/lib/backend-health', () => ({
  markLocalBackendUnreachable: vi.fn(),
}));

vi.mock('@/lib/platform-readiness', () => ({
  whenDatabaseReady: vi.fn(async () => true),
}));

const CHANGES: ConfigChange[] = [
  {
    key: 'personalSettings',
    value: { ...DEFAULT_PERSONAL_SETTINGS, systemInstructions: 'test' },
    expectedVersion: '0_0',
    timestamp: Date.now(),
  },
];

const BACKEND_NOT_AVAILABLE = {
  success: false,
  conflicts: [],
  newVersions: new Map(),
  error: 'Backend not available',
};

describe('TauriConfigAdapter backend unavailable', () => {
  const originalFetch = globalThis.fetch;
  let adapter: TauriConfigAdapter;

  beforeEach(() => {
    adapter = new TauriConfigAdapter();
    vi.mocked(markLocalBackendUnreachable).mockClear();
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.stubGlobal('fetch', originalFetch);
    vi.restoreAllMocks();
  });

  it('sync treats Next proxy HTTP 500 like Failed to fetch', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    } as Response);

    await expect(adapter.sync(CHANGES)).resolves.toEqual(BACKEND_NOT_AVAILABLE);
    expect(markLocalBackendUnreachable).toHaveBeenCalledTimes(1);
  });

  it.each(['Failed to fetch', 'Load failed', 'NetworkError when attempting to fetch resource.'])(
    'sync reports Backend not available when the browser fails the request (%s)',
    async (message) => {
      vi.mocked(fetch).mockRejectedValueOnce(new TypeError(message));

      await expect(adapter.sync(CHANGES)).resolves.toEqual(BACKEND_NOT_AVAILABLE);
      expect(markLocalBackendUnreachable).toHaveBeenCalledTimes(1);
    },
  );

  it('sync does not mistake a malformed answer for a network failure', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    } as Response);

    await expect(adapter.sync(CHANGES)).rejects.toBeInstanceOf(TypeError);
    expect(markLocalBackendUnreachable).not.toHaveBeenCalled();
  });

  it('getAll throws on HTTP 502 to enable ConfigSyncManager retry', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
    } as Response);

    await expect(adapter.getAll()).rejects.toThrow('Backend not available');
  });

  it('getAll throws when localFetch times out (AbortError) to enable retry', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new DOMException('The operation was aborted.', 'AbortError'));

    await expect(adapter.getAll()).rejects.toThrow('Backend not available');
    expect(markLocalBackendUnreachable).toHaveBeenCalledTimes(1);
  });

  describe('get', () => {
    it('answers null only when the backend says the row does not exist', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 404, statusText: 'Not Found' } as Response);

      await expect(adapter.get('chatSettings')).resolves.toBeNull();
    });

    it.each([500, 502, 503, 504])('throws on HTTP %i: the state of the row is unknown', async (status) => {
      vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status, statusText: 'Unavailable' } as Response);

      await expect(adapter.get('chatSettings')).rejects.toThrow(new ConfigSyncError('Backend not available'));
      expect(markLocalBackendUnreachable).toHaveBeenCalledTimes(1);
    });

    it.each([new TypeError('Load failed'), new DOMException('The operation was aborted.', 'AbortError')])(
      'throws when the request never gets an answer (%s)',
      async (failure) => {
        vi.mocked(fetch).mockRejectedValueOnce(failure);

        await expect(adapter.get('chatSettings')).rejects.toThrow(new ConfigSyncError('Backend not available'));
        expect(markLocalBackendUnreachable).toHaveBeenCalledTimes(1);
      },
    );
  });
});
