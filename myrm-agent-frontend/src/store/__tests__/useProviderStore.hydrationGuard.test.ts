/**
 * Regression cover: the provider store must never push its seed state to the server.
 *
 * Before the server config is loaded, `providers` still holds the built-in defaults (every provider
 * disabled). Writing that to the server wiped the real configuration — the user's enabled providers and
 * the default model disappeared, and the instance ended up with no usable model at all.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { manager } = vi.hoisted(() => ({
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
  fetchProviderOAuthStatus: vi.fn(async () => ({ provider: 'openai', issuer: 'openai', connected: false })),
}));
vi.mock('@/lib/backend-health', () => ({ ensureLocalBackendReady: vi.fn(async () => {}) }));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isLocalMode: () => false,
}));
vi.mock('@/lib/platform-readiness', () => ({
  ensurePlatformReadiness: vi.fn(async () => ({ database: false })),
}));

import useProviderStore from '../useProviderStore';
import { getInitialDefaultModelConfig, getInitialProviders } from '../config/providerTypes';

const serverProviders = () => ({
  providers: getInitialProviders().map((p) =>
    p.id === 'minimax' ? { ...p, isEnabled: true, apiUrl: 'https://api.minimaxi.com/v1' } : p,
  ),
  defaultModelConfig: getInitialDefaultModelConfig(),
  customModelInfo: {},
});

describe('useProviderStore hydration guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    manager.status = 'ready';
    manager.stored = undefined;
    manager.get.mockImplementation(() => manager.stored);
  });

  it('does not push the seed providers to the server before the config is loaded', async () => {
    // 后端不可达 → 配置没加载回来，本地只有种子默认值
    manager.status = 'offline';
    manager.stored = undefined;

    await useProviderStore.getState().retryInit();
    manager.set.mockClear();

    useProviderStore.getState().updateProvider('openai', { isEnabled: true });

    expect(manager.set).not.toHaveBeenCalled();
  });

  it('allows the first provider write on a fresh instance without a server-side config', async () => {
    // 服务端没有 providers 配置：种子默认值就是真实状态，首个配置必须能落库
    manager.status = 'ready';
    manager.stored = undefined;

    await useProviderStore.getState().retryInit();
    manager.set.mockClear();

    useProviderStore.getState().updateProvider('openai', { isEnabled: true });

    expect(manager.set).toHaveBeenCalledTimes(1);
  });

  it('pushes provider edits once the server config has been loaded', async () => {
    manager.stored = serverProviders();

    await useProviderStore.getState().retryInit();
    manager.set.mockClear();

    useProviderStore.getState().updateProvider('openai', { isEnabled: true });

    expect(manager.set).toHaveBeenCalledTimes(1);
    const [key, value] = manager.set.mock.calls[0] as [string, { providers: Array<{ id: string; isEnabled: boolean }> }];
    expect(key).toBe('providers');
    // 推送的必须是服务端那份（minimax 仍然启用），不是种子默认值
    expect(value.providers.find((p) => p.id === 'minimax')?.isEnabled).toBe(true);
  });
});
