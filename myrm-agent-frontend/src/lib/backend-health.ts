import { getDeployMode, isLocalMode } from '@/lib/deploy-mode';
import {
  markPlatformUnreachable,
  whenDatabaseReady,
} from '@/lib/platform-readiness';
import { isTauriEnvironment, tauriBackend } from '@/lib/tauri';

export type BackendDevMode = 'split_dev' | 'standalone_webui';

export interface BackendSystemStatusPayload {
  database_recovered?: boolean;
  database_degraded?: boolean;
}

export interface BackendHealthPayload {
  status: string;
  dev_mode?: BackendDevMode;
  listen_port?: number;
  listen_host?: string;
  backend_port?: number;
  webui_dev_port?: number | null;
  system_status?: BackendSystemStatusPayload;
}

/** Align with desktop `BACKEND_HEALTH_*` in python_backend.rs */
export const BACKEND_HEALTH_POLL_INTERVAL_MS = 500;
export const BACKEND_HEALTH_MAX_ATTEMPTS = 60;

export interface WaitForBackendReadyOptions {
  signal?: AbortSignal;
  pollIntervalMs?: number;
  maxAttempts?: number;
}

export async function fetchBackendHealth(): Promise<BackendHealthPayload | null> {
  try {
    const response = await fetch('/api/v1/health', { cache: 'no-store' });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as BackendHealthPayload;
  } catch {
    return null;
  }
}

async function probeBackendReadyOnce(): Promise<boolean> {
  if (isTauriEnvironment()) {
    try {
      return await tauriBackend.checkHealth();
    } catch {
      return false;
    }
  }

  const payload = await fetchBackendHealth();
  return payload?.status === 'healthy';
}

/** One-shot backend health probe (no polling). For inline UI before the API readiness gate resolves. */
export async function checkBackendReadyOnce(): Promise<boolean> {
  return probeBackendReadyOnce();
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }

    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      },
      { once: true },
    );
  });
}

const TAURI_RUNTIME_POLL_INTERVAL_MS = 50;
const TAURI_RUNTIME_MAX_ATTEMPTS = 60;

/**
 * Wait until Tauri injects `window.__TAURI__` (desktop dev/prod WebView).
 * No-op when deploy mode is not `tauri`.
 */
export async function waitForTauriRuntime(options: WaitForBackendReadyOptions = {}): Promise<boolean> {
  if (typeof window === 'undefined' || getDeployMode() !== 'tauri') {
    return true;
  }

  const pollIntervalMs = options.pollIntervalMs ?? TAURI_RUNTIME_POLL_INTERVAL_MS;
  const maxAttempts = options.maxAttempts ?? TAURI_RUNTIME_MAX_ATTEMPTS;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (options.signal?.aborted) {
      return false;
    }

    if (isTauriEnvironment()) {
      return true;
    }

    if (attempt < maxAttempts - 1) {
      try {
        await sleep(pollIntervalMs, options.signal);
      } catch {
        return false;
      }
    }
  }

  return isTauriEnvironment();
}

/**
 * Poll until backend responds healthy or attempts exhaust (~30s default).
 * Returns true when healthy; false on timeout or abort.
 */
export async function waitForBackendReady(options: WaitForBackendReadyOptions = {}): Promise<boolean> {
  if (getDeployMode() === 'tauri') {
    await waitForTauriRuntime(options);
  }

  const pollIntervalMs = options.pollIntervalMs ?? BACKEND_HEALTH_POLL_INTERVAL_MS;
  const maxAttempts = options.maxAttempts ?? BACKEND_HEALTH_MAX_ATTEMPTS;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (options.signal?.aborted) {
      return false;
    }

    if (await probeBackendReadyOnce()) {
      return true;
    }

    if (attempt < maxAttempts - 1) {
      try {
        await sleep(pollIntervalMs, options.signal);
      } catch {
        return false;
      }
    }
  }

  return false;
}

let localBackendReadyGate: Promise<boolean> | null = null;
let cachedLocalBackendReady = true;

function startLocalBackendReadyGate(): Promise<boolean> {
  return whenDatabaseReady();
}

/**
 * Single-flight gate: local mode waits until /health/ready reports database up.
 * Re-probes after `markLocalBackendUnreachable()` on transport failures.
 */
export function ensureLocalBackendReady(): Promise<boolean> {
  if (typeof window === 'undefined' || !isLocalMode()) {
    return Promise.resolve(true);
  }

  if (localBackendReadyGate && cachedLocalBackendReady) {
    return localBackendReadyGate;
  }

  if (localBackendReadyGate && !cachedLocalBackendReady) {
    localBackendReadyGate = whenDatabaseReady().then((ready) => {
      cachedLocalBackendReady = ready;
      return ready;
    });
    return localBackendReadyGate;
  }

  if (!localBackendReadyGate) {
    localBackendReadyGate = startLocalBackendReadyGate().then((ready) => {
      cachedLocalBackendReady = ready;
      return ready;
    });
  }

  return localBackendReadyGate;
}

/** Invalidate cached readiness after a local transport failure (mid-session backend stop). */
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
  void import('@/lib/platform-readiness').then(({ resetPlatformReadinessForTests }) => {
    resetPlatformReadinessForTests();
  });
}
