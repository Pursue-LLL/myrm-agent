import { afterEach, describe, expect, it } from 'vitest';
import { getApiBaseUrl, getBackendBaseUrl, getDocsUrl } from '@/lib/deploy-mode';
import { getWsUrl } from '@/lib/api';

const ENV_KEYS = ['NEXT_PUBLIC_DEPLOY_MODE', 'NEXT_PUBLIC_API_BASE_URL', 'NEXT_PUBLIC_BACKEND_BASE_URL'] as const;
type EnvKey = (typeof ENV_KEYS)[number];
type EnvSnapshot = Record<EnvKey, string | undefined>;

function snapshotEnv(): EnvSnapshot {
  return {
    NEXT_PUBLIC_DEPLOY_MODE: process.env.NEXT_PUBLIC_DEPLOY_MODE,
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
    NEXT_PUBLIC_BACKEND_BASE_URL: process.env.NEXT_PUBLIC_BACKEND_BASE_URL,
  };
}

function restoreEnv(snapshot: EnvSnapshot): void {
  for (const key of ENV_KEYS) {
    const value = snapshot[key];
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
}

describe('deploy-mode base url resolution', () => {
  const originalEnv = snapshotEnv();

  afterEach(() => {
    restoreEnv(originalEnv);
  });

  it('uses local-mode relative api base when no sandbox override is active', () => {
    delete process.env.NEXT_PUBLIC_DEPLOY_MODE;
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.com/v1/';
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL = 'https://backend.example.com/';

    expect(getApiBaseUrl()).toBe('/api/v1');
    expect(getBackendBaseUrl()).toBe('');
  });

  it('rejects invalid configured base urls in sandbox mode', () => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
    process.env.NEXT_PUBLIC_API_BASE_URL = 'undefined';
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL = 'null';

    expect(getApiBaseUrl()).toBe('http://127.0.0.1:8080/api/v1');
    expect(getBackendBaseUrl()).toBe('http://127.0.0.1:8080');
  });

  it('normalizes valid configured base urls in sandbox mode', () => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.com/v1/';
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL = 'https://backend.example.com/';

    expect(getApiBaseUrl()).toBe('https://api.example.com/v1');
    expect(getBackendBaseUrl()).toBe('https://backend.example.com');
  });

  it('builds sandbox websocket url from configured api base', () => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://cp.example.com/proxy/me/api/v1';

    expect(getWsUrl('/ws/voice/session')).toBe('wss://cp.example.com/proxy/me/api/v1/ws/voice/session');
  });

  it('resolves docs url from env with default fallback', () => {
    process.env.NEXT_PUBLIC_DOCS_URL = 'https://docs.example.com/';
    expect(getDocsUrl()).toBe('https://docs.example.com');
    expect(getDocsUrl('/getting-started')).toBe('https://docs.example.com/getting-started');

    delete process.env.NEXT_PUBLIC_DOCS_URL;
    expect(getDocsUrl()).toBe('https://docs.myrm.ai');
  });

  it('uses Next proxy for tauri runtime on loopback dev host', () => {
    const originalWindow = globalThis.window;
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        ...originalWindow,
        __TAURI__: {},
        location: { hostname: '127.0.0.1' },
        localStorage: {
          getItem: () => null,
          setItem: () => undefined,
        },
      },
    });

    expect(getApiBaseUrl()).toBe('/api/v1');
    expect(getBackendBaseUrl()).toBe('');

    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
  });

  it('uses desktop backend port 8080 for tauri runtime off loopback host', () => {
    const originalWindow = globalThis.window;
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        ...originalWindow,
        __TAURI__: {},
        location: { hostname: 'desktop.myrm.local' },
        localStorage: {
          getItem: () => null,
          setItem: () => undefined,
        },
      },
    });

    expect(getApiBaseUrl()).toBe('http://127.0.0.1:8080/api/v1');
    expect(getBackendBaseUrl()).toBe('http://127.0.0.1:8080');

    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
  });

  it('uses webui api port for tauri runtime when webui mode cached', () => {
    const originalWindow = globalThis.window;
    const mockWindow = {
      __TAURI__: {},
      location: { hostname: 'desktop.myrm.local' },
      localStorage: {
        getItem: () => JSON.stringify({ enableWebUIMode: true, apiPort: 25808 }),
        setItem: () => undefined,
      },
    };
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: mockWindow,
    });

    expect(getApiBaseUrl()).toBe('http://127.0.0.1:25808/api/v1');
    expect(getBackendBaseUrl()).toBe('http://127.0.0.1:25808');

    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
  });

  it('uses injected E2E private backend base for SHPOIB chrome tests', () => {
    const originalWindow = globalThis.window;
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        __MYRM_E2E_API_BASE__: 'http://127.0.0.1:18143/',
      },
    });

    expect(getApiBaseUrl()).toBe('http://127.0.0.1:18143/api/v1');
    expect(getBackendBaseUrl()).toBe('http://127.0.0.1:18143');

    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
  });
});
