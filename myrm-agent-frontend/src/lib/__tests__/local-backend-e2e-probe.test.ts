import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import {
  isChromeE2eTab,
  waitForChromeE2eBackendBinding,
} from '@/lib/local-backend-e2e-probe';

describe('isChromeE2eTab', () => {
  beforeEach(() => {
    delete window.__MYRM_E2E_API_BASE__;
    delete window.__MYRM_E2E_RUNTIME_READY__;
    window.name = '';
  });

  it('returns true when window.name carries an E2E runtime binding', () => {
    window.name = 'myrm-e2e-v1:{"version":1}';
    expect(isChromeE2eTab()).toBe(true);
  });

  it('returns true when __MYRM_E2E_API_BASE__ is injected', () => {
    window.__MYRM_E2E_API_BASE__ = 'http://127.0.0.1:18081';
    expect(isChromeE2eTab()).toBe(true);
  });

  it('returns false for ordinary dev tabs', () => {
    expect(isChromeE2eTab()).toBe(false);
  });
});

describe('waitForChromeE2eBackendBinding', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    delete window.__MYRM_E2E_API_BASE__;
    delete window.__MYRM_E2E_RUNTIME_READY__;
    window.name = '';
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('resolves true when __MYRM_E2E_RUNTIME_READY__ succeeds', async () => {
    window.name = 'myrm-e2e-v1:{"version":1}';
    window.__MYRM_E2E_RUNTIME_READY__ = Promise.resolve(
      Object.freeze({ version: 1, apiBase: 'http://127.0.0.1:18081' }),
    );

    await expect(waitForChromeE2eBackendBinding(1_000)).resolves.toBe(true);
  });

  it('returns false for non-E2E tabs', async () => {
    await expect(waitForChromeE2eBackendBinding(1_000)).resolves.toBe(false);
  });

  it('polls private health when only __MYRM_E2E_API_BASE__ is present', async () => {
    window.__MYRM_E2E_API_BASE__ = 'http://127.0.0.1:18081';
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ status: 'healthy' }), { status: 200 })),
    );
    vi.stubGlobal('fetch', fetchMock);

    const pending = waitForChromeE2eBackendBinding(1_000);
    await vi.advanceTimersByTimeAsync(250);
    await expect(pending).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:18081/api/v1/health',
      { cache: 'no-store' },
    );
  });
});
