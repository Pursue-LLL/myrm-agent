/**
 * What a write made on this device leaves in the cached copies: a plain record authored by this device, one version
 * past the cached record while queued changes are replayed, and the confirmed version as both the copy and an
 * independent merge base once a sync succeeded.
 */

import { cloneDeep } from 'lodash-es';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { applyReplayedChanges, buildLocalRecord, recordSyncedChanges } from '../localWrites';
import type { ConfigChange, ConfigKey, ConfigRecord } from '../types';

const DEVICE = 'this-device';
const NOW = Date.parse('2026-02-03T04:05:06.000Z');

const record = (key: ConfigKey, value: unknown, version: string, extra: Partial<ConfigRecord> = {}): ConfigRecord => ({
  key,
  value: value as never,
  meta: { version, updatedAt: '2026-01-01T00:00:00.000Z', deviceId: 'other-device' },
  ...extra,
});

const change = (key: ConfigKey, value: unknown): ConfigChange => ({
  key,
  value: value as never,
  expectedVersion: '1000_0',
  timestamp: 1,
});

/** Caches that hold `cached` as the copy and, separately, as the merge base. */
function cachesHolding(cached: ConfigRecord[]) {
  return {
    cache: new Map(cached.map((entry) => [entry.key, cloneDeep(entry)])),
    baseCache: new Map(cached.map((entry) => [entry.key, cloneDeep(entry)])),
  };
}

describe('local writes', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('authors a built record with this device and the given version, and no unreadable mark', () => {
    const built = buildLocalRecord('chatSettings', { n: 1 } as never, '1000_3', DEVICE);

    expect(built).toEqual({
      key: 'chatSettings',
      value: { n: 1 },
      meta: { version: '1000_3', updatedAt: '2026-02-03T04:05:06.000Z', deviceId: DEVICE },
    });
    expect(built).not.toHaveProperty('unreadable');
  });

  it('replays the latest queued value of each key one version past the cached record, leaving the merge base alone', () => {
    const caches = cachesHolding([record('chatSettings', { n: 0 }, '1000_0', { unreadable: true })]);

    applyReplayedChanges(caches, DEVICE, [
      change('chatSettings', { n: 1 }),
      change('chatSettings', { n: 2 }),
      change('securityConfig', { s: 1 }),
    ]);

    expect(caches.cache.get('chatSettings')).toEqual(
      buildLocalRecord('chatSettings', { n: 2 } as never, `${NOW}_0`, DEVICE),
    );
    expect(caches.cache.get('chatSettings')).not.toHaveProperty('unreadable');
    expect(caches.cache.get('securityConfig')?.value).toEqual({ s: 1 });
    expect(caches.baseCache.get('chatSettings')?.value).toEqual({ n: 0 });
    expect(caches.baseCache.has('securityConfig')).toBe(false);
  });

  it('records a synced change on the version the server answered, as the copy and as an independent merge base', () => {
    const caches = cachesHolding([record('chatSettings', { n: 0 }, '1000_0')]);

    recordSyncedChanges(caches, DEVICE, [change('chatSettings', { n: 1 })], new Map([['chatSettings', '2000_7']]));

    expect(caches.cache.get('chatSettings')).toMatchObject({
      value: { n: 1 },
      meta: { version: '2000_7', deviceId: DEVICE },
    });
    expect(caches.baseCache.get('chatSettings')).toEqual(caches.cache.get('chatSettings'));
    expect(caches.baseCache.get('chatSettings')).not.toBe(caches.cache.get('chatSettings'));
  });

  it('bumps the cached version for a synced change the server named no version for', () => {
    const caches = cachesHolding([record('chatSettings', { n: 0 }, '1000_0')]);

    recordSyncedChanges(caches, DEVICE, [change('chatSettings', { n: 1 })], new Map());

    expect(caches.cache.get('chatSettings')?.meta.version).toBe(`${NOW}_0`);
    expect(caches.baseCache.get('chatSettings')?.meta.version).toBe(`${NOW}_0`);
  });
});
