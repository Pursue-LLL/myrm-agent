import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fetchMock = vi.fn();

vi.mock('@/lib/utils/apiConfig', () => ({
  getBackendUrl: () => 'http://127.0.0.1:8080',
}));

vi.mock('@/lib/e2ee', () => ({
  ensureE2EEClient: vi.fn(),
}));

describe('mobileRemotePost', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ success: true, code: 0, data: { ok: true } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
    } as unknown as Storage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends JSON bodies with an explicit application/json content type', async () => {
    const { mobileRemotePost } = await import('../mobileRemote');

    await mobileRemotePost('/api/v1/remote-access/mobile/spawn', {
      agent_id: 'builtin-general',
      project_id: null,
      initial_message: '帮我调研三家竞品的定价策略',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/v1/remote-access/mobile/spawn');
    expect(init.method).toBe('POST');
    // FastAPI only parses a JSON body when the content type declares it; a
    // missing header makes every remote POST fail with 422 "field required".
    const headers = init.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body as string)).toEqual({
      agent_id: 'builtin-general',
      project_id: null,
      initial_message: '帮我调研三家竞品的定价策略',
    });
  });
});
