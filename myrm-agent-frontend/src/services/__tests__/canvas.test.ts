import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { createCanvasEventSource, listCanvases } from '../canvas';

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => 'http://127.0.0.1:8080/api/v1',
  getBackendBaseUrl: () => 'http://127.0.0.1:8080',
  isLocalMode: () => false,
  shouldRedirectToLoginOnAuthFailure: () => false,
}));

describe('canvas service URLs', () => {
  const originalFetch = globalThis.fetch;
  const OriginalEventSource = globalThis.EventSource;

  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true, data: [] }),
      } as Response),
    );
  });

  afterEach(() => {
    vi.stubGlobal('fetch', originalFetch);
    if (OriginalEventSource) {
      vi.stubGlobal('EventSource', OriginalEventSource);
    }
    vi.restoreAllMocks();
  });

  it('listCanvases requests a single /api/v1 prefix via getApiUrl', async () => {
    await listCanvases();
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8080/api/v1/canvas',
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it('createCanvasEventSource uses getApiUrl without double prefix', () => {
    const canvasId = '11111111-2222-3333-4444-555555555555';
    const eventSourceCtor = vi.fn();
    vi.stubGlobal('EventSource', eventSourceCtor);

    createCanvasEventSource(canvasId);

    expect(eventSourceCtor).toHaveBeenCalledWith(
      `http://127.0.0.1:8080/api/v1/canvas/${canvasId}/events`,
    );
  });
});
