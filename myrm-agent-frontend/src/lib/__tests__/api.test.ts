import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { apiRequest, fetchWithTimeout, getApiUrl, getStorageUrl } from '../api';

const ensureLocalBackendReady = vi.fn(() => Promise.resolve(true));
const resolveBackendUnreachableMessage = vi.fn(() =>
  Promise.resolve('Backend not reachable. Run: myrm dev or myrm start.'),
);

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => 'http://127.0.0.1:8080/api/v1',
  getBackendBaseUrl: () => 'http://127.0.0.1:8080',
  shouldRedirectToLoginOnAuthFailure: () => true,
  isLocalMode: vi.fn(() => true),
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: (...args: unknown[]) => ensureLocalBackendReady(...args),
}));

vi.mock('@/lib/local-backend-dev', () => ({
  BACKEND_UNREACHABLE_CODE: 'BACKEND_UNREACHABLE',
  resolveBackendUnreachableMessage: (...args: unknown[]) => resolveBackendUnreachableMessage(...args),
}));

describe('getApiUrl', () => {
  it('routes /webui paths without /api/v1 prefix', () => {
    expect(getApiUrl('/webui/desktop/permissions')).toBe(
      'http://127.0.0.1:8080/webui/desktop/permissions',
    );
  });

  it('keeps /api/v1 prefix for standard API endpoints', () => {
    expect(getApiUrl('/integrations/mcp/options')).toBe(
      'http://127.0.0.1:8080/api/v1/integrations/mcp/options',
    );
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
    expect(getStorageUrl('/api/v1/files/storage/abc')).toBe(
      'http://127.0.0.1:8080/api/v1/files/storage/abc',
    );
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
});

describe('apiRequest local backend gate', () => {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    ensureLocalBackendReady.mockReset();
    ensureLocalBackendReady.mockResolvedValue(true);
    resolveBackendUnreachableMessage.mockClear();

    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: { location: { href: '', pathname: '/test', search: '', hash: '' } } as Window &
        typeof globalThis,
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
});
