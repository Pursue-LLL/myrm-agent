/**
 * `resolveE2eApiBase`: the one switch every E2E-aware call site reads.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { resolveE2eApiBase } from '@/lib/deploy-mode';

type E2eWindow = Record<string, unknown>;

function setBinding(apiBase: string): void {
  (window as unknown as E2eWindow).__MYRM_E2E_API_BASE__ = apiBase;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.name = '';
  delete (window as unknown as E2eWindow).__MYRM_E2E_API_BASE__;
  delete (window as unknown as E2eWindow).__MYRM_E2E_RUNTIME__;
});

describe('resolveE2eApiBase', () => {
  it('is null on a page without a binding', () => {
    expect(resolveE2eApiBase()).toBeNull();
  });

  it.each([
    ['http://127.0.0.1:18080', 'http://127.0.0.1:18080'],
    ['http://localhost:18080/', 'http://localhost:18080'],
    ['  http://127.0.0.1:18080///  ', 'http://127.0.0.1:18080'],
    ['https://127.0.0.1:18443/api/v1', 'https://127.0.0.1:18443'],
  ])('reduces the bound backend %j to its origin', (bound, origin) => {
    setBinding(bound);
    expect(resolveE2eApiBase()).toBe(origin);
  });

  it('prefers the validated runtime identity over the bare base', () => {
    setBinding('http://127.0.0.1:18080');
    (window as unknown as E2eWindow).__MYRM_E2E_RUNTIME__ = { apiBase: 'http://127.0.0.1:18090' };
    expect(resolveE2eApiBase()).toBe('http://127.0.0.1:18090');
  });

  it.each([
    'http://example.com:18080',
    'http://192.168.1.5:18080',
    'http://127.0.0.1.evil.com:18080',
    'ftp://127.0.0.1:21',
    'not a url',
    '',
  ])('refuses the binding %j that does not point at a loopback http backend', (bound) => {
    setBinding(bound);
    expect(resolveE2eApiBase()).toBeNull();
  });

  it('ignores a window.name binding the page bootstrap did not validate', () => {
    window.name = 'myrm-e2e-v1:{"version":1,"apiBase":"http://127.0.0.1:18080"}';
    expect(resolveE2eApiBase()).toBeNull();
    expect((window as unknown as E2eWindow).__MYRM_E2E_API_BASE__).toBeUndefined();
  });

  it('is null in a production build even when a binding is present', () => {
    setBinding('http://127.0.0.1:18080');
    vi.stubEnv('NODE_ENV', 'production');
    expect(resolveE2eApiBase()).toBeNull();
  });

  it('is null without a window (server render)', () => {
    vi.stubGlobal('window', undefined);
    expect(resolveE2eApiBase()).toBeNull();
  });
});
