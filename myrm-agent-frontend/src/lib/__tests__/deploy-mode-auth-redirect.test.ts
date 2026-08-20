import { afterEach, describe, expect, it, vi } from 'vitest';

import { shouldRedirectToLoginOnAuthFailure } from '../deploy-mode';

describe('shouldRedirectToLoginOnAuthFailure', () => {
  const originalWindow = globalThis.window;

  afterEach(() => {
    vi.unstubAllEnvs();
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
  });

  it('returns true for sandbox build', () => {
    vi.stubEnv('NEXT_PUBLIC_DEPLOY_MODE', 'sandbox');
    expect(shouldRedirectToLoginOnAuthFailure()).toBe(true);
  });

  it('returns false for local build', () => {
    vi.stubEnv('NEXT_PUBLIC_DEPLOY_MODE', 'local');
    expect(shouldRedirectToLoginOnAuthFailure()).toBe(false);
  });

  it('returns true when Tauri desktop has active remote gateway', () => {
    const cfg = JSON.stringify({ enabled: true, url: 'https://remote.example.com' });
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        __TAURI__: {},
        location: { hostname: 'desktop.myrm.local' },
        localStorage: {
          getItem: (k: string) => (k === 'myrm-remote-gateway' ? cfg : null),
          setItem: () => undefined,
          removeItem: () => undefined,
        },
      },
    });
    expect(shouldRedirectToLoginOnAuthFailure()).toBe(true);
  });

  it('returns false for Tauri desktop without remote gateway', () => {
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
    expect(shouldRedirectToLoginOnAuthFailure()).toBe(false);
  });
});
