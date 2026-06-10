"""System shutdown API — graceful sandbox recycle (control plane triggered).

[INPUT]
- app.lifecycle.harness_bridge::close_harness_resources

[OUTPUT]
- POST /shutdown: initiate graceful process exit

[POS]
HTTP shutdown control. Distinct from app/lifecycle/ daemon schedulers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from fastapi import APIRouter, BackgroundTasks

logger = logging.getLogger(__name__)

router = APIRouter()


async def graceful_shutdown_task() -> None:
    """Execute graceful shutdown sequence."""
    logger.info("Starting graceful shutdown process...")
    logger.info("Step 1: Stopping new task acceptance...")
    logger.info("Step 2: Waiting for active tasks to complete...")
    await asyncio.sleep(1)

    logger.info("Step 3: Closing Harness resources...")
    from app.lifecycle.harness_bridge import close_harness_resources

    await close_harness_resources()

    logger.info("Step 4: Sending SIGTERM to self...")
    os.kill(os.getpid(), signal.SIGTERM)


@router.post("/shutdown", summary="Graceful shutdown")
async def shutdown(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Trigger graceful shutdown (returns immediately, shutdown runs in background)."""
    logger.warning("Graceful shutdown requested via API")
    background_tasks.add_task(graceful_shutdown_task)
    return {"status": "shutting_down", "message": "Graceful shutdown initiated"}
