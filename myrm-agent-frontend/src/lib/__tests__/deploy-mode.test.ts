import { afterEach, describe, expect, it } from 'vitest';
import {
  getAgentApiBaseUrl,
  getApiBaseUrl,
  getBackendBaseUrl,
  getDocsUrl,
  getNotificationStreamUrl,
  getRemoteGatewayConfig,
  getRuntimeTauriBackendPort,
  isRemoteGatewayActive,
  setRuntimeTauriBackendPort,
} from '@/lib/deploy-mode';
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
    setRuntimeTauriBackendPort(null);
    restoreEnv(originalEnv);
  });

  it('uses local-mode relative api base when no sandbox override is active', () => {
    delete process.env.NEXT_PUBLIC_DEPLOY_MODE;
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.example.com/v1/';
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL = 'https://backend.example.com/';

    expect(getApiBaseUrl()).toBe('/api/v1');
    expect(getBackendBaseUrl()).toBe('');
    expect(getAgentApiBaseUrl()).toBe('http://127.0.0.1:8080/v1');
    expect(getNotificationStreamUrl()).toBe('/api/v1/notifications/stream');
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
    expect(getAgentApiBaseUrl()).toBe('https://backend.example.com/v1');
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

  it('prioritizes memory runtime tauri backend port over localStorage cache', () => {
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

    setRuntimeTauriBackendPort(3005);
    expect(getRuntimeTauriBackendPort()).toBe(3005);
    expect(getApiBaseUrl()).toBe('http://127.0.0.1:3005/api/v1');
    expect(getBackendBaseUrl()).toBe('http://127.0.0.1:3005');

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

// ── Remote Gateway ──────────────────────────────────────────────────────────

describe('remote gateway config', () => {
  const originalWindow = globalThis.window;

  function makeTauriWindow(storageEntries: Record<string, string> = {}) {
    const store = new Map(Object.entries(storageEntries));
    return {
      __TAURI__: {},
      location: { hostname: 'desktop.myrm.local' },
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => {
          store.set(k, v);
        },
        removeItem: (k: string) => {
          store.delete(k);
        },
      },
    };
  }

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
  });

  it('returns null when no remote gateway is configured', () => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: makeTauriWindow(),
    });
    expect(getRemoteGatewayConfig()).toBeNull();
    expect(isRemoteGatewayActive()).toBe(false);
  });

  it('parses valid remote gateway config from localStorage', () => {
    const cfg = JSON.stringify({ enabled: true, url: 'https://remote.example.com' });
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: makeTauriWindow({ 'myrm-remote-gateway': cfg }),
    });
    const result = getRemoteGatewayConfig();
    expect(result).toEqual({ enabled: true, url: 'https://remote.example.com' });
    expect(isRemoteGatewayActive()).toBe(true);
  });

  it('rejects disabled remote gateway config', () => {
    const cfg = JSON.stringify({ enabled: false, url: 'https://remote.example.com' });
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: makeTauriWindow({ 'myrm-remote-gateway': cfg }),
    });
    expect(getRemoteGatewayConfig()).toBeNull();
    expect(isRemoteGatewayActive()).toBe(false);
  });

  it('rejects invalid protocol in remote gateway url', () => {
    const cfg = JSON.stringify({ enabled: true, url: 'ftp://remote.example.com' });
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: makeTauriWindow({ 'myrm-remote-gateway': cfg }),
    });
    expect(getRemoteGatewayConfig()).toBeNull();
  });

  it('rejects malformed JSON in remote gateway storage', () => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: makeTauriWindow({ 'myrm-remote-gateway': 'not-json' }),
    });
    expect(getRemoteGatewayConfig()).toBeNull();
  });

  it('strips trailing slashes from remote gateway url', () => {
    const cfg = JSON.stringify({ enabled: true, url: 'https://remote.example.com///' });
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: makeTauriWindow({ 'myrm-remote-gateway': cfg }),
    });
    const result = getRemoteGatewayConfig();
    expect(result?.url).toBe('https://remote.example.com');
  });

  it('returns false for isRemoteGatewayActive in non-Tauri environment', () => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        location: { hostname: 'localhost' },
        localStorage: {
          getItem: () => JSON.stringify({ enabled: true, url: 'https://remote.example.com' }),
          setItem: () => undefined,
          removeItem: () => undefined,
        },
      },
    });
    expect(isRemoteGatewayActive()).toBe(false);
  });

  it('returns null for getRemoteGatewayConfig during SSR', () => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: undefined,
    });
    expect(getRemoteGatewayConfig()).toBeNull();
  });
});

describe('remote gateway URL routing', () => {
  const originalWindow = globalThis.window;
  const originalEnv = snapshotEnv();

  function makeTauriWindowWithRemote(remoteUrl: string) {
    const cfg = JSON.stringify({ enabled: true, url: remoteUrl });
    const store = new Map([['myrm-remote-gateway', cfg]]);
    return {
      __TAURI__: {},
      location: { hostname: 'desktop.myrm.local' },
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => {
          store.set(k, v);
        },
        removeItem: (k: string) => {
          store.delete(k);
        },
      },
    };
  }

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
    restoreEnv(originalEnv);
  });

  it('routes API calls to remote server when gateway is active', () => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: makeTauriWindowWithRemote('https://my-vps.example.com'),
    });

    expect(getApiBaseUrl()).toBe('https://my-vps.example.com/api/v1');
    expect(getBackendBaseUrl()).toBe('https://my-vps.example.com');
    expect(getAgentApiBaseUrl()).toBe('https://my-vps.example.com/v1');
    expect(getNotificationStreamUrl()).toBe('https://my-vps.example.com/api/v1/notifications/stream');
  });

  it('E2E override takes priority over remote gateway', () => {
    const tauriWin = makeTauriWindowWithRemote('https://my-vps.example.com');
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        ...tauriWin,
        __MYRM_E2E_API_BASE__: 'http://127.0.0.1:19999/',
      },
    });

    expect(getApiBaseUrl()).toBe('http://127.0.0.1:19999/api/v1');
    expect(getBackendBaseUrl()).toBe('http://127.0.0.1:19999');
  });

  it('falls back to local backend when remote gateway is removed', () => {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        __TAURI__: {},
        location: { hostname: 'desktop.myrm.local' },
        localStorage: {
          getItem: () => null,
          setItem: () => undefined,
          removeItem: () => undefined,
        },
      },
    });

    expect(getApiBaseUrl()).toBe('http://127.0.0.1:8080/api/v1');
    expect(getBackendBaseUrl()).toBe('http://127.0.0.1:8080');
  });
});
