"""What the React E2E bridge wait reports about a page that has not hydrated."""

from __future__ import annotations

import sys
import time

from chrome_mcp.client import ChromeMcpClient, McpPage
from e2e_core.orchestrator import touch_wall_progress

from tests.support.chrome_bridge_load import wait_for_load_to_settle

from .probe_result import _coerce_evaluate_result

_REACT_E2E_BRIDGE_PROBE_JS = """(() => ({
  ready:
    typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function'
    && window.__MYRM_E2E_CHAT__?.__e2eFallback !== true,
  hasAttach: typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function',
  // A bridge object without attachToChat means the client tree booted with a stale bundle (reload fixes it);
  // no bridge object at all means the client tree has not booted yet (only waiting helps).
  hasBridgeObject: Boolean(window.__MYRM_E2E_CHAT__),
  // The E2E runtime binding (window.name) decides whether the bootstrap script ran at all.
  hasRuntime: Boolean(window.__MYRM_E2E_RUNTIME__),
  fallback: window.__MYRM_E2E_CHAT__?.__e2eFallback === true,
  hasInput: Boolean(document.querySelector('[data-chat-input]')),
  hasAppLayout: Boolean(document.querySelector('[data-testid="app-layout"]')),
  hasSkeleton: Boolean(document.querySelector('[data-testid="app-shell-skeleton"]')),
  // React only attaches its fiber keys to the DOM once it hydrated: this separates "the client tree
  // never booted" from "the client tree booted but the bridge did not install itself".
  clientHydrated: (() => {
    const el = document.querySelector('[data-chat-input]') || document.querySelector('[data-testid="app-layout"]');
    if (!el) return false;
    return Boolean(Object.keys(el).find((k) => k.startsWith('__react') || k.includes('react')));
  })(),
  bodyLength: (document.body?.innerText || '').length,
  href: location.href,
  readyState: document.readyState,
  scriptsDone: performance.getEntriesByType('resource')
    .filter((e) => /\\.js(\\?|$)/.test(e.name) && e.responseEnd > 0).length,
  domScripts: document.scripts.length,
  // Everything still in flight, not just scripts: a pending RSC/messages request is what a booting
  // page waits for, and the .js-only counter cannot see it.
  pendingAny: performance.getEntriesByType('resource')
    .filter((e) => e.responseEnd === 0)
    .map((e) => e.name.split('/').slice(-1)[0].slice(0, 60)),
}))()"""

# Installed on the first bridge poll so a blank page that never hydrates still
# reports the uncaught errors / rejected promises it raised (no CDP console API here).
_BRIDGE_DIAG_HOOK_JS = """(() => {
  if (window.__MYRM_DIAG_ERRORS__) return true;
  const sink = (window.__MYRM_DIAG_ERRORS__ = []);
  const push = (kind, msg) => { if (sink.length < 8) sink.push(`${kind}: ${String(msg).slice(0, 240)}`); };
  window.addEventListener('error', (e) => push('error', e.message || e.filename));
  window.addEventListener('unhandledrejection', (e) => push('rejection', e.reason?.message || e.reason));
  return true;
})()"""

_BRIDGE_DIAG_SNAPSHOT_JS = """(() => {
  const scripts = performance.getEntriesByType('resource').filter((e) => /\\.js(\\?|$)/.test(e.name));
  const nav = performance.getEntriesByType('navigation')[0];
  return {
    readyState: document.readyState,
    scriptsLoaded: scripts.filter((e) => e.responseEnd > 0).length,
    scriptsPending: scripts.filter((e) => e.responseEnd === 0).length,
    slowestScripts: scripts
      .slice().sort((a, b) => b.duration - a.duration).slice(0, 3)
      .map((e) => `${Math.round(e.duration)}ms ${e.name.split('/').slice(-2).join('/').slice(0, 80)}`),
    navTtfbMs: nav ? Math.round(nav.responseStart) : null,
    navDomContentLoadedMs: nav ? Math.round(nav.domContentLoadedEventEnd) : null,
    rscChunks: Array.isArray(self.__next_f) ? self.__next_f.length : null,
    bodyChildren: document.body?.children.length ?? null,
    nextErrorDialog: (() => {
      const portal = document.querySelector('nextjs-portal');
      const dialog = document.querySelector('[data-nextjs-dialog]')
        || portal?.shadowRoot?.querySelector('[data-nextjs-dialog]');
      return dialog ? (dialog.textContent || '').slice(0, 300) : null;
    })(),
    bodyHead: (document.body?.innerHTML || '').slice(0, 200),
    scriptSrcs: Array.from(document.scripts).map((s) => s.src).filter(Boolean).slice(0, 10),
    pageErrors: window.__MYRM_DIAG_ERRORS__ || null,
  };
})()"""


def _bridge_failure_diagnostics(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    """Best-effort page snapshot attached to the bridge-timeout error; never raises."""
    try:
        return _coerce_evaluate_result(client.evaluate(page, _BRIDGE_DIAG_SNAPSHOT_JS, timeout_sec=10.0))
    except Exception as exc:  # noqa: BLE001 - diagnostics must not mask the original timeout
        return {"diagnosticsError": f"{type(exc).__name__}: {str(exc)[:160]}"}


def _log_bridge_wait_state(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    polls: int,
    reload_passes: int,
    last: dict[str, object],
) -> None:
    """Emit bridge-wait state to stderr so a hung loop killed by the outer wall stays diagnosable."""
    print(
        f"E2E_BRIDGE_WAIT: polls={polls} reload_passes={reload_passes} probe={last} "
        f"diagnostics={_bridge_failure_diagnostics(client, page)}",
        file=sys.stderr,
        flush=True,
    )


def _wait_for_page_load_to_settle(
    client: ChromeMcpClient,
    page: McpPage,
    first_probe: dict[str, object],
    *,
    deadline: float,
) -> str:
    """Hold the heal reloads back while the page is still loading its scripts (see ``chrome_bridge_load``)."""
    started_at = time.monotonic()

    def read_probe() -> dict[str, object]:
        return _coerce_evaluate_result(client.evaluate(page, _REACT_E2E_BRIDGE_PROBE_JS, timeout_sec=10.0))

    outcome = wait_for_load_to_settle(
        read_probe,
        first_probe,
        deadline=deadline,
        on_wait=lambda: touch_wall_progress(current_node="wait_for_page_load"),
        clock=time.monotonic,
        sleep=time.sleep,
    )
    print(
        f"E2E_BRIDGE_LOAD_WAIT: outcome={outcome} waited={time.monotonic() - started_at:.0f}s",
        file=sys.stderr,
        flush=True,
    )
    return outcome
