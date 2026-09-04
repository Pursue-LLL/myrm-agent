"""System shutdown and drain API — graceful sandbox recycle (control plane triggered).

[INPUT]
- app.lifecycle.harness_bridge::close_harness_resources
- app.services.agent.gateway::get_agent_gateway (POS: Agent 执行网关)

[OUTPUT]
- POST /shutdown: initiate graceful process exit
- POST /drain: begin draining (reject new turns, wait for in-flight)
- DELETE /drain: cancel drain and re-accept new turns

[POS]
HTTP shutdown/drain control. POST /drain lets CP pre-drain before sleep/destroy;
POST /shutdown drains then SIGTERM.
"""

from __future__ import annotations

import logging
import os
import signal

from fastapi import APIRouter, BackgroundTasks

logger = logging.getLogger(__name__)

router = APIRouter()


async def graceful_shutdown_task() -> None:
    """Execute graceful shutdown: drain active Agent turns, flush WAL, close resources, then SIGTERM."""
    logger.info("[GracefulShutdown] Starting graceful shutdown process...")

    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    logger.info(
        "[GracefulShutdown] Draining %d active Agent session(s)...",
        gateway.active_count,
    )
    await gateway.begin_drain()

    # Stage 2: Force WAL Checkpoint flush to disk to prevent torn writes
    try:
        from app.platform_utils import get_database_engine

        engine = get_database_engine()
        async with engine.begin() as conn:
            try:
                await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
                logger.info("[GracefulShutdown] WAL checkpoint TRUNCATE completed")
            except Exception:
                await conn.exec_driver_sql("PRAGMA wal_checkpoint(PASSIVE)")
                logger.info("[GracefulShutdown] WAL checkpoint PASSIVE fallback completed")
    except Exception as exc:
        logger.warning("[GracefulShutdown] Pre-shutdown WAL checkpoint skipped: %s", exc)

    logger.info("[GracefulShutdown] Closing Harness resources...")
    from app.lifecycle.harness_bridge import close_harness_resources

    await close_harness_resources()

    logger.info("[GracefulShutdown] Sending SIGTERM to self...")
    os.kill(os.getpid(), signal.SIGTERM)


@router.post("/shutdown", summary="Graceful shutdown")
async def shutdown(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Trigger graceful shutdown (returns immediately, shutdown runs in background)."""
    logger.warning("Graceful shutdown requested via API")
    background_tasks.add_task(graceful_shutdown_task)
    return {"status": "shutting_down", "message": "Graceful shutdown initiated"}


@router.post("/drain", summary="Begin drain")
async def begin_drain(background_tasks: BackgroundTasks) -> dict[str, object]:
    """Begin draining: reject new Agent turns, wait for in-flight to finish.

    Used by the control plane before sandbox sleep/destroy to ensure no
    active Agent turn is hard-cut. The caller can poll this endpoint (or
    ``/health/liveness``) until ``active_count`` reaches 0, then proceed.
    """
    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    if not gateway.is_draining:
        background_tasks.add_task(gateway.begin_drain)
        logger.info("[Drain] Drain initiated via API")
    return {
        "draining": True,
        "active_count": gateway.active_count,
    }


@router.delete("/drain", summary="Cancel drain")
async def cancel_drain() -> dict[str, object]:
    """Cancel an in-progress drain and re-accept new Agent turns.

    Idempotent: returns success even if no drain was active.
    """
    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    was_draining = gateway.cancel_drain()
    return {
        "draining": False,
        "was_draining": was_draining,
        "active_count": gateway.active_count,
    }
