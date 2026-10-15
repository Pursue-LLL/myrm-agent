"""Tell a React dev page that is still loading from one that is stuck, for the E2E bridge wait.

Hydrating a Next dev page on a loaded host takes minutes (every chunk is a slow request), far longer than the
bridge wait's heal reloads allow, and each reload restarts all of those downloads: reloading a page that is merely
slow guarantees it never finishes. The wait therefore leaves a loading page alone and heals only a settled or
stalled one.
"""

from __future__ import annotations

import time
from collections.abc import Callable

# Quiet period after ``readyState == complete`` that counts as "nothing is loading any more".
SETTLE_SEC = 3.0
# Quiet period in which no script finished and the document state did not move: the load is stuck, not slow.
STALL_SEC = 45.0
_POLL_SEC = 1.0


def _progress(probe: dict[str, object]) -> tuple[object, object, object]:
    """Signals that move while the page loads: document state, finished scripts, injected script tags."""
    return probe.get("readyState"), probe.get("scriptsDone"), probe.get("domScripts")


def wait_for_load_to_settle(
    read_probe: Callable[[], dict[str, object]],
    first_probe: dict[str, object],
    *,
    deadline: float,
    on_wait: Callable[[], None],
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Block while the page keeps loading; the returned outcome says why waiting ended.

    ``ready``: the bridge appeared. ``settled``: the document is complete and nothing moved for ``SETTLE_SEC``.
    ``stalled``: nothing moved for ``STALL_SEC``, which is when a heal reload helps. ``deadline``: out of time.
    ``unobservable``: the page could not be probed (it is navigating), so the caller's heal loop decides.
    """
    probe = first_probe
    progress = _progress(probe)
    changed_at = clock()
    while clock() < deadline:
        idle_sec = clock() - changed_at
        if probe.get("readyState") == "complete" and idle_sec >= SETTLE_SEC:
            return "settled"
        if idle_sec >= STALL_SEC:
            return "stalled"
        on_wait()
        sleep(_POLL_SEC)
        try:
            probe = read_probe()
        except Exception:  # noqa: BLE001 - a navigating page cannot be observed; the heal loop decides
            return "unobservable"
        if probe.get("ready") is True:
            return "ready"
        if (observed := _progress(probe)) != progress:
            progress, changed_at = observed, clock()
    return "deadline"
