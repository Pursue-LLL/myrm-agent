/**
 * [INPUT]
 * - `@/lib/backend-health-probe` (POS: leaf transport, stateless health probes and bounded polling)
 * - `@/lib/deploy-mode` (POS: deploy mode and base URL resolution)
 * - `@/lib/tauri` (POS: Tauri native bridge, runtime detection and shell event subscription)
 * - `@/lib/utils/networkResilience` (POS: abortable waits for poll intervals)
 *
 * [OUTPUT]
 * Platform readiness SSOT: gate business API until backend DB is reachable. When the shell reports a failure it
 * will not recover from, every parked wait ends at once and later waits fail after one probe until the backend
 * answers again.
 *
 * [POS]
 * Frontend-only coordinator. Subscribers await `whenDatabaseReady()` before
 * ConfigSync, approvals recovery, and TauriAdapter config fetches.
 */
import { getBackendBaseUrl, isLocalMode } from '@/lib/deploy-mode';
import {
  BACKEND_HEALTH_MAX_ATTEMPTS,
  BACKEND_HEALTH_POLL_INTERVAL_MS,
  waitForBackendReady,
  waitForTauriRuntime,
} from '@/lib/backend-health-probe';
import { isTauriEnvironment, listenTauriEvent } from '@/lib/tauri';
import { abortableDelay } from '@/lib/utils/networkResilience';

export type PlatformReadinessState = 'unreachable' | 'warming' | 'ready';

export interface PlatformReadinessSnapshot {
  state: PlatformReadinessState;
  database: boolean;
}

interface HealthReadyResponse {
  ready?: boolean;
  checks?: {
    database?: boolean;
  };
}

type ReadinessListener = (snapshot: PlatformReadinessSnapshot) => void;

/**
 * Shell events for failures it will not recover from: the sidecar failed to start, or the watchdog gave up
 * restarting it. `backend-crash` is not final (the watchdog restarts the sidecar), so waits stay parked through it.
 */
const FINAL_FAILURE_EVENTS = ['backend-start-failed', 'backend-crash-loop'] as const;

let snapshot: PlatformReadinessSnapshot = {
  state: isLocalMode() ? 'warming' : 'ready',
  database: !isLocalMode(),
};

let warmPromise: Promise<PlatformReadinessSnapshot> | null = null;
// Every poll reads the controller current when it starts, including polls `markPlatformUnreachable` detached
// from `warmPromise`; aborting it ends them all, and later polls use the replacement.
let warmAbort = new AbortController();
// Set by a final failure and cleared by the next healthy probe. While set, a wait fails after one probe instead
// of polling a whole budget for a backend nobody is restarting.
let backendFinallyDown = false;
let listeningForFinalFailure = false;
const listeners = new Set<ReadinessListener>();

function emit(next: PlatformReadinessSnapshot): void {
  snapshot = next;
  for (const listener of listeners) {
    listener(next);
  }
}

export function getPlatformReadinessSnapshot(): PlatformReadinessSnapshot {
  return snapshot;
}

export function subscribePlatformReadiness(listener: ReadinessListener): () => void {
  listeners.add(listener);
  listener(snapshot);
  return () => {
    listeners.delete(listener);
  };
}

async function probeDatabaseReady(): Promise<PlatformReadinessSnapshot> {
  if (!isLocalMode()) {
    return { state: 'ready', database: true };
  }

  try {
    const backendBase = getBackendBaseUrl();
    const readyPath = backendBase ? `${backendBase}/api/v1/health/ready` : '/api/v1/health/ready';
    const response = await fetch(readyPath, { cache: 'no-store' });
    if (!response.ok) {
      return { state: 'unreachable', database: false };
    }

    const body = (await response.json()) as HealthReadyResponse;
    const database = body.checks?.database === true;
    return {
      state: database ? 'ready' : 'warming',
      database,
    };
  } catch {
    return { state: 'unreachable', database: false };
  }
}

function endWaitsOnFinalFailure(): void {
  backendFinallyDown = true;
  warmAbort.abort();
  warmAbort = new AbortController();
}

/** Idempotent; a failed subscription is retried by the next warm. */
function listenForFinalFailure(): void {
  if (listeningForFinalFailure || !isTauriEnvironment()) {
    return;
  }

  listeningForFinalFailure = true;
  void Promise.all(FINAL_FAILURE_EVENTS.map((event) => listenTauriEvent(event, endWaitsOnFinalFailure))).catch(() => {
    listeningForFinalFailure = false;
  });
}

async function warmUntilDatabaseReady(signal: AbortSignal): Promise<PlatformReadinessSnapshot> {
  if (!isLocalMode()) {
    emit({ state: 'ready', database: true });
    return snapshot;
  }

  emit({ state: 'warming', database: false });

  // A final failure event is what ends the long poll below early, so subscribe before it starts.
  if (await waitForTauriRuntime({ signal })) {
    listenForFinalFailure();
  }

  // The default budget depends on who owns the backend process (see `getBackendHealthMaxAttempts`).
  const healthy = await waitForBackendReady({ signal, ...(backendFinallyDown ? { maxAttempts: 1 } : {}) });

  if (!healthy) {
    emit({ state: 'unreachable', database: false });
    return snapshot;
  }

  backendFinallyDown = false;

  for (let attempt = 0; attempt < BACKEND_HEALTH_MAX_ATTEMPTS && !signal.aborted; attempt += 1) {
    const probed = await probeDatabaseReady();
    if (probed.database) {
      emit({ state: 'ready', database: true });
      return snapshot;
    }

    if (attempt < BACKEND_HEALTH_MAX_ATTEMPTS - 1) {
      try {
        await abortableDelay(BACKEND_HEALTH_POLL_INTERVAL_MS, signal);
      } catch {
        break;
      }
    }
  }

  emit({ state: 'unreachable', database: false });
  return snapshot;
}

/** Single-flight warm: poll /health then /health/ready until database is up. */
export function ensurePlatformReadiness(): Promise<PlatformReadinessSnapshot> {
  if (!isLocalMode()) {
    return Promise.resolve({ state: 'ready', database: true });
  }

  if (snapshot.state === 'ready' && snapshot.database) {
    return Promise.resolve(snapshot);
  }

  if (!warmPromise) {
    // `markPlatformUnreachable` can replace `warmPromise` while this warm is still polling, so only clear our own.
    const warm = warmUntilDatabaseReady(warmAbort.signal).finally(() => {
      if (warmPromise === warm) {
        warmPromise = null;
      }
    });
    warmPromise = warm;
  }

  return warmPromise;
}

/** Gate business APIs on database readiness (config, approvals, etc.). */
export async function whenDatabaseReady(): Promise<boolean> {
  const result = await ensurePlatformReadiness();
  return result.database;
}

/** Invalidate after proxy/transport failures so the next gate re-probes. */
export function markPlatformUnreachable(): void {
  if (!isLocalMode()) {
    return;
  }
  warmPromise = null;
  emit({ state: 'unreachable', database: false });
}

/** @internal */
export function resetPlatformReadinessForTests(): void {
  warmAbort.abort();
  warmAbort = new AbortController();
  backendFinallyDown = false;
  listeningForFinalFailure = false;
  warmPromise = null;
  snapshot = {
    state: isLocalMode() ? 'warming' : 'ready',
    database: !isLocalMode(),
  };
  listeners.clear();
}
