/**
 * [INPUT]
 * - `./types` ConfigKey / ConfigRecord / ConfigValueMap (POS: key union and record shapes)
 *
 * [OUTPUT]
 * ConfigChangeListener: callback signature for config change subscribers.
 * ConfigListenerRegistry: per-key subscriber set with fault-isolated delivery.
 *
 * [POS]
 * Subscription half of `ConfigSyncManager`. A listener that throws is logged and skipped so one broken subscriber
 * cannot keep the others from seeing a change.
 */
import type { ConfigKey, ConfigRecord, ConfigValueMap } from './types';

/**
 * 配置变更监听器
 */
export type ConfigChangeListener<K extends ConfigKey = ConfigKey> = (
  key: K,
  value: ConfigValueMap[K],
  meta: ConfigRecord<K>['meta'],
) => void;

export class ConfigListenerRegistry {
  private listeners: Map<ConfigKey, Set<ConfigChangeListener>> = new Map();

  /** Returns the unsubscribe function. */
  subscribe<K extends ConfigKey>(key: K, listener: ConfigChangeListener<K>): () => void {
    let keyListeners = this.listeners.get(key);
    if (!keyListeners) {
      keyListeners = new Set();
      this.listeners.set(key, keyListeners);
    }
    keyListeners.add(listener as ConfigChangeListener);

    return () => {
      this.listeners.get(key)?.delete(listener as ConfigChangeListener);
    };
  }

  notify<K extends ConfigKey>(key: K, value: ConfigValueMap[K], meta: ConfigRecord<K>['meta']): void {
    for (const listener of this.listeners.get(key) ?? []) {
      try {
        listener(key, value, meta);
      } catch (error) {
        console.warn(`[ConfigSync] Listener error for '${key}':`, error);
      }
    }
  }
}
