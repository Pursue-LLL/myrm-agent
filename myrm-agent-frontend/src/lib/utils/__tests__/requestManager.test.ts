import { afterEach, describe, expect, it, vi } from 'vitest';

async function loadRequestManager() {
  vi.resetModules();
  return (await import('../requestManager')).requestManager;
}

describe('requestManager', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('registers no page-exit listeners: the browser ends in-flight requests when the page goes away, `unload` is deprecated, and a navigation the user cancels must not kill live requests', async () => {
    const addListener = vi.spyOn(window, 'addEventListener');

    await loadRequestManager();

    const pageExitListeners = addListener.mock.calls
      .map(([type]): string => type)
      .filter((type) => type === 'beforeunload' || type === 'unload');
    expect(pageExitListeners).toEqual([]);
  });

  it('cancels every request that is still pending', async () => {
    const manager = await loadRequestManager();
    const first = new AbortController();
    const second = new AbortController();
    manager.registerRequest(first);
    manager.registerRequest(second);

    manager.cancelAllRequests();

    expect(first.signal.aborted).toBe(true);
    expect(second.signal.aborted).toBe(true);
  });

  it('leaves a request alone once it has been unregistered', async () => {
    const manager = await loadRequestManager();
    const finished = new AbortController();
    manager.registerRequest(finished);
    manager.unregisterRequest(finished);

    manager.cancelAllRequests();

    expect(finished.signal.aborted).toBe(false);
  });

  it('tolerates a request that was already aborted by its owner', async () => {
    const manager = await loadRequestManager();
    const stopped = new AbortController();
    manager.registerRequest(stopped);
    stopped.abort('stopped by user');

    expect(() => manager.cancelAllRequests()).not.toThrow();
    expect(stopped.signal.reason).toBe('stopped by user');
  });
});
