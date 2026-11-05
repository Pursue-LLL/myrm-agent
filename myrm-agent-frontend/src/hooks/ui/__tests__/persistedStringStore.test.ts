import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createPersistedStringStore } from '../persistedStringStore';

/**
 * A stand-in for `localStorage` whose failures the test controls. The test environment's own storage is a
 * polyfill, so a spy on `Storage.prototype` would not reach it; a stubbed global behaves the same everywhere.
 */
function stubLocalStorage(initial: Record<string, string> = {}) {
  const control = { data: new Map(Object.entries(initial)), refuseReads: false, refuseWrites: false };
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => {
      if (control.refuseReads) {
        throw new DOMException('denied', 'SecurityError');
      }
      return control.data.get(key) ?? null;
    },
    setItem: (key: string, value: string) => {
      if (control.refuseWrites) {
        throw new DOMException('quota', 'QuotaExceededError');
      }
      control.data.set(key, value);
    },
  });
  return control;
}

describe('persisted string store', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reads null for a key nobody wrote', () => {
    expect(createPersistedStringStore('ns.').read('missing')).toBeNull();
  });

  it('persists under the namespace prefix and keeps namespaces apart', () => {
    const first = createPersistedStringStore('first.');
    const second = createPersistedStringStore('second.');

    first.write('flag', '1');

    expect(localStorage.getItem('first.flag')).toBe('1');
    expect(first.read('flag')).toBe('1');
    expect(second.read('flag')).toBeNull();
  });

  it('reads null instead of throwing when storage cannot be read', () => {
    stubLocalStorage({ 'ns.flag': '1' }).refuseReads = true;

    expect(createPersistedStringStore('ns.').read('flag')).toBeNull();
  });

  it('keeps a refused write for this page and lets it outrank the older value storage still holds', () => {
    const control = stubLocalStorage({ 'ns.flag': '1' });
    const store = createPersistedStringStore('ns.');
    control.refuseWrites = true;

    store.write('flag', '0');

    expect(control.data.get('ns.flag')).toBe('1');
    expect(store.read('flag')).toBe('0');
  });

  it('hands authority back to storage once a write is accepted again', () => {
    const control = stubLocalStorage();
    const store = createPersistedStringStore('ns.');
    control.refuseWrites = true;
    store.write('flag', '1');
    expect(store.read('flag')).toBe('1');

    control.refuseWrites = false;
    store.write('flag', '0');
    expect(control.data.get('ns.flag')).toBe('0');
    expect(store.read('flag')).toBe('0');

    // Another tab's value is visible again: the page no longer holds a value that shadows storage.
    control.data.set('ns.flag', '1');
    expect(store.read('flag')).toBe('1');
  });

  it('notifies subscribers after a write and after another tab changes the namespace, and only then', () => {
    const store = createPersistedStringStore('ns.');
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);

    store.write('flag', '1');
    expect(listener).toHaveBeenCalledTimes(1);

    window.dispatchEvent(new StorageEvent('storage', { key: 'ns.flag' }));
    expect(listener).toHaveBeenCalledTimes(2);

    window.dispatchEvent(new StorageEvent('storage', { key: null }));
    expect(listener).toHaveBeenCalledTimes(3);

    window.dispatchEvent(new StorageEvent('storage', { key: 'other.flag' }));
    expect(listener).toHaveBeenCalledTimes(3);

    unsubscribe();
    store.write('flag', '0');
    window.dispatchEvent(new StorageEvent('storage', { key: 'ns.flag' }));
    expect(listener).toHaveBeenCalledTimes(3);
  });
});
