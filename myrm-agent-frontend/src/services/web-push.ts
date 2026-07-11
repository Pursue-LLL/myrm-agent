/**
 * Web Push API client — manages VAPID key retrieval, subscription, and unsubscription.
 *
 * [POS] Thin API layer for Web Push REST endpoints on the backend.
 */

import { getApiUrl } from '@/lib/api';

interface WebPushVapidKeyResponse {
  public_key: string;
}

interface WebPushSubscriptionResponse {
  endpoint_hash: string;
}

export async function fetchVapidPublicKey(): Promise<string> {
  const res = await fetch(getApiUrl('/web-push/vapid-key'));
  if (!res.ok) throw new Error(`Failed to fetch VAPID key: ${res.status}`);
  const data = (await res.json()) as WebPushVapidKeyResponse;
  return data.public_key;
}

export async function registerSubscription(
  subscription: PushSubscription,
  userAgent: string = '',
): Promise<string> {
  const json = subscription.toJSON();
  const res = await fetch(getApiUrl('/web-push/subscribe'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      endpoint: json.endpoint,
      p256dh: json.keys?.p256dh ?? '',
      auth: json.keys?.auth ?? '',
      user_agent: userAgent,
    }),
  });
  if (!res.ok) throw new Error(`Failed to register subscription: ${res.status}`);
  const data = (await res.json()) as WebPushSubscriptionResponse;
  return data.endpoint_hash;
}

export async function removeSubscription(endpoint: string): Promise<void> {
  const res = await fetch(getApiUrl('/web-push/unsubscribe'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ endpoint }),
  });
  if (!res.ok) throw new Error(`Failed to unsubscribe: ${res.status}`);
}

export async function sendTestPush(): Promise<number> {
  const res = await fetch(getApiUrl('/web-push/test'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`Failed to send test push: ${res.status}`);
  const data = (await res.json()) as { delivered: number };
  return data.delivered;
}

/**
 * Convert a URL-safe base64 string (no padding) to a Uint8Array.
 * Required for PushManager.subscribe({ applicationServerKey }).
 */
export function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}
