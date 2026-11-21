/**
 * [INPUT]
 * - `./conflictResolution` RecordSink (POS: the live caches the sync layer hands to its helpers)
 * - `./offlineReplay` mergeLatestChanges (POS: one change per key, the latest value)
 * - `./types` ConfigChange / ConfigRecord / createInitialVersion / incrementVersion (POS: record shapes and version arithmetic)
 *
 * [OUTPUT]
 * buildLocalRecord: the cached record for a value this device wrote.
 * applyReplayedChanges: optimistic cache write for queued changes about to be replayed (same semantics as `ConfigSyncManager.set()`).
 * recordSyncedChanges: after a successful sync, what was sent becomes the cached copy and the merge base.
 *
 * [POS]
 * Cache bookkeeping for writes that originate on this device, free of manager state: callers hand in the live caches.
 * A record built here never carries `unreadable`, so an explicit save lifts that mark.
 */
import { cloneDeep } from 'lodash-es';
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

/** Apply queued change values to cache (mirrors set() optimistic write for offline replay). */
export function applyReplayedChanges(
  { cache, baseCache }: LocalCaches,
  deviceId: string,
  changes: ConfigChange[],
): void {
  for (const change of mergeLatestChanges(changes, baseCache)) {
    const currentVersion = cache.get(change.key)?.meta.version ?? createInitialVersion();
    cache.set(change.key, buildLocalRecord(change.key, change.value, incrementVersion(currentVersion), deviceId));
  }
}

/** 同步成功：cache/baseCache 必须与已发送的变更一致（offline replay 等路径可能未先乐观更新）。 */
export function recordSyncedChanges(
  { cache, baseCache }: LocalCaches,
  deviceId: string,
  changes: ConfigChange[],
  newVersions: ReadonlyMap<ConfigKey, ConfigVersion>,
): void {
  for (const change of changes) {
    const fallbackVersion = cache.get(change.key)?.meta.version ?? createInitialVersion();
    const newRecord = buildLocalRecord(
      change.key,
      change.value,
      newVersions.get(change.key) ?? incrementVersion(fallbackVersion),
      deviceId,
    );
    cache.set(change.key, newRecord);
    baseCache.set(change.key, cloneDeep(newRecord));
  }
}
