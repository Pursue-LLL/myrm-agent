/** @vitest-environment node */
import { afterEach, describe, expect, it, vi } from 'vitest';

const ORIGIN = 'https://app.example';

interface ClientStub {
  url: string;
  focus: ReturnType<typeof vi.fn>;
  navigate: ReturnType<typeof vi.fn>;
}

interface WorkerHarness {
  scope: {
    skipWaiting: ReturnType<typeof vi.fn>;
    clients: {
      claim: ReturnType<typeof vi.fn>;
      matchAll: ReturnType<typeof vi.fn>;
      openWindow: ReturnType<typeof vi.fn>;
    };
    registration: { showNotification: ReturnType<typeof vi.fn> };
  };
  cacheStorage: { keys: ReturnType<typeof vi.fn>; delete: ReturnType<typeof vi.fn> };
  /** Fires the registered listener the way the browser does and waits for everything it passed to `waitUntil`. */
  dispatch: (type: string, init?: Record<string, unknown>) => Promise<void>;
}

function clientAt(url: string): ClientStub {
  return { url, focus: vi.fn().mockResolvedValue(undefined), navigate: vi.fn().mockResolvedValue(undefined) };
}

/** Loads `src/app/sw.ts` against a stubbed ServiceWorkerGlobalScope. */
async function loadWorker(cacheNames: string[] = []): Promise<WorkerHarness> {
  vi.resetModules();
  const listeners = new Map<string, (event: unknown) => void>();
  const scope = {
    location: { origin: ORIGIN },
    addEventListener: (type: string, listener: (event: unknown) => void) => {
      listeners.set(type, listener);
    },
    skipWaiting: vi.fn().mockResolvedValue(undefined),
    clients: {
      claim: vi.fn().mockResolvedValue(undefined),
      matchAll: vi.fn().mockResolvedValue([]),
      openWindow: vi.fn().mockResolvedValue(null),
    },
    registration: { showNotification: vi.fn().mockResolvedValue(undefined) },
  };
  const cacheStorage = {
    keys: vi.fn().mockResolvedValue(cacheNames),
    delete: vi.fn().mockResolvedValue(true),
  };
  vi.stubGlobal('self', scope);
  vi.stubGlobal('caches', cacheStorage);
  await import('../../../app/sw');

  const dispatch = async (type: string, init: Record<string, unknown> = {}): Promise<void> => {
    const listener = listeners.get(type);
    if (!listener) {
      throw new Error(`the worker registered no ${type} listener`);
    }
    const pending: Promise<unknown>[] = [];
    listener({ ...init, waitUntil: (promise: Promise<unknown>) => pending.push(promise) });
    await Promise.all(pending);
  };
  return { scope, cacheStorage, dispatch };
}

function jsonPush(payload: Record<string, string>): { data: { json: () => unknown; text: () => string } } {
  return { data: { json: () => payload, text: () => JSON.stringify(payload) } };
}

function click(url: string | undefined): { notification: { close: ReturnType<typeof vi.fn>; data?: { url: string } } } {
  return { notification: { close: vi.fn(), data: url === undefined ? undefined : { url } } };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('service worker lifecycle', () => {
  it('activates at once instead of waiting for open tabs to close', async () => {
    const { scope, dispatch } = await loadWorker();

    await dispatch('install');

    expect(scope.skipWaiting).toHaveBeenCalledOnce();
  });

  it('drops every cache and takes over open tabs on activation', async () => {
    const { scope, cacheStorage, dispatch } = await loadWorker(['serwist-precache-v2', 'static-js-assets']);

    await dispatch('activate');

    expect(cacheStorage.delete.mock.calls.map(([name]) => name)).toEqual(['serwist-precache-v2', 'static-js-assets']);
    expect(scope.clients.claim).toHaveBeenCalledOnce();
  });

  it('still takes over when listing the caches fails', async () => {
    const { scope, cacheStorage, dispatch } = await loadWorker();
    cacheStorage.keys.mockRejectedValue(new Error('storage unavailable'));

    await expect(dispatch('activate')).resolves.toBeUndefined();

    expect(scope.clients.claim).toHaveBeenCalledOnce();
  });

  it('waits for the remaining deletions when one of them fails', async () => {
    const { scope, cacheStorage, dispatch } = await loadWorker(['broken', 'healthy']);
    let healthyDeleted = false;
    cacheStorage.delete.mockImplementation(async (name: string) => {
      if (name === 'broken') {
        throw new Error('delete failed');
      }
      await new Promise((resolve) => setTimeout(resolve, 5));
      healthyDeleted = true;
      return true;
    });

    await expect(dispatch('activate')).resolves.toBeUndefined();

    expect(healthyDeleted).toBe(true);
    expect(scope.clients.claim).toHaveBeenCalledOnce();
  });
});

describe('push display', () => {
  it('shows the payload with a chat-scoped tag and the sanitized target', async () => {
    const { scope, dispatch } = await loadWorker();

    await dispatch('push', jsonPush({ title: 'Task done', body: 'Report ready', url: '/abcd1234efgh?approval=7' }));

    expect(scope.registration.showNotification).toHaveBeenCalledExactlyOnceWith('Task done', {
      body: 'Report ready',
      icon: '/favicon-32.png',
      badge: '/favicon-32.png',
      data: { url: '/abcd1234efgh?approval=7' },
      tag: 'myrm-abcd1234efgh',
    });
  });

  it('sends a target outside this origin to the root', async () => {
    const { scope, dispatch } = await loadWorker();

    await dispatch('push', jsonPush({ title: 'Task done', url: 'https://evil.example/abcd1234efgh' }));

    const [, options] = scope.registration.showNotification.mock.calls[0];
    expect(options.data).toEqual({ url: '/' });
  });

  it('shows a plain-text payload under the default title', async () => {
    const { scope, dispatch } = await loadWorker();
    const plainText = {
      data: {
        json: () => {
          throw new SyntaxError('not JSON');
        },
        text: () => 'Backup finished',
      },
    };

    await dispatch('push', plainText);

    const [title, options] = scope.registration.showNotification.mock.calls[0];
    expect(title).toBe('Myrm AI');
    expect(options.body).toBe('Backup finished');
    expect(options.data).toEqual({ url: '/' });
    expect(options.tag).toMatch(/^myrm-\d+$/);
  });

  it('ignores a push without data', async () => {
    const { scope, dispatch } = await loadWorker();

    await dispatch('push', { data: null });

    expect(scope.registration.showNotification).not.toHaveBeenCalled();
  });
});

describe('notification click', () => {
  it('closes the notification and opens a window when no tab is open', async () => {
    const { scope, dispatch } = await loadWorker();
    const event = click('/abcd1234efgh');

    await dispatch('notificationclick', event);

    expect(event.notification.close).toHaveBeenCalledOnce();
    expect(scope.clients.openWindow).toHaveBeenCalledExactlyOnceWith('/abcd1234efgh');
  });

  it('focuses the tab that is already on the target', async () => {
    const { scope, dispatch } = await loadWorker();
    const tab = clientAt(`${ORIGIN}/abcd1234efgh`);
    scope.clients.matchAll.mockResolvedValue([tab]);

    await dispatch('notificationclick', click('/abcd1234efgh'));

    expect(tab.focus).toHaveBeenCalledOnce();
    expect(tab.navigate).not.toHaveBeenCalled();
    expect(scope.clients.openWindow).not.toHaveBeenCalled();
  });

  it('navigates the tab on the same chat when the query differs', async () => {
    const { scope, dispatch } = await loadWorker();
    const tab = clientAt(`${ORIGIN}/abcd1234efgh`);
    scope.clients.matchAll.mockResolvedValue([tab]);

    await dispatch('notificationclick', click('/abcd1234efgh?approval=7'));

    expect(tab.navigate).toHaveBeenCalledExactlyOnceWith('/abcd1234efgh?approval=7');
    expect(tab.focus).not.toHaveBeenCalled();
  });

  it('opens a window for a tab on another page', async () => {
    const { scope, dispatch } = await loadWorker();
    scope.clients.matchAll.mockResolvedValue([clientAt(`${ORIGIN}/settings/channels`)]);

    await dispatch('notificationclick', click('/abcd1234efgh'));

    expect(scope.clients.openWindow).toHaveBeenCalledExactlyOnceWith('/abcd1234efgh');
  });

  it('treats a notification without a target as the root', async () => {
    const { scope, dispatch } = await loadWorker();

    await dispatch('notificationclick', click(undefined));

    expect(scope.clients.openWindow).toHaveBeenCalledExactlyOnceWith('/');
  });
});
