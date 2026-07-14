import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => true,
}));

vi.mock('@/lib/backend-health', () => ({
  BACKEND_HEALTH_MAX_ATTEMPTS: 2,
  BACKEND_HEALTH_POLL_INTERVAL_MS: 1,
  waitForBackendReady: vi.fn(async () => true),
}));

describe('platform-readiness', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.endsWith('/api/v1/health/ready')) {
          return {
            ok: true,
            json: async () => ({ ready: true, checks: { database: true } }),
          } as Response;
        }
        return { ok: false } as Response;
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('resolves when database check passes', async () => {
    const { whenDatabaseReady, resetPlatformReadinessForTests } = await import('@/lib/platform-readiness');
    resetPlatformReadinessForTests();
    await expect(whenDatabaseReady()).resolves.toBe(true);
  });

  it('marks unreachable and re-warms after transport failure', async () => {
    const { getPlatformReadinessSnapshot, markPlatformUnreachable, resetPlatformReadinessForTests } = await import(
      '@/lib/platform-readiness'
    );
    resetPlatformReadinessForTests();
    markPlatformUnreachable();
    expect(getPlatformReadinessSnapshot().state).toBe('unreachable');
  });
});
