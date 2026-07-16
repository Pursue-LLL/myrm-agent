/**
 * [INPUT]
 * - `@/lib/backend-health-probe` raw backend and Tauri health probes
 * - `@/lib/platform-readiness` database readiness state machine
 *
 * [OUTPUT]
 * - Raw health probe facade exports
 * - Local business-request readiness gate and invalidation
 *
 * [POS]
 * Backend readiness facade. Raw probes remain dependency-free so platform
 * readiness can consume them without creating a circular module dependency.
 */
import { isLocalMode } from '@/lib/deploy-mode';
import {
  markPlatformUnreachable,
  resetPlatformReadinessForTests,
  whenDatabaseReady,
} from '@/lib/platform-readiness';

export {
  BACKEND_HEALTH_MAX_ATTEMPTS,
  BACKEND_HEALTH_POLL_INTERVAL_MS,
  checkBackendReadyOnce,
  fetchBackendHealth,
  waitForBackendReady,
  waitForTauriRuntime,
} from '@/lib/backend-health-probe';
export type {
  BackendDevMode,
  BackendHealthPayload,
  BackendSystemStatusPayload,
  WaitForBackendReadyOptions,
} from '@/lib/backend-health-probe';

let localBackendReadyGate: Promise<boolean> | null = null;
let cachedLocalBackendReady = true;

function probeDatabaseReadiness(): Promise<boolean> {
  return whenDatabaseReady().then((ready) => {
    cachedLocalBackendReady = ready;
    return ready;
  });
}

/**
 * Single-flight gate: local mode waits until /health/ready reports database up.
 * A failed or invalidated gate is re-probed so a restarted backend can recover.
 */
export function ensureLocalBackendReady(): Promise<boolean> {
  if (typeof window === 'undefined' || !isLocalMode()) {
    return Promise.resolve(true);
  }

  if (localBackendReadyGate && cachedLocalBackendReady) {
    return localBackendReadyGate;
  }

  localBackendReadyGate = probeDatabaseReadiness();
  return localBackendReadyGate;
}

/** Invalidate transport and database readiness after a local request failure. */
export function markLocalBackendUnreachable(): void {
  if (typeof window === 'undefined' || !isLocalMode()) {
    return;
  }
  cachedLocalBackendReady = false;
  localBackendReadyGate = null;
  markPlatformUnreachable();
}

/** @internal test helper */
export function resetLocalBackendReadyGate(): void {
  localBackendReadyGate = null;
  cachedLocalBackendReady = true;
  resetPlatformReadinessForTests();
}
