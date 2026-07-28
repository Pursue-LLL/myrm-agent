'use client';

/**
 * [INPUT]
 * - services/web-push::fetchVapidPublicKey, registerSubscription, removeSubscription, sendTestPush
 * - navigator.serviceWorker (PushManager API)
 *
 * [OUTPUT]
 * - usePushSubscription: hook for managing Web Push subscription lifecycle
 *
 * [POS]
 * Manages the browser ↔ server push subscription. Handles:
 * - Checking feature support (SW + PushManager + Notification)
 * - Subscribing/unsubscribing via VAPID
 * - Auto-reconciling existing subscriptions on mount
 * - Sending test pushes
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  fetchVapidPublicKey,
  registerSubscription,
  removeSubscription,
  sendTestPush,
  urlBase64ToUint8Array,
} from '@/services/web-push';

export type PushSubscriptionState = 'unsupported' | 'prompt' | 'denied' | 'subscribed' | 'unsubscribed';

interface UsePushSubscriptionReturn {
  state: PushSubscriptionState;
  loading: boolean;
  error: string | null;
  subscribe: () => Promise<void>;
  unsubscribe: () => Promise<void>;
  sendTest: () => Promise<number>;
}

function isPushSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator &&
    typeof window !== 'undefined' &&
    'PushManager' in window &&
    'Notification' in window
  );
}

export function usePushSubscription(): UsePushSubscriptionReturn {
  const [state, setState] = useState<PushSubscriptionState>('unsupported');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    if (!isPushSupported()) {
      setState('unsupported');
      return () => { mountedRef.current = false; };
    }

    (async () => {
      const permission = Notification.permission;
      if (permission === 'denied') {
        if (mountedRef.current) setState('denied');
        return;
      }
      try {
        const registration = await navigator.serviceWorker.ready;
        const existing = await registration.pushManager.getSubscription();
        if (!mountedRef.current) return;
        setState(existing ? 'subscribed' : permission === 'default' ? 'prompt' : 'unsubscribed');
      } catch {
        if (mountedRef.current) setState('unsubscribed');
      }
    })();

    return () => { mountedRef.current = false; };
  }, []);

  const subscribe = useCallback(async () => {
    if (!isPushSupported()) return;
    setLoading(true);
    setError(null);

    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        if (mountedRef.current) setState('denied');
        throw new Error('permission_denied');
      }

      const vapidPublicKey = await fetchVapidPublicKey();
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
      });

      try {
        await registerSubscription(subscription, navigator.userAgent);
      } catch (backendErr) {
        // Rollback: unsubscribe browser-side to prevent state drift
        await subscription.unsubscribe().catch(() => {});
        throw backendErr;
      }
      if (mountedRef.current) setState('subscribed');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg !== 'permission_denied' && mountedRef.current) setError(msg);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  const unsubscribe = useCallback(async () => {
    if (!isPushSupported()) return;
    setLoading(true);
    setError(null);

    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        await removeSubscription(subscription.endpoint);
        await subscription.unsubscribe();
      }
      if (mountedRef.current) setState('unsubscribed');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (mountedRef.current) setError(msg);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  const sendTest = useCallback(async (): Promise<number> => {
    setError(null);
    try {
      return await sendTestPush();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (mountedRef.current) setError(msg);
      throw err;
    }
  }, []);

  return { state, loading, error, subscribe, unsubscribe, sendTest };
}
