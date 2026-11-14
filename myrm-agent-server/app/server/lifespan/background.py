"""[INPUT]
- app.server.warmup::run_async_warmup (POS: warmup of schedulers, browser pool, tokenizer, vector store)
- app.lifecycle::pause_orphaned_active_goals (POS: goal recovery after an unclean stop)
- app.lifecycle::start_kanban_dispatchers (POS: per-board kanban dispatchers)
- app.startup.gc_policy::settle_collection_after (POS: ends the boot GC pause)
- .startup (POS: boot housekeeping coroutines)

[OUTPUT]
- schedule_background_work, start_warmup_after_first_screen, cancel_scheduled_background_work

[POS]
Starts the boot's background tasks once uvicorn is accepting connections, in two steps.
Recovery (orphaned goals paused after an unclean stop) starts right after the bind: the first screen reads that state.
The warm-up (scheduler wiring, tokenizer and vector store warmup, the agent tool chain import, the kanban dispatchers'
first queries, @startup events) is CPU-heavy on the single event loop and in import threads, so started while the first
screen loads it slows the requests that screen waits for. It starts shortly after the readiness route first reports the
database ready, which is when a client renders, or after a fallback delay when no client asks. When the warm-up tasks
have all ended, the boot GC pause ends with them. A shutdown that arrives before a start cancels it, so no scheduler is
started once components are stopping.
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
RECOVERY_DELAY_SECONDS = 0.25

# The first screen's requests follow the readiness response; this is how long they get before the warm-up starts.
FIRST_SCREEN_SETTLE_SECONDS = 2.0

# A server that no client polls for readiness still warms up.
WARMUP_FALLBACK_DELAY_SECONDS = 10.0

# The loop keeps only weak references to tasks; a running background task must be held until it ends.
_running: set[asyncio.Task[None]] = set()

# The starts that have not fired yet, held so that a shutdown can cancel them and the readiness route can bring the
# warm-up forward.
_recovery_timer: asyncio.TimerHandle | None = None
_warmup_timer: asyncio.TimerHandle | None = None


def schedule_background_work() -> None:
    """Called as the lifespan yields: recovery starts once the socket is bound, the warm-up after the first screen."""
    global _recovery_timer, _warmup_timer
    loop = asyncio.get_running_loop()
    _recovery_timer = loop.call_later(RECOVERY_DELAY_SECONDS, _start_recovery)
    _warmup_timer = loop.call_later(WARMUP_FALLBACK_DELAY_SECONDS, _start_warmup)


def start_warmup_after_first_screen() -> None:
    """Called when the readiness route reports the database ready: the warm-up starts once the first screen has loaded.

    The start only ever moves earlier, so clients that keep polling readiness cannot push it back.
    """
    global _warmup_timer
    if _warmup_timer is None:
        return
    loop = asyncio.get_running_loop()
    settled_at = loop.time() + FIRST_SCREEN_SETTLE_SECONDS
    if settled_at < _warmup_timer.when():
        _warmup_timer.cancel()
        _warmup_timer = loop.call_at(settled_at, _start_warmup)


def cancel_scheduled_background_work() -> None:
    """Called when the server shuts down: background work that has not started yet is not started."""
    global _recovery_timer, _warmup_timer
    for timer in (_recovery_timer, _warmup_timer):
        if timer is not None:
            timer.cancel()
    _recovery_timer = None
    _warmup_timer = None


def _start_recovery() -> None:
    global _recovery_timer
    _recovery_timer = None
    _spawn(pause_orphaned_active_goals())


def _start_warmup() -> None:
    global _warmup_timer
    _warmup_timer = None
    logger.info("[Startup] Starting background warmup...")
    tasks = [
        _spawn(run_async_warmup()),
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
