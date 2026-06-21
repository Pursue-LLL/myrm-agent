import { isTauriEnvironment, tauriBackend } from '@/lib/tauri';

export type BackendDevMode = 'split_dev' | 'standalone_webui';

export interface BackendHealthPayload {
  status: string;
  dev_mode?: BackendDevMode;
  listen_port?: number;
  listen_host?: string;
  frontend_proxy_port?: number;
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

/**
 * Poll until backend responds healthy or attempts exhaust (~30s default).
 * Returns true when healthy; false on timeout or abort.
 */
export async function waitForBackendReady(options: WaitForBackendReadyOptions = {}): Promise<boolean> {
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
