/**
 * Regression cover for the startup normalization that used to overwrite a sealed config row whose key is gone.
 *
 * The server reports such a row as empty and flagged `unreadable`. The startup normalization treated the empty
 * value as "nothing configured", filled in the built-in providers and wrote them back, which replaced the user's
 * stored credentials with defaults. An unreadable row must be left alone until the user writes it on purpose.
 */

import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { ConfigSyncManager, resetConfigSyncManager } from '@/services/config/ConfigSyncManager';
import { normalizeProviders } from '@/services/config/configNormalizer';
import { DEFAULT_PERSONAL_SETTINGS } from '@/services/config/types';

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: vi.fn(() => true),
  getApiBaseUrl: vi.fn(() => 'http://localhost:8080/api/v1'),
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(() => Promise.resolve(true)),
  markLocalBackendUnreachable: vi.fn(),
}));

vi.mock('@/lib/platform-readiness', () => ({
  ensurePlatformReadiness: vi.fn(() => Promise.resolve({ state: 'ready', database: true })),
  whenDatabaseReady: vi.fn(() => Promise.resolve(true)),
}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
  };
})();
Object.defineProperty(global, 'localStorage', { value: localStorageMock });

interface ServerRow {
  key: string;
  value: unknown;
  version: string;
  updatedAt: string;
  deviceId: string;
  encrypted: boolean;
  unreadable?: boolean;
}

const row = (key: string, value: unknown, extra: Partial<ServerRow> = {}): ServerRow => ({
  key,
  value,
  version: '1793_0',
  updatedAt: '2026-10-27T22:31:09.000Z',
  deviceId: 'tauri-local',
  encrypted: false,
  ...extra,
});

const UNREADABLE_PROVIDERS = row('providers', {}, { encrypted: true, unreadable: true });
const READABLE_SETTINGS = row('personalSettings', { ...DEFAULT_PERSONAL_SETTINGS });

const respond = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

function serveRows(rows: ServerRow[]): void {
  mockFetch.mockImplementation((url: string, init?: RequestInit) => {
    if (init?.method === 'POST' && url.endsWith('/config/sync')) {
      const { changes } = JSON.parse(String(init.body)) as { changes: { key: string }[] };
      return respond({
        success: true,
        conflicts: [],
        newVersions: Object.fromEntries(changes.map((change) => [change.key, '1794_0'])),
      });
    }
    return respond({ configs: Object.fromEntries(rows.map((r) => [r.key, r])) });
  });
}

const writes = (): { key: string }[] => {
  const calls = mockFetch.mock.calls as [string, RequestInit?][];
  return calls.flatMap(([, init]) =>
    init?.method === 'POST' ? (JSON.parse(String(init.body)) as { changes: { key: string }[] }).changes : [],
  );
};

describe('ConfigSyncManager with a sealed row whose key is gone', () => {
  let manager: ConfigSyncManager;

  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
    resetConfigSyncManager();
    manager = new ConfigSyncManager();
  });

  afterEach(() => {
    resetConfigSyncManager();
  });

  it('does not write defaults over the unreadable row during startup normalization', async () => {
    serveRows([UNREADABLE_PROVIDERS, READABLE_SETTINGS]);

    await manager.initialize();
    await manager.runStartupNormalization();
    await manager.forceSync();

    expect(writes()).toEqual([]);
  });

  it('reports which keys cannot be read so the user can be told', async () => {
    serveRows([UNREADABLE_PROVIDERS, READABLE_SETTINGS]);

    await manager.initialize();

    expect(manager.getUnreadableKeys()).toEqual(['providers']);
  });

  it('still normalizes a readable row that is missing the built-in providers', async () => {
    serveRows([row('providers', { providers: [] }, { encrypted: true }), READABLE_SETTINGS]);

    await manager.initialize();
    await manager.runStartupNormalization();
    await manager.forceSync();

    expect(writes().map((change) => change.key)).toEqual(['providers']);
    expect(manager.getUnreadableKeys()).toEqual([]);
  });

  it('writes when the user saves the key on purpose, and the key stops being reported unreadable', async () => {
    serveRows([UNREADABLE_PROVIDERS, READABLE_SETTINGS]);
    await manager.initialize();
    await manager.runStartupNormalization();

    manager.set('providers', normalizeProviders(null));
    await manager.forceSync();

    expect(writes().map((change) => change.key)).toEqual(['providers']);
    expect(manager.getUnreadableKeys()).toEqual([]);
  });
});
