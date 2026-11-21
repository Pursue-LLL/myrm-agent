import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getAuthToken } from '@/lib/guest';
import { SandboxConfigAdapter } from '@/services/config/adapters/SandboxAdapter';
import { ConfigSyncError, DEFAULT_PERSONAL_SETTINGS, type ConfigChange } from '@/services/config/types';

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => 'http://test.local',
}));

vi.mock('@/lib/guest', () => ({
  getAuthToken: vi.fn(() => 'test-token'),
}));

const reply = (status: number, body: unknown = {}) =>
  ({ ok: status >= 200 && status < 300, status, statusText: `HTTP ${status}`, json: async () => body }) as Response;

const CHANGES: ConfigChange[] = [
  {
    key: 'personalSettings',
    value: { ...DEFAULT_PERSONAL_SETTINGS, systemInstructions: 'edited' },
    expectedVersion: '1000_0',
    timestamp: 1,
  },
];

const BACKEND_NOT_AVAILABLE = {
  success: false,
  conflicts: [],
  newVersions: new Map(),
  error: 'Backend not available',
};

describe('SandboxConfigAdapter', () => {
  const originalFetch = globalThis.fetch;
  let adapter: SandboxConfigAdapter;

  beforeEach(() => {
    adapter = new SandboxConfigAdapter();
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.stubGlobal('fetch', originalFetch);
    vi.mocked(getAuthToken).mockReturnValue('test-token');
  });

  describe('get', () => {
    it('answers null only when the server says the row does not exist', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(reply(404));

      await expect(adapter.get('chatSettings')).resolves.toBeNull();
    });

    it.each([401, 500, 502, 503])('throws on HTTP %i: the state of the row is unknown', async (status) => {
      vi.mocked(fetch).mockResolvedValueOnce(reply(status));

      await expect(adapter.get('chatSettings')).rejects.toThrow(ConfigSyncError);
    });

    it('throws when the session has no token', async () => {
      vi.mocked(getAuthToken).mockReturnValue(null);

      await expect(adapter.get('chatSettings')).rejects.toThrow(ConfigSyncError);
      expect(fetch).not.toHaveBeenCalled();
    });

    it('throws when the request never gets an answer', async () => {
      vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Load failed'));

      await expect(adapter.get('chatSettings')).rejects.toThrow('Load failed');
    });
  });

  describe('sync', () => {
    it.each(['Failed to fetch', 'Load failed', 'NetworkError when attempting to fetch resource.'])(
      'reports Backend not available when the browser fails the request (%s)',
      async (message) => {
        vi.mocked(fetch).mockRejectedValueOnce(new TypeError(message));

        await expect(adapter.sync(CHANGES)).resolves.toEqual(BACKEND_NOT_AVAILABLE);
      },
    );

    it('reports Backend not available when the request times out', async () => {
      vi.mocked(fetch).mockRejectedValueOnce(new DOMException('The operation was aborted.', 'AbortError'));

      await expect(adapter.sync(CHANGES)).resolves.toEqual(BACKEND_NOT_AVAILABLE);
    });

    it.each([401, 408, 429, 502, 503, 504])(
      'reports Backend not available on HTTP %i: the same write may succeed later',
      async (status) => {
        vi.mocked(fetch).mockResolvedValueOnce(reply(status));

        await expect(adapter.sync(CHANGES)).resolves.toEqual(BACKEND_NOT_AVAILABLE);
      },
    );

    it('reports Backend not available when the session has no token, without sending anything', async () => {
      vi.mocked(getAuthToken).mockReturnValue(null);

      await expect(adapter.sync(CHANGES)).resolves.toEqual(BACKEND_NOT_AVAILABLE);
      expect(fetch).not.toHaveBeenCalled();
    });

    it.each([400, 422, 500])('rejects on HTTP %i: the server refused the write itself', async (status) => {
      vi.mocked(fetch).mockResolvedValueOnce(reply(status));

      await expect(adapter.sync(CHANGES)).rejects.toThrow('Failed to sync configs');
    });

    it('does not mistake a malformed answer for a network failure', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(reply(200, { success: true }));

      await expect(adapter.sync(CHANGES)).rejects.toBeInstanceOf(TypeError);
    });

    it('passes the answer of a delivered write through, conflicts included', async () => {
      vi.mocked(fetch).mockResolvedValueOnce(
        reply(200, { success: false, conflicts: ['personalSettings'], newVersions: { chatSettings: '2000_1' } }),
      );

      await expect(adapter.sync(CHANGES)).resolves.toEqual({
        success: false,
        conflicts: ['personalSettings'],
        newVersions: new Map([['chatSettings', '2000_1']]),
        error: undefined,
      });
    });
  });
});
