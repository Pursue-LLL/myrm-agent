import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockFetchStatus, manager } = vi.hoisted(() => ({
  mockFetchStatus: vi.fn(),
  manager: {
    status: 'ready' as 'ready' | 'offline',
    stored: undefined as unknown,
    initialize: vi.fn(async () => {}),
    get: vi.fn(() => undefined as unknown),
    set: vi.fn(),
    subscribe: vi.fn(() => () => {}),
  },
}));

vi.mock('@/services/config', () => ({ getConfigSyncManager: () => manager }));
vi.mock('@/services/provider-oauth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/provider-oauth')>()),
  fetchProviderOAuthStatus: mockFetchStatus,
}));
vi.mock('@/lib/backend-health', () => ({ ensureLocalBackendReady: vi.fn(async () => {}) }));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isLocalMode: () => false,
}));
vi.mock('@/lib/platform-readiness', () => ({ ensurePlatformReadiness: vi.fn(async () => ({ database: false })) }));

import useProviderStore from '../useProviderStore';
import { getInitialDefaultModelConfig, getInitialProviders } from '../config/providerTypes';

const xaiFlag = () => useProviderStore.getState().providers.find((p) => p.id === 'xai')?.oauthConnected;

/** Lets the fire-and-forget reconciliation that `initProviders` starts run to completion. */
const settleReconciliation = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

function storeXaiLogin(oauthConnected: boolean) {
  manager.stored = {
    providers: getInitialProviders().map((p) => (p.id === 'xai' ? { ...p, oauthConnected } : p)),
    defaultModelConfig: getInitialDefaultModelConfig(),
    customModelInfo: {},
  };
}

describe('useProviderStore.initProviders: subscription login reconciliation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    manager.status = 'ready';
    manager.get.mockImplementation(() => manager.stored);
  });

  it('clears a stored login the server no longer backs once the providers are loaded', async () => {
    storeXaiLogin(true);
    mockFetchStatus.mockResolvedValue({ provider: 'xai', issuer: 'xai', connected: false });

    await useProviderStore.getState().retryInit();
    await settleReconciliation();

    expect(mockFetchStatus).toHaveBeenCalledExactlyOnceWith('xai');
    expect(xaiFlag()).toBe(false);
  });

  it('records a login the stored flag does not know about', async () => {
    storeXaiLogin(false);
    mockFetchStatus.mockResolvedValue({ provider: 'xai', issuer: 'xai', connected: true });

    await useProviderStore.getState().retryInit();
    await settleReconciliation();

    expect(xaiFlag()).toBe(true);
  });

  it('keeps a login completed while the status request is in flight', async () => {
    storeXaiLogin(false);
    mockFetchStatus.mockImplementation(async () => {
      useProviderStore.getState().updateProvider('xai', { oauthConnected: true });
      return { provider: 'xai', issuer: 'xai', connected: false };
    });

    await useProviderStore.getState().retryInit();
    await settleReconciliation();

    expect(xaiFlag()).toBe(true);
  });

  it('keeps a logout completed while the status request is in flight', async () => {
    storeXaiLogin(true);
    mockFetchStatus.mockImplementation(async () => {
      useProviderStore.getState().updateProvider('xai', { oauthConnected: false });
      return { provider: 'xai', issuer: 'xai', connected: true };
    });

    await useProviderStore.getState().retryInit();
    await settleReconciliation();

    expect(xaiFlag()).toBe(false);
  });

  it('does not reconcile while the backend is offline', async () => {
    manager.stored = undefined;
    manager.status = 'offline';

    await useProviderStore.getState().retryInit();
    await settleReconciliation();

    expect(mockFetchStatus).not.toHaveBeenCalled();
  });
});
