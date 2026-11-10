"""[INPUT]
- app.server.warmup::run_async_warmup (POS: warmup of schedulers, browser pool, tokenizer, vector store)
- app.lifecycle::pause_orphaned_active_goals (POS: goal recovery after an unclean stop)
- app.lifecycle::start_kanban_dispatchers (POS: per-board kanban dispatchers)
- app.startup.gc_policy::settle_collection_after (POS: ends the boot GC pause)
- .startup (POS: boot housekeeping coroutines)

[OUTPUT]
- schedule_background_work

[POS]
Starts the boot's background tasks once uvicorn is accepting connections. They are CPU-heavy on the single event loop
(scheduler wiring, tokenizer and vector store warmup, the agent tool chain import, the kanban dispatchers' first
queries); started before the lifespan yields, their first synchronous slices would delay the socket bind, which
uvicorn performs only after startup completes. When they have all ended, the boot GC pause ends with them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

from app.lifecycle import pause_orphaned_active_goals, start_kanban_dispatchers
from app.server.warmup import run_async_warmup
from app.startup.gc_policy import settle_collection_after

from . import startup
from .state import logger

# Covers the few loop iterations between the lifespan yielding and uvicorn binding its socket.
BACKGROUND_START_DELAY_SECONDS = 0.25

# The loop keeps only weak references to tasks; a running background task must be held until it ends.
_running: set[asyncio.Task[None]] = set()


def schedule_background_work() -> None:
    """Start the background tasks shortly after the lifespan yields, i.e. once the socket is bound."""
    asyncio.get_running_loop().call_later(BACKGROUND_START_DELAY_SECONDS, _start_background_work)


def _start_background_work() -> None:
    logger.info("[Startup] Starting background warmup...")
    tasks = [
        _spawn(run_async_warmup()),
        _spawn(pause_orphaned_active_goals()),
        _spawn(start_kanban_dispatchers()),
        # Trigger-bound cron jobs ("@startup") fire on boot.
        _spawn(startup._dispatch_startup_event()),
        _spawn(startup._seed_trunk_templates()),
        # Registering server-layer tools imports the full agent tool chain; the first agent turn awaits the same
        # idempotent bootstrap.
        _spawn(startup._preload_agent_tool_layers()),
    ]
    settle_collection_after(asyncio.gather(*tasks, return_exceptions=True))


def _spawn(work: Coroutine[object, object, None]) -> asyncio.Task[None]:
    task = asyncio.create_task(work)
    _running.add(task)
    task.add_done_callback(_finish)
    return task


def _finish(task: asyncio.Task[None]) -> None:
    _running.discard(task)
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error("[Startup] Background task %s failed: %s", task.get_name(), error, exc_info=error)
