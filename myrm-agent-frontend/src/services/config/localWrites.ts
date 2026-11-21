/**
 * [INPUT]
 * - `./configFingerprint` valuesEqual (POS: deep equality for config values)
 * - `./conflictResolution` RecordSink (POS: the live caches the sync layer hands to its helpers)
 * - `./offlineReplay` mergeLatestChanges (POS: one change per key, the latest value)
 * - `./types` ConfigChange / ConfigRecord / createInitialVersion / incrementVersion (POS: record shapes and version arithmetic)
 *
 * [OUTPUT]
 * buildLocalRecord: the cached record for a value this device wrote.
 * applyReplayedChanges: optimistic cache write, and the subscribers' news, for queued changes about to be replayed (same semantics as `ConfigSyncManager.set()`).
 * recordSyncedChanges: after the backend accepted a write, what was sent becomes the merge base, and the cached copy unless a newer edit replaced it.
 *
 * [POS]
 * Cache bookkeeping for writes that originate on this device, free of manager state: callers hand in the live caches.
 * A record built here never carries `unreadable`, so an explicit save lifts that mark.
 */
import { cloneDeep } from 'lodash-es';
import { valuesEqual } from './configFingerprint';
import type { RecordSink } from './conflictResolution';
import { mergeLatestChanges } from './offlineReplay';
import type { ConfigChange, ConfigKey, ConfigRecord, ConfigValueMap, ConfigVersion } from './types';
import { createInitialVersion, incrementVersion } from './types';

type LocalCaches = Pick<RecordSink, 'cache' | 'baseCache'>;

/** 与 set() 的乐观写入同语义：新记录不带 `unreadable`，用户显式保存即解除「读不出」标记。 */
export function buildLocalRecord<K extends ConfigKey>(
  key: K,
  value: ConfigValueMap[K],
  version: ConfigVersion,
  deviceId: string,
): ConfigRecord<K> {
  return {
    key,
    value,
    meta: {
      version,
      updatedAt: new Date().toISOString(),
      deviceId,
    },
  };
}

/** Applies queued change values to the cache and tells the subscribers (mirrors the optimistic write of `set()`). */
export function applyReplayedChanges(
  { cache, baseCache, notify }: RecordSink,
  deviceId: string,
  changes: ConfigChange[],
): void {
  for (const change of mergeLatestChanges(changes, baseCache)) {
    const currentVersion = cache.get(change.key)?.meta.version ?? createInitialVersion();
    const record = buildLocalRecord(change.key, change.value, incrementVersion(currentVersion), deviceId);
    cache.set(change.key, record);
    notify(change.key, change.value, record.meta);
  }
}

/**
 * 后端已接受：已发送的值成为合并基线，并在缓存仍是该值时成为缓存副本（offline replay 等路径可能未先乐观更新）。
 * 发送期间用户又改了同一个键时缓存持有更新的值，不能被这次确认盖回旧值；它随后按新基线版本发出。
 */
export function recordSyncedChanges(
  { cache, baseCache }: LocalCaches,
  deviceId: string,
  changes: ConfigChange[],
  newVersions: ReadonlyMap<ConfigKey, ConfigVersion>,
): void {
  for (const change of changes) {
    const cached = cache.get(change.key);
    const fallbackVersion = cached?.meta.version ?? createInitialVersion();
    const newRecord = buildLocalRecord(
      change.key,
      change.value,
      newVersions.get(change.key) ?? incrementVersion(fallbackVersion),
      deviceId,
    );
    if (!cached || valuesEqual(cached.value, change.value)) {
      cache.set(change.key, newRecord);
    }
    baseCache.set(change.key, cloneDeep(newRecord));
  }
}
