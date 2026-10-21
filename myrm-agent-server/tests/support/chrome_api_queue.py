"""Wait until a request made now would not queue behind the page's mount-time fan-out, before a user-triggered mutation.

A Chrome tab opens at most six HTTP/1.1 connections per host, long-lived streams keep some of them for good, and a
CORS preflight doubles every request toward the API origin. On a loaded host the chat page's mount fan-out (dozens of
requests) therefore keeps a request made afterwards waiting longer than the app's 30 s fetch timeout, so the mutation a
test clicks for is aborted before it is ever sent. A user does not click inside that window, and the test must not
either. The gate measures what matters: how long a preflighted GET issued now takes to come back.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable

# A queue-free preflighted GET comes back well inside this even on a loaded host; a queued one takes tens of seconds.
FAST_PROBE_MS = 3000
# One fast sample can land between two bursts, so the queue counts as drained only after several in a row.
FAST_PROBES_REQUIRED = 3
_PROBE_ABORT_MS = 50_000
_POLL_SEC = 0.5

_QUEUE_PROBE_JS = """(async () => {
  const started = performance.now();
  const settled = (extra) => ({
    ms: Math.round(performance.now() - started),
    complete: document.readyState === 'complete',
    ...extra,
  });
  try {
    const nonce = Math.random().toString(36).slice(2);
    // The JSON content type makes this a preflighted request, like every mutation the app sends.
    const response = await fetch(`${__API__}/api/v1/health/liveness?queue_probe=${nonce}`, {
      cache: 'no-store',
      credentials: 'omit',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(__ABORT_MS__),
    });
    await response.arrayBuffer();
    return settled({ ok: response.ok });
  } catch (error) {
    return settled({ ok: false, error: String(error).slice(0, 120) });
  }
})()"""


def api_queue_probe_js(api_url: str) -> str:
    """The page-side probe: one preflighted GET toward the API origin, timed from the page."""
    return _QUEUE_PROBE_JS.replace("__API__", json.dumps(api_url.rstrip("/"))).replace("__ABORT_MS__", str(_PROBE_ABORT_MS))


def _is_fast(probe: dict[str, object]) -> bool:
    ms = probe.get("ms")
    return probe.get("ok") is True and probe.get("complete") is True and isinstance(ms, int | float) and ms <= FAST_PROBE_MS


def _run_probe(evaluate: Callable[[str], object], api_url: str) -> dict[str, object]:
    """One probe; a page that cannot be evaluated right now (navigating, hot-reloading) is a failed probe."""
    try:
        result = evaluate(api_queue_probe_js(api_url))
    except (RuntimeError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": str(exc)[:120]}
    return result if isinstance(result, dict) else {"ok": False, "error": f"unexpected probe result {result!r}"[:120]}


def wait_for_api_queue_to_drain(
    evaluate: Callable[[str], object],
    api_url: str,
    *,
    deadline_sec: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Probe until ``FAST_PROBES_REQUIRED`` probes in a row came back fast on a completely loaded document.

    ``evaluate`` runs a page-side expression and returns its result. The outcome is ``drained`` or ``deadline``, with
    the probes taken, the seconds waited and the last probe.
    """
    started = clock()
    probes = 0
    streak = 0
    last: dict[str, object] = {}
    while clock() - started < deadline_sec:
        last = _run_probe(evaluate, api_url)
        probes += 1
        streak = streak + 1 if _is_fast(last) else 0
        if streak >= FAST_PROBES_REQUIRED:
            return {"outcome": "drained", "probes": probes, "waited_sec": round(clock() - started, 1), "last": last}
        sleep(_POLL_SEC)
    return {"outcome": "deadline", "probes": probes, "waited_sec": round(clock() - started, 1), "last": last}
