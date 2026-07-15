/**
 * [INPUT]
 * - `@/lib/backend-health` health probes
 * - `@/lib/deploy-mode` local vs cloud
 *
 * [OUTPUT]
 * Platform readiness SSOT: gate business API until backend DB is reachable.
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
} from '@/lib/backend-health';

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

let snapshot: PlatformReadinessSnapshot = {
  state: isLocalMode() ? 'warming' : 'ready',
  database: !isLocalMode(),
};

let warmPromise: Promise<PlatformReadinessSnapshot> | null = null;
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

async function warmUntilDatabaseReady(): Promise<PlatformReadinessSnapshot> {
  if (!isLocalMode()) {
    emit({ state: 'ready', database: true });
    return snapshot;
  }

  emit({ state: 'warming', database: false });

  const healthy = await waitForBackendReady({
    pollIntervalMs: BACKEND_HEALTH_POLL_INTERVAL_MS,
    maxAttempts: BACKEND_HEALTH_MAX_ATTEMPTS,
  });

  if (!healthy) {
    emit({ state: 'unreachable', database: false });
    return snapshot;
  }

  for (let attempt = 0; attempt < BACKEND_HEALTH_MAX_ATTEMPTS; attempt += 1) {
    const probed = await probeDatabaseReady();
    if (probed.database) {
      emit({ state: 'ready', database: true });
      return snapshot;
    }

    if (attempt < BACKEND_HEALTH_MAX_ATTEMPTS - 1) {
      await new Promise((resolve) => setTimeout(resolve, BACKEND_HEALTH_POLL_INTERVAL_MS));
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
    warmPromise = warmUntilDatabaseReady().finally(() => {
      warmPromise = null;
    });
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
  warmPromise = null;
  snapshot = {
    state: isLocalMode() ? 'warming' : 'ready',
    database: !isLocalMode(),
  };
  listeners.clear();
}
