const CONFIG_INIT_LOCK = 'myrm-config-init';

/**
 * Ensures only one browser tab runs startup config migration writes.
 */
export async function withConfigInitLock<T>(fn: () => Promise<T>): Promise<T> {
  if (typeof navigator !== 'undefined' && 'locks' in navigator) {
    return navigator.locks.request(CONFIG_INIT_LOCK, fn);
  }
  return fn();
}
