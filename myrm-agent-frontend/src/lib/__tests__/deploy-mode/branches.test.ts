/**
 * Deploy-mode branch coverage: agent API base, mode resolution and Tauri port fallbacks.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  backupLocalAuthToken,
  getAgentApiBaseUrl,
  getDeployMode,
  getLocalUserId,
  getRemoteGatewayConfig,
  isLoopbackDevHost,
  isTauriRuntime,
  setRemoteGatewayConfig,
  isSandbox,
  isSandboxAuthBuild,
  setRuntimeTauriBackendPort,
  shouldRedirectToLoginOnAuthFailure,
  showsLocalIntegrationTabs,
} from '@/lib/deploy-mode';

const ENV_KEYS = ['NEXT_PUBLIC_DEPLOY_MODE', 'NEXT_PUBLIC_API_BASE_URL', 'NEXT_PUBLIC_BACKEND_BASE_URL'] as const;

function snapshotEnv(): Record<string, string | undefined> {
  return Object.fromEntries(ENV_KEYS.map((key) => [key, process.env[key]]));
}

function restoreEnv(snapshot: Record<string, string | undefined>): void {
  for (const key of ENV_KEYS) {
    const value = snapshot[key];
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
}

const originalLocation = window.location;
const originalEnv = snapshotEnv();

afterEach(() => {
  vi.unstubAllGlobals();
  restoreEnv(originalEnv);
  setRuntimeTauriBackendPort(null);
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
  window.localStorage.clear();
  delete (window as unknown as Record<string, unknown>).__TAURI__;
  delete (window as unknown as Record<string, unknown>).__MYRM_E2E_API_BASE__;
  delete (window as unknown as Record<string, unknown>).__MYRM_E2E_RUNTIME__;
});

describe('getAgentApiBaseUrl', () => {
  it('honours the E2E isolated base first', () => {
    (window as unknown as Record<string, unknown>).__MYRM_E2E_API_BASE__ = 'http://127.0.0.1:18080';
    expect(getAgentApiBaseUrl()).toBe('http://127.0.0.1:18080/v1');
  });

  it('uses the runtime Tauri port when there is no configured base', () => {
    (window as unknown as Record<string, unknown>).__TAURI__ = {};
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, hostname: 'tauri.localhost' },
    });
    setRuntimeTauriBackendPort(25808);

    expect(getAgentApiBaseUrl()).toBe('http://127.0.0.1:25808/v1');
  });

  it('falls back to the configured backend in sandbox builds', () => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL = 'https://backend.example.com';

    expect(getAgentApiBaseUrl()).toBe('https://backend.example.com/v1');
  });
});

describe('deploy mode resolution', () => {
  it('defaults to tauri when the env is absent', () => {
    delete process.env.NEXT_PUBLIC_DEPLOY_MODE;
    expect(getDeployMode()).toBe('tauri');
    expect(isSandbox()).toBe(false);
    expect(isSandboxAuthBuild()).toBe(false);
  });

  it('reports sandbox builds and login redirects', () => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
    expect(getDeployMode()).toBe('sandbox');
    expect(isSandbox()).toBe(true);
    expect(isSandboxAuthBuild()).toBe(true);
    expect(shouldRedirectToLoginOnAuthFailure()).toBe(true);
  });

  it('treats a loopback host as a local integration surface', () => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, hostname: '127.0.0.1' },
    });
    expect(showsLocalIntegrationTabs()).toBe(true);
  });
});

describe('server-side (no window) guards', () => {
  it('returns safe defaults without a window object', () => {
    vi.stubGlobal('window', undefined);

    expect(getRemoteGatewayConfig()).toBeNull();
    expect(() => setRemoteGatewayConfig({ enabled: true, url: 'https://remote.example.com' })).not.toThrow();
    expect(backupLocalAuthToken()).toBeUndefined();
    expect(isTauriRuntime()).toBe(false);
    expect(isLoopbackDevHost()).toBe(false);
    expect(getDeployMode()).toBe('tauri');
    expect(getLocalUserId()).toBe('local_user');
  });
});
