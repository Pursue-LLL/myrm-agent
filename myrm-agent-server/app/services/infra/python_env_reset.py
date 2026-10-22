"""Deferred reset of the agent's shared Python environment.

The environment lives on the persistent volume and the running process caches its interpreter path, so removing
it while the process is alive leaves agent commands pointing at a missing interpreter. The reset is therefore
deferred: the request leaves a marker, and the next process start consumes it before any agent command can use
the environment. Any start inside the TTL consumes it, including the old container a rolled-back swap brings
back up: the user asked for a clean environment and that restart is the first chance to give it.

[INPUT]
- app.config.settings::get_settings (POS: state_dir, the persistent data root)
- myrm_agent_harness.api.hooks::discard_shared_venv (POS: shared Python environment reset)

[OUTPUT]
- request_python_env_reset: leave the marker for the next start (reports whether this call placed it)
- cancel_python_env_reset: withdraw it when the container swap it was placed for was not accepted
- apply_pending_python_env_reset: consume the marker at startup and reset the environment

[POS]
Cloud sandbox "reset environment" support. The marker sits in `locks/`, a runtime directory the instance archive
leaves out, so a backup never carries it to another instance.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

try:  # optional harness helper; degrade to "no shared venv to discard"
    from myrm_agent_harness.api.hooks import discard_shared_venv
except ImportError:  # pragma: no cover - optional harness capability
    discard_shared_venv = None

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# Longer than the control plane's container swap (its own marker lives 300 s). A marker older than this belongs to
# a reset that never completed; honouring it on some later restart would wipe packages the user did not just ask for.
_MARKER_TTL_SECONDS = 600


def _marker_path() -> Path:
    return Path(get_settings().database.state_dir) / "locks" / "python-env-reset"


def _marker_age_seconds(marker: Path) -> float | None:
    """Age of the marker, or None when there is none."""
    try:
        return time.time() - marker.stat().st_mtime
    except FileNotFoundError:
        return None


def request_python_env_reset() -> bool:
    """Record that the next start must rebuild the Python environment from scratch.

    A still-valid request is left as it is: it belongs to a swap that is already under way, and only the call that
    placed a request may withdraw it.

    Returns:
        True if this call placed the request.
    """
    marker = _marker_path()
    age_seconds = _marker_age_seconds(marker)
    if age_seconds is not None and age_seconds <= _MARKER_TTL_SECONDS:
        return False
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    return True


def cancel_python_env_reset() -> None:
    """Withdraw a pending reset request."""
    _marker_path().unlink(missing_ok=True)


def apply_pending_python_env_reset() -> bool:
    """Consume a pending reset request and remove the Python environment.

    The marker is deleted whether or not the removal succeeds, so a failure is never retried on later restarts.
    Blocking file I/O: call from a worker thread.

    Returns:
        True if an environment was removed.
    """
    marker = _marker_path()
    age_seconds = _marker_age_seconds(marker)
    if age_seconds is None:
        return False

    try:
        if age_seconds > _MARKER_TTL_SECONDS:
            logger.warning("Ignoring stale Python environment reset request (%.0f s old)", age_seconds)
            return False
        return discard_shared_venv()
    finally:
        marker.unlink(missing_ok=True)
