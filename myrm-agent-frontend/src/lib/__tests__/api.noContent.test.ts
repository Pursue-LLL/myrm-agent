/**
 * An answer without content reaches the caller of `apiRequest` as an empty object.
 *
 * `getJobDeliveryHealth` relies on it: the server answers 204 when a destination has nothing to judge.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../api';

vi.mock('@/lib/deploy-mode', () => ({
  getApiBaseUrl: () => 'http://127.0.0.1:8080/api/v1',
  getBackendBaseUrl: () => 'http://127.0.0.1:8080',
  shouldRedirectToLoginOnAuthFailure: () => true,
  isLocalMode: vi.fn(() => false),
  resolveE2eApiBase: () => '',
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: () => Promise.resolve(true),
  markLocalBackendUnreachable: () => undefined,
}));

vi.mock('@/store/useConfigStore', () => ({
  default: { getState: () => ({ personalSettings: undefined }) },
}));

describe('apiRequest on an answer without content', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    ['a 204', () => new Response(null, { status: 204 })],
    ['an empty 200', () => new Response('', { status: 200, headers: { 'content-length': '0' } })],
  ])('hands back an empty object for %s', async (_case, answer) => {
    vi.stubGlobal('fetch', vi.fn(async () => answer()));

    await expect(apiRequest('/cron/job-1/delivery-health', { silent: true })).resolves.toEqual({});
  });
});
