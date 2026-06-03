import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { fetchWithTimeout } from '../api';

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => 'http://127.0.0.1:8080/api/v1',
  getBackendBaseUrl: () => 'http://127.0.0.1:8080',
  shouldRedirectToLoginOnAuthFailure: () => true,
}));

describe('fetchWithTimeout Global Auth Interceptor', () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;

  beforeEach(() => {
    const location = { href: '', pathname: '/test' } as Location;
    globalThis.window = { location } as Window & typeof globalThis;
    globalThis.document = { cookie: '' } as Document;

    const store = new Map<string, string>();
    globalThis.localStorage = {
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
    } as Storage;

    globalThis.fetch = vi.fn() as typeof fetch;
  });

  afterEach(() => {
    globalThis.window = originalWindow;
    globalThis.document = originalDocument;
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
