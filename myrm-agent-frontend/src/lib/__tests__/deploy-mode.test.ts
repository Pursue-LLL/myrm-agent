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

  it('builds extension bridge websocket url from configured api base', () => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
    process.env.NEXT_PUBLIC_API_BASE_URL = 'https://cp.example.com/proxy/me/api/v1';

    expect(getWsUrl('/ws/extension')).toBe('wss://cp.example.com/proxy/me/api/v1/ws/extension');
  });

  it('resolves docs url from env with default fallback', () => {
    process.env.NEXT_PUBLIC_DOCS_URL = 'https://docs.example.com/';
    expect(getDocsUrl()).toBe('https://docs.example.com');
    expect(getDocsUrl('/getting-started')).toBe('https://docs.example.com/getting-started');

    delete process.env.NEXT_PUBLIC_DOCS_URL;
    expect(getDocsUrl()).toBe('https://docs.myrm.ai');
  });
});
