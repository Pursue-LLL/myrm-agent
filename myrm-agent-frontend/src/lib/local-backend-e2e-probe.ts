/**
 * [INPUT]
 * - Browser `window.name` E2E runtime binding (`myrm-e2e-v1:` prefix)
 * - `window.__MYRM_E2E_RUNTIME_READY__` / `window.__MYRM_E2E_API_BASE__`
 *
 * [OUTPUT]
 * - `isChromeE2eTab`: whether the current tab is driven by Chrome MCP E2E
 * - `waitForChromeE2eBackendBinding`: wait for private Backend health before UI probes
 *
 * [POS]
 * Suppresses false "backend unreachable" banners on shared :3000 during SHPOIB E2E runs.
 */
const E2E_RUNTIME_PREFIX = 'myrm-e2e-v1:';
const E2E_BIND_POLL_MS = 200;

function hasE2eApiBase(): boolean {
  return typeof window.__MYRM_E2E_API_BASE__ === 'string' && window.__MYRM_E2E_API_BASE__.trim().length > 0;
}

export function isChromeE2eTab(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  if (hasE2eApiBase()) {
    return true;
  }
  return window.name.startsWith(E2E_RUNTIME_PREFIX);
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
  if (!isChromeE2eTab()) {
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

    if (hasE2eApiBase()) {
      const apiBase = window.__MYRM_E2E_API_BASE__.trim().replace(/\/+$/, '');
      if (await probeE2eHealth(apiBase)) {
        return true;
      }
    }

    await new Promise((resolve) => {
      window.setTimeout(resolve, E2E_BIND_POLL_MS);
    });
  }

  return false;
}
