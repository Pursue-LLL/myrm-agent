/**
 * [INPUT]
 * (none — self-contained HTTP polling)
 *
 * [OUTPUT]
 * useLivenessState: Global agent liveness state from SSOT API
 *
 * [POS]
 * Polls `/api/v1/health/liveness` to provide a single global tri-state
 * (busy / idle / degraded) for all consumers: tray, Pet, tab badge.
 * Falls back to "degraded" when the API is unreachable.
 * Uses a module-level singleton poller so multiple hook consumers
 * share a single setInterval (no duplicate polling).
 */
import { useSyncExternalStore } from 'react';

export type LivenessState = 'busy' | 'idle' | 'degraded';

export interface LivenessData {
  state: LivenessState;
  activeCount: number;
  tooltip: string;
}

const POLL_INTERVAL_MS = 3_000;
const VALID_STATES = new Set<LivenessState>(['busy', 'idle', 'degraded']);

function toLivenessState(raw: unknown): LivenessState {
  if (typeof raw === 'string' && VALID_STATES.has(raw as LivenessState)) {
    return raw as LivenessState;
  }
  return 'degraded';
}

function buildTooltip(state: LivenessState, activeCount: number): string {
  if (state === 'busy') {
    return `${activeCount} task${activeCount > 1 ? 's' : ''} running`;
  }
  if (state === 'degraded') {
    return 'Service degraded';
  }
  return '';
}

// --- Module-level singleton poller ---

let currentData: LivenessData = { state: 'idle', activeCount: 0, tooltip: '' };
let listeners = new Set<() => void>();
let pollerTimer: ReturnType<typeof setInterval> | null = null;
let subscriberCount = 0;

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

async function poll(): Promise<void> {
  try {
    const res = await fetch('/api/v1/health/liveness', { cache: 'no-store' });
    if (!res.ok) {
      currentData = { state: 'degraded', activeCount: 0, tooltip: '' };
      notify();
      return;
    }
    const json = await res.json();
    const state = toLivenessState(json.state);
    const activeCount: number = json.agents?.activeCount ?? 0;
    currentData = { state, activeCount, tooltip: buildTooltip(state, activeCount) };
    notify();
  } catch {
    currentData = { state: 'degraded', activeCount: 0, tooltip: '' };
    notify();
  }
}

function startPoller(): void {
  if (pollerTimer !== null) return;
  void poll();
  pollerTimer = setInterval(() => void poll(), POLL_INTERVAL_MS);
}

function stopPoller(): void {
  if (pollerTimer === null) return;
  clearInterval(pollerTimer);
  pollerTimer = null;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  subscriberCount += 1;
  if (subscriberCount === 1) {
    startPoller();
  }
  return () => {
    listeners.delete(listener);
    subscriberCount -= 1;
    if (subscriberCount === 0) {
      stopPoller();
    }
  };
}

function getSnapshot(): LivenessData {
  return currentData;
}

const SERVER_SNAPSHOT: LivenessData = { state: 'idle', activeCount: 0, tooltip: '' };

function getServerSnapshot(): LivenessData {
  return SERVER_SNAPSHOT;
}

export function useLivenessState(): LivenessData {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
