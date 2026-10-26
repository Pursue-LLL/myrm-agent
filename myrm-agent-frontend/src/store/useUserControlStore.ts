/**
 * [INPUT]
 * - zustand::create (POS: Lightweight state management)
 * - @/lib/api::fetchWithTimeout, fetchOnPageExit (POS: Direct REST client; the latter survives page teardown)
 *
 * [OUTPUT]
 * useUserControlStore: whether the person currently drives the agent's browser/desktop (`held`),
 * with `acquire` (take control) and `release` (hand back).
 *
 * [POS]
 * Client side of the server's single "who holds control" fact (`/webui/vnc/takeover`, `/webui/vnc/resume`).
 * While held it renews the server lease every 30s and mirrors the server back, so the UI never claims control
 * the agent has already taken back. A closed tab stops renewing; the server hands control back when the lease
 * runs out, and `pagehide` hands it back at once.
 */

import { create } from 'zustand';
import { fetchOnPageExit, fetchWithTimeout } from '@/lib/api';

const TAKEOVER_ENDPOINT = '/webui/vnc/takeover';
const RESUME_ENDPOINT = '/webui/vnc/resume';
const HEARTBEAT_INTERVAL_MS = 30_000;

export interface UserControlResumeResult {
  learned: boolean;
}

interface UserControlState {
  held: boolean;
  /** Take control, or renew while holding it. Resolves false when the server did not grant it. */
  acquire: (reason?: string) => Promise<boolean>;
  /** Hand control back. Rejects when the server could not be told, leaving `held` as it was. */
  release: () => Promise<UserControlResumeResult>;
}

let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let queue: Promise<unknown> = Promise.resolve();

/**
 * Take, renew and hand back run one after another: a renewal that lands after the hand-back
 * would silently take control again.
 */
function serialized<T>(operation: () => Promise<T>): Promise<T> {
  const run = queue.then(operation);
  queue = run.catch(() => undefined);
  return run;
}

function jsonPost(body?: Record<string, string>): RequestInit {
  return body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    : { method: 'POST' };
}

function stopHeartbeat(): void {
  if (heartbeatTimer !== null) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function startHeartbeat(): void {
  if (heartbeatTimer === null) {
    heartbeatTimer = setInterval(() => void serialized(renewLease), HEARTBEAT_INTERVAL_MS);
  }
}

async function renewLease(): Promise<void> {
  if (!useUserControlStore.getState().held) {
    return;
  }
  try {
    const stateRes = await fetchWithTimeout(TAKEOVER_ENDPOINT);
    if (!stateRes.ok) {
      return;
    }
    const { state } = (await stateRes.json()) as { state: string };
    if (state !== 'user_takeover') {
      // The lease ran out or control was handed back elsewhere: stop claiming it.
      stopHeartbeat();
      useUserControlStore.setState({ held: false });
      return;
    }
    await fetchWithTimeout(TAKEOVER_ENDPOINT, jsonPost());
  } catch {
    // Transient failure: the next beat retries, and the server lease is the safety net.
  }
}

const useUserControlStore = create<UserControlState>((set) => ({
  held: false,

  acquire: (reason = '') =>
    serialized(async () => {
      try {
        const res = await fetchWithTimeout(TAKEOVER_ENDPOINT, jsonPost({ reason }));
        if (!res.ok) {
          return false;
        }
      } catch {
        return false;
      }
      set({ held: true });
      startHeartbeat();
      return true;
    }),

  release: () =>
    serialized(async () => {
      const res = await fetchWithTimeout(RESUME_ENDPOINT, jsonPost());
      if (!res.ok) {
        throw new Error(`Hand back failed with status ${res.status}`);
      }
      stopHeartbeat();
      set({ held: false });
      return (await res.json()) as UserControlResumeResult;
    }),
}));

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => {
    if (useUserControlStore.getState().held) {
      fetchOnPageExit(RESUME_ENDPOINT, { method: 'POST' });
    }
  });
}

export default useUserControlStore;
