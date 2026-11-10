/**
 * Doubles for the settings-sync initializer tests: the sync manager, the stores it starts, the chat store pieces it
 * reads and the browser's idle callbacks. `calls` records the order in which the start-up steps run.
 */
import { vi } from 'vitest';

import type { ConfigConflictResolver } from '@/services/config/conflictResolution';

export const calls: string[] = [];

export const manager = {
  setConflictResolver: vi.fn<(resolver: ConfigConflictResolver | null) => void>(),
  initialize: vi.fn<() => Promise<void>>(),
  runStartupNormalization: vi.fn<() => Promise<void>>(),
  subscribe: vi.fn<(key: string, listener: () => void) => () => void>(),
};

export const storeInits = {
  initConfig: vi.fn<() => Promise<void>>(),
  initProviders: vi.fn<() => Promise<void>>(),
  initCommands: vi.fn<() => Promise<void>>(),
  initRetrieval: vi.fn<() => Promise<void>>(),
};

export const whenDatabaseReady = vi.fn<() => Promise<boolean>>();
export const enforceSecurityPresetYoloMutex = vi.fn<(preset: string) => void>();
export const hydrateChatPreferencesFromStorage = vi.fn<() => void>();
export const chatState = { securityPreset: 'hitl' };

/** A store that answers both as a state hook and through `getState()`, however the code under test reads it. */
export function storeDouble<State extends object>(state: State) {
  return Object.assign(() => state, { getState: () => state });
}

/** Puts every double back to a start-up that succeeds. */
export function resetSettingsSyncKit(): void {
  vi.resetAllMocks();
  calls.length = 0;
  chatState.securityPreset = 'hitl';
  hydrateChatPreferencesFromStorage.mockImplementation(() => {
    calls.push('hydrate');
  });
  whenDatabaseReady.mockImplementation(async () => {
    calls.push('database-ready');
    return true;
  });
  manager.setConflictResolver.mockImplementation(() => {
    calls.push('resolver');
  });
  manager.initialize.mockImplementation(async () => {
    calls.push('initialize');
  });
  manager.runStartupNormalization.mockImplementation(async () => {
    calls.push('normalize');
  });
  manager.subscribe.mockImplementation(() => {
    calls.push('subscribe');
    return () => undefined;
  });
  enforceSecurityPresetYoloMutex.mockImplementation((preset) => {
    calls.push(`mutex:${preset}`);
  });
  for (const [name, init] of Object.entries(storeInits)) {
    init.mockImplementation(async () => {
      calls.push(name);
    });
  }
}

/** Idle callbacks that run only when the test says the browser went idle. */
export function stubIdleCallbacks(): { goIdle: () => void } {
  const waiting: Array<() => void> = [];
  vi.stubGlobal('requestIdleCallback', (callback: () => void) => waiting.push(callback));
  vi.stubGlobal('cancelIdleCallback', vi.fn());
  return { goIdle: () => waiting.splice(0).forEach((callback) => callback()) };
}
