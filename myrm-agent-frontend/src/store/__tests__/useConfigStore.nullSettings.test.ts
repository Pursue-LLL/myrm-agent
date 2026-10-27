/**
 * Regression cover: a field the server serializes as null must not reach the store.
 *
 * The server writes every unset personal setting as null. Spread into the store, a null replaced the seed
 * `[]` of the privacy pattern lists and the privacy rule tester crashed reading `.length` on it.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

type Listener = (key: string, value: unknown) => void;

const { manager, listeners } = vi.hoisted(() => {
  const listeners = new Map<string, (key: string, value: unknown) => void>();
  return {
    listeners,
    manager: {
      isInitialized: true,
      stored: {} as Record<string, unknown>,
      initialize: vi.fn(async () => {}),
      get: vi.fn((key: string) => manager.stored[key] ?? null),
      set: vi.fn(),
      subscribe: vi.fn((key: string, listener: (key: string, value: unknown) => void) => {
        listeners.set(key, listener);
        return () => {};
      }),
    },
  };
});

vi.mock('@/services/config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/config')>()),
  getConfigSyncManager: () => manager,
}));

import useConfigStore from '../useConfigStore';

const SERVER_VALUE = { enableMemory: false, privacyCustomPatternsS2: null, privacyCustomKeywordsS3: null };

describe('useConfigStore with null personal settings from the server', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listeners.clear();
    manager.stored = { personalSettings: SERVER_VALUE };
    useConfigStore.setState({ _configStoreReady: false, privacyCustomPatternsS2: [], privacyCustomKeywordsS3: [] });
  });

  it('keeps the seed lists when the loaded settings carry nulls', async () => {
    await useConfigStore.getState().initConfig();

    const state = useConfigStore.getState();
    expect(state.enableMemory).toBe(false);
    expect(state.privacyCustomPatternsS2).toEqual([]);
    expect(state.privacyCustomKeywordsS3).toEqual([]);
  });

  it('keeps the lists when a later sync notification carries nulls', async () => {
    await useConfigStore.getState().initConfig();
    useConfigStore.setState({ privacyCustomPatternsS2: ['secret-\\d+'] });

    const notify = listeners.get('personalSettings') as Listener;
    notify('personalSettings', { ...SERVER_VALUE, enableMemory: true });

    const state = useConfigStore.getState();
    expect(state.enableMemory).toBe(true);
    expect(state.privacyCustomPatternsS2).toEqual(['secret-\\d+']);
    expect(state.personalSettings).not.toHaveProperty('privacyCustomPatternsS2');
  });

  it('does not write a null back to the server when another setting changes', async () => {
    await useConfigStore.getState().initConfig();
    manager.set.mockClear();

    useConfigStore.getState().setEnableCostEstimation(false);

    const written = manager.set.mock.calls.at(-1)?.[1] as Record<string, unknown>;
    expect(written.enableCostEstimation).toBe(false);
    expect(Object.values(written)).not.toContain(null);
  });
});
