import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { markLocalBackendUnreachable } from '@/lib/backend-health';
import { TauriConfigAdapter } from '@/services/config/adapters/TauriAdapter';
import type { ConfigChange } from '@/services/config/types';

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => '/api/v1',
}));

vi.mock('@/lib/backend-health', () => ({
  markLocalBackendUnreachable: vi.fn(),
}));

vi.mock('@/lib/platform-readiness', () => ({
  whenDatabaseReady: vi.fn(async () => true),
}));

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

    const changes: ConfigChange[] = [
      {
        key: 'personalSettings',
        value: { systemInstructions: 'test' },
        expectedVersion: '0_0',
        timestamp: Date.now(),
      },
    ];

    await expect(adapter.sync(changes)).resolves.toEqual({
      success: false,
      conflicts: [],
      newVersions: new Map(),
      error: 'Backend not available',
    });
    expect(markLocalBackendUnreachable).toHaveBeenCalledTimes(1);
  });

  it('getAll returns empty map on HTTP 502', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
    } as Response);

    await expect(adapter.getAll()).resolves.toEqual(new Map());
  });

  it('getAll returns empty map when localFetch times out (AbortError)', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new DOMException('The operation was aborted.', 'AbortError'));

    await expect(adapter.getAll()).resolves.toEqual(new Map());
    expect(markLocalBackendUnreachable).toHaveBeenCalledTimes(1);
  });
});
