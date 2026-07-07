import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { TauriConfigAdapter } from '@/services/config/adapters/TauriAdapter';
import type { ConfigChange } from '@/services/config/types';

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => '/api/v1',
}));

describe('TauriConfigAdapter backend unavailable', () => {
  const originalFetch = globalThis.fetch;
  let adapter: TauriConfigAdapter;

  beforeEach(() => {
    adapter = new TauriConfigAdapter();
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
  });

  it('getAll returns empty map on HTTP 502', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
    } as Response);

    await expect(adapter.getAll()).resolves.toEqual(new Map());
  });
});
