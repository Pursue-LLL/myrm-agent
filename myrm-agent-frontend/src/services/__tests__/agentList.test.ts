import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import { listAgents, type AgentListResponse } from '../agent';

const ensureLocalBackendReady = vi.hoisted(() => vi.fn<() => Promise<boolean>>());
const toastMock = vi.hoisted(() =>
  Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
);

vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => 'http://127.0.0.1:8080/api/v1',
  getBackendBaseUrl: () => 'http://127.0.0.1:8080',
  shouldRedirectToLoginOnAuthFailure: () => false,
  isLocalMode: () => true,
  resolveE2eApiBase: () => '',
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: () => ensureLocalBackendReady(),
  markLocalBackendUnreachable: vi.fn(),
}));

vi.mock('@/lib/local-backend-dev', () => ({
  BACKEND_UNREACHABLE_CODE: 'BACKEND_UNREACHABLE',
  resolveBackendUnreachableMessage: () => Promise.resolve('Backend not reachable.'),
}));

vi.mock('@/store/useConfigStore', () => ({
  default: { getState: () => ({ personalSettings: undefined }) },
}));

const PAGE: AgentListResponse = {
  items: [{ id: 'agent-1', name: 'Agent One', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }],
  pagination: { page: 2, page_size: 20, total: 21, total_pages: 2, has_next: false, has_prev: true },
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('listAgents', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.clearAllMocks();
    ensureLocalBackendReady.mockResolvedValue(true);
    vi.stubGlobal('fetch', fetchMock);
  });

  it('requests the page through the shared API client and unwraps the data envelope', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { success: true, code: 200, data: PAGE }));

    await expect(listAgents(2, 20)).resolves.toEqual(PAGE);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://127.0.0.1:8080/api/v1/user-agents?page=2&page_size=20');
    expect(init?.method).toBe('GET');
    // The roster changes through writes on other URLs, so it must never be served from the HTTP cache.
    expect(init?.cache).toBe('no-store');
  });

  it('waits for the local backend before sending the request', async () => {
    let releaseGate: (ready: boolean) => void = () => undefined;
    ensureLocalBackendReady.mockReturnValue(new Promise<boolean>((resolve) => (releaseGate = resolve)));
    fetchMock.mockResolvedValue(jsonResponse(200, { success: true, code: 200, data: PAGE }));

    const pending = listAgents(1, 50);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).not.toHaveBeenCalled();

    releaseGate(true);
    await expect(pending).resolves.toEqual(PAGE);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('rejects without any request when the local backend never becomes ready', async () => {
    ensureLocalBackendReady.mockResolvedValue(false);

    await expect(listAgents()).rejects.toMatchObject({ name: 'ApiError', code: 503, message: 'Backend not reachable.' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects with the backend message and keeps the failure toast-free for the caller to present', async () => {
    fetchMock.mockResolvedValue(jsonResponse(500, { detail: 'roster storage offline' }));

    const failure = await listAgents(1, 50).catch((error: unknown) => error);
    await vi.dynamicImportSettled();

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ message: 'roster storage offline', code: 500 });
    expect(toastMock).not.toHaveBeenCalled();
    expect(toastMock.error).not.toHaveBeenCalled();
    expect(toastMock.warning).not.toHaveBeenCalled();
  });
});
