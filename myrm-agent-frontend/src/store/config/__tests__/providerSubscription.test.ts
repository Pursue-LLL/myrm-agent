import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ModelsDevModel } from '@/services/models-dev';

const { mockSyncSet, mockGetModelsForProvider } = vi.hoisted(() => ({
  mockSyncSet: vi.fn(),
  mockGetModelsForProvider: vi.fn(),
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({ set: mockSyncSet, get: vi.fn(), subscribe: vi.fn(), initialize: vi.fn() }),
}));

vi.mock('@/services/models-dev', () => ({
  getModelsForProvider: mockGetModelsForProvider,
}));

import useProviderStore from '@/store/useProviderStore';
import { getInitialDefaultModelConfig, getInitialProviders, type ProviderConfig } from '../providerTypes';
import { connectProviderSubscription, disconnectProviderSubscription } from '../providerSubscription';

const CATALOG: ModelsDevModel[] = [
  { id: 'grok-4.7', name: 'Grok 4.7', tool_call: true, release_date: '2026-09-21', modalities: { output: ['text'] } },
  { id: 'grok-4.6', name: 'Grok 4.6', tool_call: true, release_date: '2026-08-12', modalities: { output: ['text'] } },
  { id: 'grok-imagine-video', name: 'Imagine', tool_call: false, release_date: '2026-10-01' },
];

function seed(
  xaiOverrides: Partial<ProviderConfig> = {},
  baseModelPrimary: { providerId: string; model: string } | null = null,
) {
  const defaultModelConfig = getInitialDefaultModelConfig();
  defaultModelConfig.baseModel = { ...defaultModelConfig.baseModel, primary: baseModelPrimary };
  useProviderStore.setState({
    providers: getInitialProviders().map((p) => (p.id === 'xai' ? { ...p, ...xaiOverrides } : p)),
    defaultModelConfig,
    customModelInfo: {},
    isInitialized: true,
  });
}

function xai(): ProviderConfig {
  const provider = useProviderStore.getState().providers.find((p) => p.id === 'xai');
  if (!provider) {
    throw new Error('xai provider missing from the seeded store');
  }
  return provider;
}

const basePrimary = () => useProviderStore.getState().defaultModelConfig.baseModel.primary;

describe('connectProviderSubscription', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetModelsForProvider.mockResolvedValue({ provider: null, models: CATALOG, source: 'models.dev' });
    seed();
  });

  it('marks the provider connected synchronously, before the catalog answers', () => {
    mockGetModelsForProvider.mockReturnValue(new Promise(() => {}));

    void connectProviderSubscription('xai');

    expect(xai().oauthConnected).toBe(true);
    expect(xai().isEnabled).toBe(false);
  });

  it('enables the provider with the newest catalog chat model and binds the empty base slot to it', async () => {
    await connectProviderSubscription('xai');

    expect(mockGetModelsForProvider).toHaveBeenCalledWith('xai');
    expect(xai()).toMatchObject({
      oauthConnected: true,
      isEnabled: true,
      availableModels: ['grok-4.7'],
      enabledModels: ['grok-4.7'],
    });
    expect(basePrimary()).toEqual({ providerId: 'xai', model: 'grok-4.7' });
  });

  it('persists the change through the config sync manager', async () => {
    await connectProviderSubscription('xai');

    const lastValue = mockSyncSet.mock.calls.at(-1)?.[1] as { providers: ProviderConfig[] };
    expect(mockSyncSet).toHaveBeenLastCalledWith('providers', expect.anything());
    expect(lastValue.providers.find((p) => p.id === 'xai')).toMatchObject({ oauthConnected: true, isEnabled: true });
  });

  it('keeps the models the provider already had and binds the empty base slot to the first of them', async () => {
    seed({ availableModels: ['grok-3', 'grok-2'], enabledModels: ['grok-3'] });

    await connectProviderSubscription('xai');

    expect(xai()).toMatchObject({
      oauthConnected: true,
      isEnabled: true,
      availableModels: ['grok-3', 'grok-2'],
      enabledModels: ['grok-3'],
    });
    expect(basePrimary()).toEqual({ providerId: 'xai', model: 'grok-3' });
  });

  it('leaves an occupied base slot alone', async () => {
    seed({}, { providerId: 'openai', model: 'gpt-4o' });

    await connectProviderSubscription('xai');

    expect(basePrimary()).toEqual({ providerId: 'openai', model: 'gpt-4o' });
    expect(xai().enabledModels).toEqual(['grok-4.7']);
  });

  it.each([
    ['the catalog request fails', () => mockGetModelsForProvider.mockRejectedValue(new Error('offline'))],
    [
      'the catalog has no agent-capable model',
      () => mockGetModelsForProvider.mockResolvedValue({ provider: null, models: [CATALOG[2]], source: 'models.dev' }),
    ],
  ])('only marks the provider connected when %s', async (_label, arrange) => {
    arrange();
    vi.spyOn(console, 'warn').mockImplementation(() => {});

    await connectProviderSubscription('xai');

    expect(xai()).toMatchObject({ oauthConnected: true, isEnabled: false, enabledModels: [], availableModels: [] });
    expect(basePrimary()).toBeNull();
  });

  it('enables a provider that already has chosen models even without the catalog', async () => {
    mockGetModelsForProvider.mockRejectedValue(new Error('offline'));
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    seed({ availableModels: ['grok-3'], enabledModels: ['grok-3'] });

    await connectProviderSubscription('xai');

    expect(xai()).toMatchObject({ oauthConnected: true, isEnabled: true, enabledModels: ['grok-3'] });
    expect(basePrimary()).toEqual({ providerId: 'xai', model: 'grok-3' });
  });

  it('decides on the state after the catalog answered, not before', async () => {
    mockGetModelsForProvider.mockImplementation(async () => {
      useProviderStore.getState().updateProvider('xai', { availableModels: ['grok-3'], enabledModels: ['grok-3'] });
      return { provider: null, models: CATALOG, source: 'models.dev' };
    });

    await connectProviderSubscription('xai');

    expect(xai().enabledModels).toEqual(['grok-3']);
    expect(xai().availableModels).toEqual(['grok-3']);
  });

  it('ignores an unknown provider id', async () => {
    const before = useProviderStore.getState().providers;

    await expect(connectProviderSubscription('no-such-provider')).resolves.toBeUndefined();

    expect(useProviderStore.getState().providers.map((p) => p.isEnabled)).toEqual(before.map((p) => p.isEnabled));
    expect(useProviderStore.getState().providers.some((p) => p.id === 'no-such-provider')).toBe(false);
  });
});

describe('disconnectProviderSubscription', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('disables a provider that has no other way to authenticate and frees its model slots', () => {
    seed(
      { oauthConnected: true, isEnabled: true, enabledModels: ['grok-4.7'] },
      { providerId: 'xai', model: 'grok-4.7' },
    );

    disconnectProviderSubscription('xai');

    expect(xai()).toMatchObject({ oauthConnected: false, isEnabled: false });
    expect(basePrimary()).toBeNull();
  });

  it('keeps a provider enabled when an active API key can still authenticate it', () => {
    seed(
      {
        oauthConnected: true,
        isEnabled: true,
        enabledModels: ['grok-4.7'],
        apiKeys: [{ id: 'k1', key: 'xai-key', remark: '', isActive: true }],
      },
      { providerId: 'xai', model: 'grok-4.7' },
    );

    disconnectProviderSubscription('xai');

    expect(xai()).toMatchObject({ oauthConnected: false, isEnabled: true });
    expect(basePrimary()).toEqual({ providerId: 'xai', model: 'grok-4.7' });
  });

  it('does not enable anything for a provider the user had disabled', () => {
    seed({ oauthConnected: true, isEnabled: false });

    disconnectProviderSubscription('xai');

    expect(xai()).toMatchObject({ oauthConnected: false, isEnabled: false });
  });

  it('persists the change through the config sync manager', () => {
    seed({ oauthConnected: true, isEnabled: true });

    disconnectProviderSubscription('xai');

    const lastValue = mockSyncSet.mock.calls.at(-1)?.[1] as { providers: ProviderConfig[] };
    expect(lastValue.providers.find((p) => p.id === 'xai')?.oauthConnected).toBe(false);
  });

  it('ignores an unknown provider id', () => {
    seed({ oauthConnected: true, isEnabled: true });

    disconnectProviderSubscription('no-such-provider');

    expect(mockSyncSet).not.toHaveBeenCalled();
    expect(xai()).toMatchObject({ oauthConnected: true, isEnabled: true });
  });
});
