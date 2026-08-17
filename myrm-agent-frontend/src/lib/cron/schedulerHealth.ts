/**
 * [INPUT]
 * - `@/lib/api` (`apiRequest`)
 * - `@/lib/backend-health` (`checkBackendReadyOnce`)
 *
 * [OUTPUT]
 * - `SchedulerHealth` type
 * - `getCachedSchedulerHealth` / `subscribeSchedulerHealth`
 *
 * [POS]
 * Shared scheduler health fetch with single-flight dedupe for Cron badge and AppLayout banner.
 */

import { apiRequest } from '@/lib/api';
import { checkBackendReadyOnce } from '@/lib/backend-health';

export interface SchedulerHealth {
  status: 'green' | 'yellow' | 'red';
  running: boolean;
  last_tick_at: string | null;
  tick_errors: number;
  last_tick_age_seconds: number | null;
  has_timer: boolean;
}

export const SCHEDULER_HEALTH_POLL_INTERVAL_MS = 30_000;

const RED_FALLBACK: SchedulerHealth = {
  status: 'red',
  running: false,
  last_tick_at: null,
  tick_errors: 0,
  last_tick_age_seconds: null,
  has_timer: false,
};

let cached: SchedulerHealth | null = null;
let inFlight: Promise<SchedulerHealth | null> | null = null;
const listeners = new Set<(health: SchedulerHealth | null) => void>();
let pollTimer: ReturnType<typeof setInterval> | null = null;
let subscriberCount = 0;
let visibilityListenerAttached = false;

function notifyListeners(): void {
  for (const listener of listeners) {
    listener(cached);
  }
}

function onVisibilityChange(): void {
  if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
    void fetchSchedulerHealthOnce();
  }
}

export async function fetchSchedulerHealthOnce(): Promise<SchedulerHealth | null> {
  if (typeof document !== 'undefined' && document.hidden) {
    return cached;
  }

  const backendReady = await checkBackendReadyOnce();
  if (!backendReady) {
    return cached;
  }

  if (inFlight) {
    return inFlight;
  }

  inFlight = (async () => {
    try {
      const res = await apiRequest<SchedulerHealth>('/cron/scheduler/health');
      if (res) {
        cached = res;
        notifyListeners();
      }
      return cached;
    } catch {
      cached = RED_FALLBACK;
      notifyListeners();
      return cached;
    } finally {
      inFlight = null;
    }
  })();

  return inFlight;
}

function startPolling(): void {
  if (typeof window === 'undefined' || pollTimer !== null) {
    return;
  }

  void fetchSchedulerHealthOnce();

  pollTimer = setInterval(() => {
    void fetchSchedulerHealthOnce();
  }, SCHEDULER_HEALTH_POLL_INTERVAL_MS);

  if (!visibilityListenerAttached) {
    visibilityListenerAttached = true;
    document.addEventListener('visibilitychange', onVisibilityChange);
  }
}

function stopPolling(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (visibilityListenerAttached && subscriberCount === 0) {
    document.removeEventListener('visibilitychange', onVisibilityChange);
    visibilityListenerAttached = false;
  }
}

export function getCachedSchedulerHealth(): SchedulerHealth | null {
  return cached;
}

export function subscribeSchedulerHealth(
  listener: (health: SchedulerHealth | null) => void,
): () => void {
  listeners.add(listener);
  subscriberCount += 1;
  listener(cached);

  if (subscriberCount === 1) {
    startPolling();
  } else {
    void fetchSchedulerHealthOnce();
  }

  return () => {
    listeners.delete(listener);
    subscriberCount -= 1;
    if (subscriberCount === 0) {
      stopPolling();
    }
  };
}

/** Test-only reset. */
export function resetSchedulerHealthForTests(): void {
  cached = null;
  inFlight = null;
  listeners.clear();
  subscriberCount = 0;
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (visibilityListenerAttached) {
    document.removeEventListener('visibilitychange', onVisibilityChange);
    visibilityListenerAttached = false;
  }
}
