import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockSyncSet, mockStoredProviders } = vi.hoisted(() => ({
  mockSyncSet: vi.fn(),
  mockStoredProviders: { current: undefined as unknown },
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    set: mockSyncSet,
    get: vi.fn((key: string) => (key === 'providers' ? mockStoredProviders.current : undefined)),
    subscribe: vi.fn(() => () => {}),
    initialize: vi.fn(async () => {}),
  }),
}));

vi.mock('@/lib/backend-health', () => ({ ensureLocalBackendReady: vi.fn(async () => {}) }));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isLocalMode: () => false,
}));
vi.mock('@/lib/platform-readiness', () => ({
  ensurePlatformReadiness: vi.fn(async () => ({ database: false })),
}));
vi.mock('@/services/provider-oauth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/provider-oauth')>()),
  fetchProviderOAuthStatus: vi.fn(async () => ({ provider: 'xai', issuer: 'xai', connected: false })),
}));

import useProviderStore from '@/store/useProviderStore';
import { getInitialDefaultModelConfig, getInitialProviders, type ProviderConfig } from '../providerTypes';
import { enableProviderWithModel } from '../enableProviderWithModel';

function seed(
  ollamaOverrides: Partial<ProviderConfig> = {},
  baseModelPrimary: { providerId: string; model: string } | null = null,
) {
  const defaultModelConfig = getInitialDefaultModelConfig();
  defaultModelConfig.baseModel = { ...defaultModelConfig.baseModel, primary: baseModelPrimary };
  useProviderStore.setState({
    providers: getInitialProviders().map((p) => (p.id === 'ollama' ? { ...p, ...ollamaOverrides } : p)),
    defaultModelConfig,
    customModelInfo: {},
    isInitialized: true,
  });
}

// Provider changes are only written back once the server's configuration has loaded, so load it once first.
beforeEach(async () => {
  vi.clearAllMocks();
  mockStoredProviders.current = {
    providers: getInitialProviders(),
    defaultModelConfig: getInitialDefaultModelConfig(),
    customModelInfo: {},
  };
  await useProviderStore.getState().initProviders();
  seed();
});

function ollama(): ProviderConfig {
  const provider = useProviderStore.getState().providers.find((p) => p.id === 'ollama');
  if (!provider) {
    throw new Error('ollama provider missing from the seeded store');
  }
  return provider;
}

const basePrimary = () => useProviderStore.getState().defaultModelConfig.baseModel.primary;

describe('enableProviderWithModel', () => {
  it('enables the provider with the model and binds the empty base slot to it', () => {
    enableProviderWithModel('ollama', 'qwen3:8b');

    expect(ollama()).toMatchObject({
      isEnabled: true,
      availableModels: ['qwen3:8b'],
      enabledModels: ['qwen3:8b'],
    });
    expect(basePrimary()).toEqual({ providerId: 'ollama', model: 'qwen3:8b' });
  });

  it('keeps the models the provider already had and adds the new one after them', () => {
    seed({ availableModels: ['llama3.2', 'phi4'], enabledModels: ['llama3.2'] });

    enableProviderWithModel('ollama', 'qwen3:8b');

    expect(ollama()).toMatchObject({
      isEnabled: true,
      availableModels: ['llama3.2', 'phi4', 'qwen3:8b'],
      enabledModels: ['llama3.2', 'qwen3:8b'],
    });
  });

  it('lists a model that was available but not enabled only once', () => {
    seed({ availableModels: ['qwen3:8b'], enabledModels: [] });

    enableProviderWithModel('ollama', 'qwen3:8b');

    expect(ollama()).toMatchObject({ availableModels: ['qwen3:8b'], enabledModels: ['qwen3:8b'] });
  });

  it('does not touch the model lists when the model is already enabled', () => {
    seed({ availableModels: ['llama3.2', 'qwen3:8b'], enabledModels: ['qwen3:8b', 'llama3.2'] });

    enableProviderWithModel('ollama', 'qwen3:8b');

    expect(ollama()).toMatchObject({
      isEnabled: true,
      availableModels: ['llama3.2', 'qwen3:8b'],
      enabledModels: ['qwen3:8b', 'llama3.2'],
    });
  });

  it('leaves an occupied base slot alone', () => {
    seed({}, { providerId: 'openai', model: 'gpt-4o' });

    enableProviderWithModel('ollama', 'qwen3:8b');

    expect(basePrimary()).toEqual({ providerId: 'openai', model: 'gpt-4o' });
    expect(ollama().enabledModels).toEqual(['qwen3:8b']);
  });

  it('applies the provider fields the connect decided', () => {
    enableProviderWithModel('ollama', 'qwen3:8b', { apiUrl: 'http://host.docker.internal:11434' });

    expect(ollama().apiUrl).toBe('http://host.docker.internal:11434');
  });

  it('keeps the provider address when none is given', () => {
    seed({ apiUrl: 'http://192.168.1.50:11434' });

    enableProviderWithModel('ollama', 'qwen3:8b');

    expect(ollama().apiUrl).toBe('http://192.168.1.50:11434');
  });

  it('persists the change through the config sync manager', () => {
    enableProviderWithModel('ollama', 'qwen3:8b');

    const lastValue = mockSyncSet.mock.calls.at(-1)?.[1] as { providers: ProviderConfig[] };
    expect(mockSyncSet).toHaveBeenLastCalledWith('providers', expect.anything());
    expect(lastValue.providers.find((p) => p.id === 'ollama')).toMatchObject({
      isEnabled: true,
      enabledModels: ['qwen3:8b'],
    });
  });

  it('ignores an unknown provider id', () => {
    const before = useProviderStore.getState().providers;
    mockSyncSet.mockClear();

    enableProviderWithModel('no-such-provider', 'qwen3:8b');

    expect(useProviderStore.getState().providers).toBe(before);
    expect(basePrimary()).toBeNull();
    expect(mockSyncSet).not.toHaveBeenCalled();
  });
});
