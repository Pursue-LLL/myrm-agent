import { renderHook, act, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { usePushSubscription } from '../usePushSubscription';

vi.mock('@/services/web-push', () => ({
  fetchVapidPublicKey: vi.fn().mockResolvedValue('test-vapid-key'),
  registerSubscription: vi.fn().mockResolvedValue('hash-1'),
  removeSubscription: vi.fn().mockResolvedValue(undefined),
  sendTestPush: vi.fn().mockResolvedValue(1),
  urlBase64ToUint8Array: vi.fn().mockReturnValue(new Uint8Array([1, 2, 3])),
}));

function mockPushEnvironment(options: {
  serviceWorker?: boolean;
  pushManager?: boolean;
  notification?: boolean;
  permission?: NotificationPermission;
  subscription?: PushSubscription | null;
  registration?: ServiceWorkerRegistration | null;
}) {
  const {
    serviceWorker = true,
    pushManager = true,
    notification = true,
    permission = 'default',
    subscription = null,
    registration = null,
  } = options;

  if (!serviceWorker) {
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: undefined,
    });
    return;
  }

  const pushManagerMock = pushManager
    ? {
        getSubscription: vi.fn().mockResolvedValue(subscription),
        subscribe: vi.fn().mockResolvedValue({
          endpoint: 'https://push.example/sub',
          toJSON: () => ({
            endpoint: 'https://push.example/sub',
            keys: { p256dh: 'p256', auth: 'auth' },
          }),
          unsubscribe: vi.fn().mockResolvedValue(true),
        }),
      }
    : undefined;

  const reg =
    registration ??
    ({
      pushManager: pushManagerMock,
    } as unknown as ServiceWorkerRegistration);

  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: {
      ready: Promise.resolve(reg),
    },
  });

  if (notification) {
    Object.defineProperty(window, 'Notification', {
      configurable: true,
      writable: true,
      value: {
        permission,
        requestPermission: vi.fn().mockResolvedValue(permission),
      },
    });
  } else {
    Reflect.deleteProperty(window, 'Notification');
  }

  if (pushManager) {
    Object.defineProperty(window, 'PushManager', {
      configurable: true,
      writable: true,
      value: function PushManager() {},
    });
  } else {
    Reflect.deleteProperty(window, 'PushManager');
  }
}

describe('usePushSubscription', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reports unsupported when Service Worker API is missing', async () => {
    mockPushEnvironment({ serviceWorker: false });

    const { result } = renderHook(() => usePushSubscription());

    await waitFor(() => {
      expect(result.current.state).toBe('unsupported');
    });
  });

  it('reports denied when Notification permission is denied', async () => {
    mockPushEnvironment({ permission: 'denied' });

    const { result } = renderHook(() => usePushSubscription());

    await waitFor(() => {
      expect(result.current.state).toBe('denied');
    });
  });

  it('reports subscribed when an existing push subscription is present', async () => {
    mockPushEnvironment({
      subscription: { endpoint: 'https://push.example/existing' } as PushSubscription,
    });

    const { result } = renderHook(() => usePushSubscription());

    await waitFor(() => {
      expect(result.current.state).toBe('subscribed');
    });
  });

  it('reports prompt when push is supported but not subscribed', async () => {
    mockPushEnvironment({ subscription: null, permission: 'default' });

    const { result } = renderHook(() => usePushSubscription());

    await waitFor(() => {
      expect(result.current.state).toBe('prompt');
    });
  });

  it('subscribe moves to subscribed after permission grant', async () => {
    mockPushEnvironment({
      permission: 'default',
      subscription: null,
    });

    Object.defineProperty(window, 'Notification', {
      configurable: true,
      writable: true,
      value: {
        permission: 'default',
        requestPermission: vi.fn().mockResolvedValue('granted'),
      },
    });

    const { result } = renderHook(() => usePushSubscription());

    await waitFor(() => {
      expect(result.current.state).toBe('prompt');
    });

    await act(async () => {
      await result.current.subscribe();
    });

    expect(result.current.state).toBe('subscribed');
  });

  it('sendTest returns delivered count from API', async () => {
    mockPushEnvironment({ permission: 'granted', subscription: null });

    const { result } = renderHook(() => usePushSubscription());

    await act(async () => {
      const count = await result.current.sendTest();
      expect(count).toBe(1);
    });
  });
});
