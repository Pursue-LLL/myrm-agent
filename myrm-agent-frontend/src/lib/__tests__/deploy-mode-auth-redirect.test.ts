import { afterEach, describe, expect, it } from 'vitest';

import { shouldRedirectToLoginOnAuthFailure } from '../deploy-mode';

describe('shouldRedirectToLoginOnAuthFailure', () => {
  const originalWindow = globalThis.window;
  const originalEnvMode = process.env.NEXT_PUBLIC_DEPLOY_MODE;

  afterEach(() => {
    if (originalEnvMode === undefined) {
      delete process.env.NEXT_PUBLIC_DEPLOY_MODE;
    } else {
      process.env.NEXT_PUBLIC_DEPLOY_MODE = originalEnvMode;
    }
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: originalWindow,
    });
  });

  it('returns true for sandbox build', () => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
    expect(shouldRedirectToLoginOnAuthFailure()).toBe(true);
  });

  it('returns false for local build', () => {
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'local';
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
