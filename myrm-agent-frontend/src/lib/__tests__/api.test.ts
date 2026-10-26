import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { apiRequest, fetchOnPageExit, fetchWithTimeout, getApiUrl, getStorageUrl } from '../api';

const ensureLocalBackendReady = vi.fn<(...args: unknown[]) => Promise<boolean>>(() => Promise.resolve(true));
const markLocalBackendUnreachable = vi.fn<(...args: unknown[]) => unknown>(() => undefined);
const resolveBackendUnreachableMessage = vi.fn<(...args: unknown[]) => Promise<string>>(() =>
  Promise.resolve('Backend not reachable. Run: myrm dev or myrm start.'),
);

const toastMock = vi.hoisted(() =>
  Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
);

vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => 'http://127.0.0.1:8080/api/v1',
  getBackendBaseUrl: () => 'http://127.0.0.1:8080',
  shouldRedirectToLoginOnAuthFailure: () => true,
  isLocalMode: vi.fn(() => true),
  resolveE2eApiBase: () => '',
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: (...args: unknown[]) => ensureLocalBackendReady(...args),
  markLocalBackendUnreachable: (...args: unknown[]) => markLocalBackendUnreachable(...args),
}));

vi.mock('@/lib/local-backend-dev', () => ({
  BACKEND_UNREACHABLE_CODE: 'BACKEND_UNREACHABLE',
  resolveBackendUnreachableMessage: (...args: unknown[]) => resolveBackendUnreachableMessage(...args),
}));

const mockConfigGetState = vi.fn(() => ({
  personalSettings: undefined as { locale?: string } | undefined,
}));

vi.mock('@/store/useConfigStore', () => ({
  default: {
    getState: () => mockConfigGetState(),
  },
}));

describe('getApiUrl', () => {
  it('routes /webui paths without /api/v1 prefix', () => {
    expect(getApiUrl('/webui/desktop/permissions')).toBe('http://127.0.0.1:8080/webui/desktop/permissions');
  });

  it('keeps /api/v1 prefix for standard API endpoints', () => {
    expect(getApiUrl('/integrations/mcp/options')).toBe('http://127.0.0.1:8080/api/v1/integrations/mcp/options');
  });
});

describe('getStorageUrl', () => {
  it('maps vault:// pointers to vault content API', () => {
    expect(getStorageUrl('vault://550e8400-e29b-41d4-a716-446655440000')).toBe(
      'http://127.0.0.1:8080/api/v1/files/vault/550e8400-e29b-41d4-a716-446655440000/content',
    );
  });

  it('strips line-range suffix from vault URIs', () => {
    expect(getStorageUrl('vault://550e8400-e29b-41d4-a716-446655440000:1-50')).toBe(
      'http://127.0.0.1:8080/api/v1/files/vault/550e8400-e29b-41d4-a716-446655440000/content',
    );
  });

  it('prefixes relative storage paths with backend base URL', () => {
    expect(getStorageUrl('/api/v1/files/storage/abc')).toBe('http://127.0.0.1:8080/api/v1/files/storage/abc');
  });
});

describe('fetchWithTimeout Global Auth Interceptor', () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const originalLocalStorage = globalThis.localStorage;
  const originalSessionStorage = globalThis.sessionStorage;
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    const location = { href: '', pathname: '/test', search: '', hash: '' } as Location;
    const store = new Map<string, string>();
    const sessionStore = new Map<string, string>();

    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: { location } as Window & typeof globalThis,
    });
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      value: { cookie: '' } as Document,
    });
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => {
          store.set(key, value);
        },
        removeItem: (key: string) => {
          store.delete(key);
        },
        clear: () => {
          store.clear();
        },
      } as Storage,
    });
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      value: {
        getItem: (key: string) => sessionStore.get(key) ?? null,
        setItem: (key: string, value: string) => {
          sessionStore.set(key, value);
        },
        removeItem: (key: string) => {
          sessionStore.delete(key);
        },
        clear: () => {
          sessionStore.clear();
        },
      } as Storage,
    });
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: vi.fn() as typeof fetch,
    });
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      value: originalDocument,
    });
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: originalLocalStorage,
    });
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      value: originalSessionStorage,
    });
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: originalFetch,
    });
    vi.restoreAllMocks();
  });

  it('removes auth_token and redirects to /auth/login on 401 response', async () => {
    localStorage.setItem('auth_token', 'test-token');

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      status: 401,
      ok: false,
    } as Response);

    await fetchWithTimeout('/some-endpoint', {}, 0);

    expect(localStorage.getItem('auth_token')).toBeNull();
    expect(window.location.href).toBe('/auth/login');
  });

  it('does not redirect if already on /auth/login', async () => {
    window.location.pathname = '/auth/login';
    localStorage.setItem('auth_token', 'test-token');

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      status: 403,
      ok: false,
    } as Response);

    await fetchWithTimeout('/some-endpoint', {}, 0);

    expect(localStorage.getItem('auth_token')).toBeNull();
    expect(window.location.href).toBe('');
  });

  it('fetchOnPageExit sends a keepalive request in the same tick, before any readiness probe could resolve', () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ status: 200, ok: true } as Response);

    fetchOnPageExit('/webui/vnc/resume', { method: 'POST' });

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8080/webui/vnc/resume',
      expect.objectContaining({ method: 'POST', keepalive: true, credentials: 'include', cache: 'no-store' }),
    );
  });

  it('fetchOnPageExit swallows a failed request', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new TypeError('Failed to fetch'));

    expect(() => fetchOnPageExit('/webui/vnc/resume', { method: 'POST' })).not.toThrow();
    await Promise.resolve();
  });
});

describe('apiRequest local backend gate', () => {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    ensureLocalBackendReady.mockReset();
    ensureLocalBackendReady.mockResolvedValue(true);
    resolveBackendUnreachableMessage.mockClear();
    markLocalBackendUnreachable.mockClear();
    mockConfigGetState.mockReturnValue({ personalSettings: undefined });

    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: { location: { href: '', pathname: '/test', search: '', hash: '' } } as Window & typeof globalThis,
    });
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: vi.fn() as typeof fetch,
    });
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: originalFetch,
    });
    vi.restoreAllMocks();
  });

  it('throws BACKEND_UNREACHABLE when local gate is not ready', async () => {
    ensureLocalBackendReady.mockResolvedValueOnce(false);

    await expect(apiRequest('/projects', { silent: true })).rejects.toMatchObject({
      businessCode: 'BACKEND_UNREACHABLE',
      code: 503,
      message: 'Backend not reachable. Run: myrm dev or myrm start.',
    });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('maps Next proxy plain-text 500 to BACKEND_UNREACHABLE', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
      text: () => Promise.resolve('Internal Server Error'),
      clone: () => ({
        text: () => Promise.resolve('Internal Server Error'),
      }),
      headers: new Headers(),
    } as Response);

    await expect(apiRequest('/projects', { silent: true })).rejects.toMatchObject({
      businessCode: 'BACKEND_UNREACHABLE',
      message: 'Backend not reachable. Run: myrm dev or myrm start.',
    });
    expect(resolveBackendUnreachableMessage).toHaveBeenCalled();
  });

  it('parses valid JSON 500 without remapping to BACKEND_UNREACHABLE', async () => {
    const jsonBody = JSON.stringify({ message: 'Server exploded' });
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
      text: () => Promise.resolve(jsonBody),
      clone: () => ({
        text: () => Promise.resolve(jsonBody),
      }),
      headers: new Headers({ 'content-type': 'application/json' }),
    } as Response);

    await expect(apiRequest('/projects', { silent: true })).rejects.toMatchObject({
      message: 'Server exploded',
    });
    expect(resolveBackendUnreachableMessage).not.toHaveBeenCalled();
  });

  it('fetchWithTimeout throws BACKEND_UNREACHABLE on Next proxy 500', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
      clone: () => ({
        text: () => Promise.resolve('Internal Server Error'),
      }),
      headers: new Headers(),
    } as Response);

    const { fetchWithTimeout } = await import('../api');
    await expect(fetchWithTimeout('/chats/x/subagents', {}, 0)).rejects.toMatchObject({
      businessCode: 'BACKEND_UNREACHABLE',
    });
  });

  it('fetchWithTimeout maps Failed to fetch to BACKEND_UNREACHABLE in local mode', async () => {
    ensureLocalBackendReady.mockResolvedValueOnce(true);
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new TypeError('Failed to fetch'));

    const { fetchWithTimeout } = await import('../api');
    await expect(fetchWithTimeout('/chats', {}, 0)).rejects.toMatchObject({
      businessCode: 'BACKEND_UNREACHABLE',
    });
    expect(resolveBackendUnreachableMessage).toHaveBeenCalled();
    expect(markLocalBackendUnreachable).toHaveBeenCalledTimes(1);
  });

  it('sends Accept-Language from personalSettings locale', async () => {
    mockConfigGetState.mockReturnValueOnce({ personalSettings: { locale: 'zh' } });
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ applied: false, checklist: [] }),
    } as Response);

    await apiRequest('/config/onboarding/second-brain/status', { silent: true });

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/config/onboarding/second-brain/status'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Accept-Language': 'zh-CN',
        }),
      }),
    );
  });

  it('does not override caller-provided Accept-Language', async () => {
    mockConfigGetState.mockReturnValueOnce({ personalSettings: { locale: 'zh' } });
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ applied: false, checklist: [] }),
    } as Response);

    await apiRequest('/config/onboarding/second-brain/status', {
      silent: true,
      headers: { 'Accept-Language': 'en' },
    });

    expect(fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Accept-Language': 'en',
        }),
      }),
    );
  });

  it('keeps merged auth and locale headers when fetchOptions includes headers', async () => {
    localStorage.setItem('auth_token', 'test-token');
    mockConfigGetState.mockReturnValueOnce({ personalSettings: { locale: 'zh' } });
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ ok: true }),
    } as Response);

    await apiRequest('/config/onboarding/second-brain/apply', {
      silent: true,
      method: 'POST',
      body: '{}',
      headers: { 'X-Test': '1' },
    });

    expect(fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
          'Accept-Language': 'zh-CN',
          'X-Test': '1',
        }),
      }),
    );
    localStorage.removeItem('auth_token');
  });
});

describe('apiRequest risk-held refusal', () => {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;
  const refusal = {
    detail: {
      code: 'risk_held',
      message: 'Text held by a risk rule',
      rules: [{ rule_id: 'api_key_like', display_name: 'API key or cloud credential pattern', severity: 'critical' }],
    },
  };

  const respond = (status: number, body: unknown) => {
    const text = () => Promise.resolve(JSON.stringify(body));
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status,
      text,
      clone: () => ({ text }),
      headers: new Headers(),
    });
  };

  beforeEach(async () => {
    ensureLocalBackendReady.mockResolvedValue(true);
    toastMock.error.mockClear();
    toastMock.warning.mockClear();
    const { setGlobalTranslator } = await import('@/services/i18nToastService');
    setGlobalTranslator(
      Object.assign(
        (key: string, values?: Record<string, unknown>) =>
          key === 'settings.securityPolicy.riskRules.blockedTitle'
            ? 'Message blocked'
            : key === 'settings.securityPolicy.riskRules.blockedDescription'
              ? `Matched: ${String(values?.rules)}`
              : key,
        { has: () => false },
      ),
    );
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: { location: { href: '', pathname: '/test', search: '', hash: '' } } as Window & typeof globalThis,
    });
    Object.defineProperty(globalThis, 'fetch', { configurable: true, value: vi.fn() as typeof fetch });
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
    Object.defineProperty(globalThis, 'fetch', { configurable: true, value: originalFetch });
    vi.restoreAllMocks();
  });

  it('shows the localized held notice, not the server English sentence, every time the text is sent', async () => {
    respond(400, refusal);

    for (let attempt = 0; attempt < 2; attempt += 1) {
      await expect(apiRequest('/kanban/tasks/t1/comments', { method: 'POST' })).rejects.toMatchObject({
        businessCode: 'risk_held',
      });
    }

    await vi.waitFor(() => expect(toastMock.error).toHaveBeenCalledTimes(2));
    expect(toastMock.error).toHaveBeenCalledWith('Message blocked', {
      description: 'Matched: API key or cloud credential pattern',
      duration: 10_000,
    });
    expect(toastMock.warning).not.toHaveBeenCalled();
  });

  it('shows no toast for a silent call', async () => {
    respond(400, refusal);

    await expect(apiRequest('/kanban/tasks/t1/comments', { method: 'POST', silent: true })).rejects.toBeDefined();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(toastMock.error).not.toHaveBeenCalled();
  });

  it('leaves any other error to the generic error toast', async () => {
    respond(500, { detail: 'Scheduler unavailable' });

    await expect(apiRequest('/cron', { method: 'POST' })).rejects.toBeDefined();

    await vi.waitFor(() => expect(toastMock.error).toHaveBeenCalledTimes(1));
    expect(toastMock.error).toHaveBeenCalledWith('Scheduler unavailable', expect.anything());
  });
});
