'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  fetchVapidPublicKey,
  registerSubscription,
  removeSubscription,
  sendTestPush,
  urlBase64ToUint8Array,
} from '@/services/web-push';

export type WebPushState = 'unsupported' | 'prompt' | 'subscribed' | 'denied' | 'loading';

interface UseWebPushReturn {
  state: WebPushState;
  subscribe: () => Promise<void>;
  unsubscribe: () => Promise<void>;
  sendTest: () => Promise<number>;
}

function getSwRegistration(): Promise<ServiceWorkerRegistration | null> {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) {
    return Promise.resolve(null);
  }
  return navigator.serviceWorker.ready.catch(() => null);
}

function isPushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

export function useWebPush(): UseWebPushReturn {
  const [state, setState] = useState<WebPushState>('loading');

  useEffect(() => {
    if (!isPushSupported()) {
      setState('unsupported');
      return;
    }

    if (Notification.permission === 'denied') {
      setState('denied');
      return;
    }

    void getSwRegistration().then(async (reg) => {
      if (!reg) {
        setState('unsupported');
        return;
      }
      const existing = await reg.pushManager.getSubscription();
      setState(existing ? 'subscribed' : 'prompt');
    });
  }, []);

  const subscribe = useCallback(async () => {
    if (!isPushSupported()) return;

    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      setState('denied');
      return;
    }

    setState('loading');
    try {
      const vapidKey = await fetchVapidPublicKey();
      const reg = await getSwRegistration();
      if (!reg) {
        setState('unsupported');
        return;
      }

      const subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      });

      await registerSubscription(subscription, navigator.userAgent);
      setState('subscribed');
    } catch (err) {
      console.error('Web Push subscribe failed:', err);
      setState('prompt');
    }
  }, []);

  const unsubscribe = useCallback(async () => {
    setState('loading');
    try {
      const reg = await getSwRegistration();
      if (!reg) {
        setState('unsupported');
        return;
      }

      const subscription = await reg.pushManager.getSubscription();
      if (subscription) {
        await removeSubscription(subscription.endpoint);
        await subscription.unsubscribe();
      }
      setState('prompt');
    } catch (err) {
      console.error('Web Push unsubscribe failed:', err);
      setState('prompt');
    }
  }, []);

  const sendTest = useCallback(async () => {
    return sendTestPush();
  }, []);

  return { state, subscribe, unsubscribe, sendTest };
}
