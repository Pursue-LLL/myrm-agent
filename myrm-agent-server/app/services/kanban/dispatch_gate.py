"""Whether a kanban task could actually run right now.

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs (POS: User config snapshot, 30 s TTL cache.)
- app.core.channel_bridge.model_resolver::resolve_model_config (POS: Model config resolution; raises ConfigIncompleteError when nothing is configured.)

[OUTPUT]
- dispatch_allowed: True when the saved provider/model configuration can launch a task.

[POS]
Dispatch gate for the kanban dispatchers. A server without a usable model configuration cannot run a
task, so the dispatchers hold their READY tasks instead of claiming them and recording a failure per
task on every boot (a 390-task board produced 390 failure rows and ~78k log lines that way).
"""

from __future__ import annotations

import asyncio
import time

from myrm_agent_harness.api import ConfigIncompleteError
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)

# One evaluation per window, shared by every board. The underlying config snapshot has a 30 s TTL of
# its own, so a longer window here would only delay the first task of a freshly configured install.
_CACHE_TTL_SECONDS = 3.0
_cached: tuple[float, bool] | None = None
_lock: asyncio.Lock | None = None


def _shared_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def reset_cache() -> None:
    """Drop the memoised answer (tests, and after a config write)."""
    global _cached
    _cached = None


async def _evaluate() -> bool:
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.model_resolver import resolve_model_config

    try:
        configs = await load_user_configs()
        resolve_model_config(configs.providers_dict)
    except ConfigIncompleteError:
        return False
    except Exception as exc:  # noqa: BLE001 - a broken gate must not stop dispatch
        logger.warning("Kanban dispatch gate could not read the model configuration: %s", exc)
        return True
    return True


async def dispatch_allowed() -> bool:
    """True unless the saved configuration is definitively missing a model.

    Fails open: only a ``ConfigIncompleteError`` (no provider, or no default model) blocks dispatch.
    Any other error means the check itself is broken, and holding work back on a broken check would
    hide real tasks from the user.
    """
    global _cached
    cached = _cached
    if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    async with _shared_lock():
        cached = _cached
        if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
        allowed = await _evaluate()
        _cached = (time.monotonic(), allowed)
        return allowed
