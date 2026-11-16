/**
 * [INPUT]
 * - `window.__MYRM_E2E_RUNTIME_READY__` / `window.__MYRM_E2E_API_BASE__` (POS: the validated E2E binding the page bootstrap or CDP script sets)
 *
 * [OUTPUT]
 * - `isChromeE2eTab`: whether the page carries a validated E2E backend binding; always false in a production build
 * - `waitForChromeE2eBackendBinding`: wait for private Backend health before UI probes
 *
 * [POS]
 * Suppresses false "backend unreachable" banners on the shared dev UI during SHPOIB E2E runs.
 */
const E2E_BIND_POLL_MS = 200;

/** The API base the E2E tooling bound to this page, or null; a production build has no binding. */
function boundApiBase(): string | null {
  if (process.env.NODE_ENV === 'production' || typeof window === 'undefined') {
    return null;
  }
  const apiBase = window.__MYRM_E2E_API_BASE__;
  return typeof apiBase === 'string' && apiBase.trim().length > 0 ? apiBase.trim() : null;
}

export function isChromeE2eTab(): boolean {
  return boundApiBase() !== null;
}

async function probeE2eHealth(apiBase: string): Promise<boolean> {
  try {
    const response = await fetch(`${apiBase}/api/v1/health`, { cache: 'no-store' });
    return response.ok;
  } catch {
    return false;
  }
}

export async function waitForChromeE2eBackendBinding(maxWaitMs = 60_000): Promise<boolean> {
  if (process.env.NODE_ENV === 'production' || !isChromeE2eTab()) {
    return false;
  }

  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    const readyPromise = window.__MYRM_E2E_RUNTIME_READY__;
    if (readyPromise) {
      try {
        await readyPromise;
        return true;
      } catch {
        return false;
      }
    }

    const apiBase = boundApiBase();
    if (apiBase !== null && (await probeE2eHealth(apiBase.replace(/\/+$/, '')))) {
      return true;
    }

    await new Promise((resolve) => {
      window.setTimeout(resolve, E2E_BIND_POLL_MS);
    });
  }

  return false;
}
