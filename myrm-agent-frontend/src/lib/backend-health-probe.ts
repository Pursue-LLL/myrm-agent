/**
 * [INPUT]
 * - `@/lib/deploy-mode` runtime mode and page-local backend base URL
 * - `@/lib/tauri` desktop sidecar health bridge
 *
 * [OUTPUT]
 * Stateless backend health probes and bounded polling primitives.
 *
 * [POS]
 * Leaf transport module. It must not depend on platform readiness or API gates.
 */
import { getBackendBaseUrl, getDeployMode } from '@/lib/deploy-mode';
import { isTauriEnvironment, tauriBackend } from '@/lib/tauri';

export type BackendDevMode = 'split_dev' | 'standalone_webui';

export interface BackendSystemStatusPayload {
  database_recovered?: boolean;
  database_degraded?: boolean;
}

export interface BackendHealthPayload {
  status: string;
  runtime_id?: string;
  dev_mode?: BackendDevMode;
  listen_port?: number;
  listen_host?: string;
  backend_port?: number;
  webui_dev_port?: number | null;
  system_status?: BackendSystemStatusPayload;
}

/** Align with desktop `BACKEND_HEALTH_*` in python_backend.rs. */
export const BACKEND_HEALTH_POLL_INTERVAL_MS = 500;
export const BACKEND_HEALTH_MAX_ATTEMPTS = 60;

export interface WaitForBackendReadyOptions {
  signal?: AbortSignal;
  pollIntervalMs?: number;
  maxAttempts?: number;
}

export async function fetchBackendHealth(): Promise<BackendHealthPayload | null> {
  try {
    const backendBase = getBackendBaseUrl();
    const healthPath = backendBase ? `${backendBase}/api/v1/health` : '/api/v1/health';
    const response = await fetch(healthPath, { cache: 'no-store' });
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

/** One-shot backend health probe for UI that must fail fast. */
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

/** Wait until Tauri injects `window.__TAURI__`; no-op outside Tauri mode. */
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

/** Poll until backend responds healthy or the bounded attempts exhaust. */
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
