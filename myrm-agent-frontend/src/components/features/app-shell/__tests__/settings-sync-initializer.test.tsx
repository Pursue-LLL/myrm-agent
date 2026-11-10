/**
 * Start-up of the configuration sync.
 *
 * Real scenario: the app opens, saved chat preferences are applied at once, and once the database is ready the sync
 * manager starts, the critical config loads and the remaining stores follow when the browser is idle. When a step
 * fails the stores still start from their defaults. When another device changed the same setting, the user decides
 * which side wins, one question at a time, and the sync waits for that decision.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ConfigConflictResolution, ConfigConflictResolver } from '@/services/config/conflictResolution';
import { deferred } from '@/test-utils/deferred';
import { expectDefined, expectNonNull } from '@/test-utils/expectDefined';

import SettingsSyncInitializer from '../settings-sync-initializer';
import {
  calls,
  chatState,
  enforceSecurityPresetYoloMutex,
  hydrateChatPreferencesFromStorage,
  manager,
  resetSettingsSyncKit,
  storeInits,
  stubIdleCallbacks,
  whenDatabaseReady,
} from './settingsSyncKit';

const translate = vi.hoisted(
  () =>
    (key: string, values?: Record<string, string>): string =>
      values ? `${key}(${Object.values(values).join(',')})` : key,
);

vi.mock('next-intl', () => ({ useTranslations: () => translate }));
vi.mock('@/lib/diff/TextDiffViewer', () => ({
  TextDiffViewer: ({ oldValue, newValue }: { oldValue: string; newValue: string }) => (
    <div data-testid="diff">{`${oldValue}=>${newValue}`}</div>
  ),
}));
vi.mock('@/lib/platform-readiness', async () => ({
  whenDatabaseReady: (await import('./settingsSyncKit')).whenDatabaseReady,
}));
vi.mock('@/services/config', async () => {
  const kit = await import('./settingsSyncKit');
  return { getConfigSyncManager: () => kit.manager };
});
vi.mock('@/store/chat/securityPreset', async () => ({
  enforceSecurityPresetYoloMutex: (await import('./settingsSyncKit')).enforceSecurityPresetYoloMutex,
}));
vi.mock('@/store/useChatStore', async () => {
  const kit = await import('./settingsSyncKit');
  return {
    default: { getState: () => kit.chatState },
    hydrateChatPreferencesFromStorage: kit.hydrateChatPreferencesFromStorage,
  };
});
vi.mock('@/store/useConfigStore', async () => {
  const kit = await import('./settingsSyncKit');
  return { default: kit.storeDouble({ initConfig: kit.storeInits.initConfig }) };
});
vi.mock('@/store/useProviderStore', async () => {
  const kit = await import('./settingsSyncKit');
  return { default: kit.storeDouble({ initProviders: kit.storeInits.initProviders }) };
});
vi.mock('@/store/useCommandStore', async () => {
  const kit = await import('./settingsSyncKit');
  return { useCommandStore: kit.storeDouble({ initCommands: kit.storeInits.initCommands }) };
});
vi.mock('@/store/useRetrievalStore', async () => {
  const kit = await import('./settingsSyncKit');
  return { useRetrievalStore: kit.storeDouble({ initRetrieval: kit.storeInits.initRetrieval }) };
});

beforeEach(() => {
  resetSettingsSyncKit();
  vi.spyOn(console, 'log').mockImplementation(() => undefined);
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const warnings = () => vi.mocked(console.warn);

describe('SettingsSyncInitializer: start-up', () => {
  it('applies the saved preferences, starts the sync, loads the critical config and leaves the rest for idle time', async () => {
    const { goIdle } = stubIdleCallbacks();

    render(<SettingsSyncInitializer />);
    await waitFor(() => expect(calls).toContain('initConfig'));

    expect(calls).toEqual([
      'hydrate',
      'database-ready',
      'resolver',
      'initialize',
      'normalize',
      'mutex:hitl',
      'subscribe',
      'initConfig',
    ]);

    goIdle();
    await waitFor(() => expect(calls).toHaveLength(11));
    expect(calls.slice(8).sort()).toEqual(['initCommands', 'initProviders', 'initRetrieval']);
  });

  it('applies the saved preferences without waiting for the database, and starts only once', async () => {
    stubIdleCallbacks();
    const ready = deferred<boolean>();
    whenDatabaseReady.mockImplementation(() => ready.promise);

    const view = render(<SettingsSyncInitializer />);
    expect(hydrateChatPreferencesFromStorage).toHaveBeenCalledOnce();
    expect(manager.initialize).not.toHaveBeenCalled();

    await act(async () => ready.resolve(true));
    await waitFor(() => expect(storeInits.initConfig).toHaveBeenCalledOnce());
    view.rerender(<SettingsSyncInitializer />);
    await act(async () => undefined);

    expect(hydrateChatPreferencesFromStorage).toHaveBeenCalledOnce();
    expect(manager.initialize).toHaveBeenCalledOnce();
    expect(storeInits.initConfig).toHaveBeenCalledOnce();
  });

  it('leaves the sync and every store alone while the database is not ready, and says so', async () => {
    whenDatabaseReady.mockImplementation(async () => false);

    render(<SettingsSyncInitializer />);
    await waitFor(() => expect(whenDatabaseReady).toHaveBeenCalled());
    await act(async () => undefined);

    expect(calls).toEqual(['hydrate']);
    expect(manager.setConflictResolver).not.toHaveBeenCalled();
    expect(warnings()).toHaveBeenCalledWith(expect.stringContaining('Backend not available'));
  });

  it('applies the preset rule again whenever the security config changes, with the preset in force then', async () => {
    stubIdleCallbacks();
    render(<SettingsSyncInitializer />);
    await waitFor(() => expect(calls).toContain('initConfig'));

    const [key, onChange] = manager.subscribe.mock.calls[0] ?? [];
    expect(key).toBe('securityConfig');
    expectDefined(onChange, 'security config listener');
    chatState.securityPreset = 'explore';
    onChange();

    expect(enforceSecurityPresetYoloMutex).toHaveBeenCalledTimes(2);
    expect(enforceSecurityPresetYoloMutex).toHaveBeenLastCalledWith('explore');
  });

  it('starts the other stores together when the browser goes idle, and one failing store does not stop the rest', async () => {
    const { goIdle } = stubIdleCallbacks();
    storeInits.initCommands.mockRejectedValue(new Error('commands down'));
    render(<SettingsSyncInitializer />);
    await waitFor(() => expect(calls).toContain('initConfig'));
    expect(storeInits.initProviders).not.toHaveBeenCalled();

    goIdle();

    await waitFor(() =>
      expect(warnings()).toHaveBeenCalledWith(
        '[SettingsSync] Deferred store initialization failed:',
        expect.any(Error),
      ),
    );
    expect(storeInits.initProviders).toHaveBeenCalledOnce();
    expect(storeInits.initRetrieval).toHaveBeenCalledOnce();
  });
});

describe('SettingsSyncInitializer: a step fails', () => {
  it.each([
    ['the manager cannot initialize', () => manager.initialize.mockRejectedValue(new Error('boom')), 1],
    ['the startup normalization fails', () => manager.runStartupNormalization.mockRejectedValue(new Error('boom')), 1],
    ['the critical config fails to load once', () => storeInits.initConfig.mockRejectedValueOnce(new Error('boom')), 2],
  ])('still starts every store directly when %s', async (_name, breakIt, initConfigCalls) => {
    const { goIdle } = stubIdleCallbacks();
    breakIt();

    render(<SettingsSyncInitializer />);
    await waitFor(() => expect(storeInits.initRetrieval).toHaveBeenCalled());

    expect(warnings()).toHaveBeenCalledWith('[SettingsSync] Initialization failed:', expect.any(Error));
    expect(storeInits.initConfig).toHaveBeenCalledTimes(initConfigCalls);
    expect(storeInits.initProviders).toHaveBeenCalledOnce();
    expect(storeInits.initCommands).toHaveBeenCalledOnce();

    goIdle();
    await act(async () => undefined);
    expect(storeInits.initProviders).toHaveBeenCalledOnce();
  });

  it('lets nothing escape when even the direct start fails', async () => {
    manager.initialize.mockRejectedValue(new Error('boom'));
    storeInits.initConfig.mockRejectedValue(new Error('still down'));

    render(<SettingsSyncInitializer />);
    await waitFor(() => expect(storeInits.initConfig).toHaveBeenCalled());
    await act(async () => undefined);

    expect(storeInits.initProviders).not.toHaveBeenCalled();
  });
});

describe('SettingsSyncInitializer: a setting changed on another device', () => {
  const conflict = (overrides: Partial<ConfigConflictResolution> = {}): ConfigConflictResolution => ({
    configKey: 'providers',
    localVersion: 'v1',
    serverVersion: 'v2',
    deviceId: 'laptop',
    localValue: { theme: 'dark' },
    serverValue: { theme: 'light' },
    ...overrides,
  });

  async function installedResolver(): Promise<ConfigConflictResolver> {
    stubIdleCallbacks();
    render(<SettingsSyncInitializer />);
    await waitFor(() => expect(manager.setConflictResolver).toHaveBeenCalled());
    const resolver = manager.setConflictResolver.mock.calls[0]?.[0] ?? null;
    expectNonNull(resolver, 'conflict resolver');
    return resolver;
  }

  /** Asks the question and reports the answer once the user gave it. */
  function ask(resolver: ConfigConflictResolver, resolution: ConfigConflictResolution) {
    const answer: { keepLocal?: boolean } = {};
    act(() => {
      void Promise.resolve(resolver(resolution)).then((keepLocal) => {
        answer.keepLocal = keepLocal;
      });
    });
    return answer;
  }

  const answerWith = async (choice: 'keepLocal' | 'useServer') => {
    fireEvent.click(screen.getByRole('button', { name: choice }));
    await act(async () => undefined);
  };

  it('shows both versions, the other device and the setting by its translated name, then keeps the local one', async () => {
    const resolver = await installedResolver();
    expect(screen.queryByRole('alertdialog')).toBeNull();

    const answer = ask(resolver, conflict());

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('description(keys.providers)');
    expect(dialog).toHaveTextContent('v1');
    expect(dialog).toHaveTextContent('v2');
    expect(dialog).toHaveTextContent('laptop');
    expect(screen.getByTestId('diff')).toHaveTextContent('{ "theme": "light" }=>{ "theme": "dark" }');
    expect(answer.keepLocal).toBeUndefined();

    await answerWith('keepLocal');
    expect(answer.keepLocal).toBe(true);
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('adopts the server version when the user chooses it', async () => {
    const resolver = await installedResolver();
    const answer = ask(resolver, conflict());
    await screen.findByRole('alertdialog');

    await answerWith('useServer');

    expect(answer.keepLocal).toBe(false);
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('keeps asking when the user presses Escape, because the sync waits for the answer', async () => {
    const resolver = await installedResolver();
    const answer = ask(resolver, conflict());
    await screen.findByRole('alertdialog');

    fireEvent.keyDown(document, { key: 'Escape' });
    await act(async () => undefined);

    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(answer.keepLocal).toBeUndefined();
    await answerWith('keepLocal');
    expect(answer.keepLocal).toBe(true);
  });

  it('asks about a second setting only after the first was answered, and answers each question itself', async () => {
    const resolver = await installedResolver();
    const first = ask(resolver, conflict({ configKey: 'providers' }));
    const second = ask(resolver, conflict({ configKey: 'voice' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('description(keys.providers)');
    expect(dialog).not.toHaveTextContent('keys.voice');

    await answerWith('useServer');
    expect(first.keepLocal).toBe(false);
    expect(second.keepLocal).toBeUndefined();
    await waitFor(() => expect(screen.getByRole('alertdialog')).toHaveTextContent('description(keys.voice)'));

    await answerWith('keepLocal');
    expect(second.keepLocal).toBe(true);
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });
});
