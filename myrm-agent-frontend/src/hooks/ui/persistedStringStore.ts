/**
 * [INPUT]
 * - (localStorage, StorageEvent)
 *
 * [OUTPUT]
 * - createPersistedStringStore: a namespaced key → string memory that survives reloads and notifies its readers.
 *
 * [POS]
 * Storage layer under per-device UI memory (closed proactive cards, the composer's options region). Storage can be
 * unavailable (private mode, quota), so a value it refuses is kept in this module instead: the write then lasts for
 * the page's lifetime rather than silently doing nothing. Such a value outranks storage, because storage may still
 * hold an older one. A missing value reads as null.
 */

export interface PersistedStringStore {
  read: (key: string) => string | null;
  write: (key: string, value: string) => void;
  /** Shaped for `useSyncExternalStore`: fires after a write on this page and when another tab changes the namespace. */
  subscribe: (listener: () => void) => () => void;
}

export function createPersistedStringStore(keyPrefix: string): PersistedStringStore {
  const unpersisted = new Map<string, string>();
  const listeners = new Set<() => void>();

  const read = (key: string): string | null => {
    const storageKey = keyPrefix + key;
    const held = unpersisted.get(storageKey);
    if (held !== undefined) {
      return held;
    }
    try {
      return localStorage.getItem(storageKey);
    } catch {
      return null;
    }
  };

  const write = (key: string, value: string): void => {
    const storageKey = keyPrefix + key;
    try {
      localStorage.setItem(storageKey, value);
      unpersisted.delete(storageKey);
    } catch {
      unpersisted.set(storageKey, value);
    }
    listeners.forEach((listener) => listener());
  };

  const subscribe = (listener: () => void): (() => void) => {
    listeners.add(listener);
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key.startsWith(keyPrefix)) {
        listener();
      }
    };
    window.addEventListener('storage', onStorage);
    return () => {
      listeners.delete(listener);
      window.removeEventListener('storage', onStorage);
    };
  };

  return { read, write, subscribe };
}
