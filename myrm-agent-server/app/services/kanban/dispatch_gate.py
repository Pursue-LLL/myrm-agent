"""Whether a kanban task could actually run right now.

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs (POS: User config snapshot, 30 s TTL cache.)
- app.core.channel_bridge.model_resolver::resolve_model_config (POS: Model config resolution; raises ConfigIncompleteError when nothing is configured.)

[OUTPUT]
- dispatch_allowed: True when the saved provider/model configuration can launch a task.

[POS]
Dispatch gate for the kanban dispatchers. A server with no provider configured cannot run a task, so
the dispatchers hold their READY tasks instead of claiming them and recording a failure per task on
every boot (a 390-task board produced 390 failure rows and ~78k log lines that way).

Only "no provider at all" blocks outright. A missing *default* model blocks only when some queued
task has no `model_override` of its own: a task that pins its model still resolves, so blocking
unconditionally there would hold back work that can run.

Every board's dispatcher asks this on each wake cycle, so the answer is memoised for a few seconds and
concurrent callers share one evaluation: hundreds of boards must not query the config table at once.
"""

from __future__ import annotations

import asyncio
import time
from weakref import WeakKeyDictionary

from myrm_agent_harness.api import ConfigIncompleteError
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)

# One evaluation per window, shared by every board. The underlying config snapshot has a 30 s TTL of
# its own, so a longer window here would only delay the first task of a freshly configured install.
_CACHE_TTL_SECONDS = 3.0
_cached: tuple[float, bool] | None = None
# A single-flight slot per event loop: an asyncio.Task belongs to the loop that created it, and this
# module is process-global (tests and background loops each run their own loop).
_inflight: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Task[bool]] = WeakKeyDictionary()

_PROVIDER_MISSING = "provider_not_configured"
_DEFAULT_MODEL_MISSING = "default_model_not_configured"


def reset_cache() -> None:
    """Drop the memoised answer (tests, and after a config write)."""
    global _cached
    _cached = None
    _inflight.clear()


async def _evaluate() -> bool:
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.model_resolver import resolve_model_config

    try:
        configs = await load_user_configs()
        resolve_model_config(configs.providers_dict)
    except ConfigIncompleteError as exc:
        if exc.error_code == _PROVIDER_MISSING:
            return False
        if exc.error_code == _DEFAULT_MODEL_MISSING:
            # A task that pins its own model resolves without a default (the runner passes the
            # override into the same resolver). Block only when some active task has no pin, which
            # is exactly the set the missing default would fail.
            return not await _unplanned_task_exists()
        return False
    except Exception as exc:  # noqa: BLE001 - a broken gate must not stop dispatch
        logger.warning("Kanban dispatch gate could not read the model configuration: %s", exc)
        return True
    return True


async def _unplanned_task_exists() -> bool:
    """True when an active queued task carries no `model_override` of its own."""
    from myrm_agent_harness.toolkits.kanban.types import TaskStatus
    from sqlalchemy import or_, select

    from app.database.connection import get_session
    from app.database.models.kanban import KanbanTaskModel

    active = (TaskStatus.TRIAGE.value, TaskStatus.BACKLOG.value, TaskStatus.READY.value)
    async with get_session() as session:
        found = (
            await session.execute(
                select(KanbanTaskModel.id)
                .where(
                    KanbanTaskModel.status.in_(active),
                    or_(
                        KanbanTaskModel.model_override.is_(None),
                        KanbanTaskModel.model_override == "",
                    ),
                )
                .limit(1)
            )
        ).first()
    return found is not None


async def _evaluate_and_store() -> bool:
    global _cached
    allowed = await _evaluate()
    _cached = (time.monotonic(), allowed)
    return allowed


async def dispatch_allowed() -> bool:
    """False only when the saved configuration has no provider at all.

    Any other outcome — including a gate that cannot read the configuration — allows dispatch: a
    broken check must not hide real tasks from the user.
    """
    cached = _cached
    if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    loop = asyncio.get_running_loop()
    inflight = _inflight.get(loop)
    if inflight is None:
        inflight = loop.create_task(_evaluate_and_store(), name="kanban-dispatch-gate")
        _inflight[loop] = inflight
        inflight.add_done_callback(lambda done, key=loop: _forget(key, done))
    return await asyncio.shield(inflight)


def _forget(loop: asyncio.AbstractEventLoop, task: asyncio.Task[bool]) -> None:
    if _inflight.get(loop) is task:
        del _inflight[loop]
