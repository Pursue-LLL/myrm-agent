import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.skill_optimization import AuditLogRepository, BatchTaskRepository
from app.api.skill_optimization.dependencies import get_storage
from app.database.connection import get_db
from app.database.models import BatchSnapshot
from app.services.skill_optimization.rollback_service import RollbackService
from app.services.skill_optimization.skill_version_sync import (
    load_skill_content_for_batch,
    restore_skill_snapshot,
)
from app.services.skill_optimization.time_estimator import TimeEstimator

"""Batch Optimization API Router

RESTful API endpoints for batch skill optimization management.
"""

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch-optimization", tags=["batch-optimization"])


def _int_from_payload(payload: dict[str, object], key: str, default: int = 0) -> int:
    v = payload.get(key, default)
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return default
    return default


class CreateBatchRequest(BaseModel):
    """Request body for creating a batch optimization task"""

    skill_ids: list[str]
    priority: int = 0
    max_concurrent: int = 3


class CancelBatchRequest(BaseModel):
    """Request body for cancelling a batch task"""

    cleanup_strategy: str = "keep"  # "keep" or "rollback"


@router.post("/tasks")
async def create_batch_task(
    request: CreateBatchRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Create a new batch optimization task

    Args:
        request: Batch task configuration
        db: Database session

    Returns:
        dict: Created batch task information
    """
    try:
        from app.core.infra.server_globals import get_optimization_scheduler
        from app.database.connection import get_session

        scheduler = get_optimization_scheduler()
        if not scheduler:
            raise HTTPException(status_code=503, detail="Optimization scheduler not available")

        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        storage = get_storage()
        rollback_service = RollbackService(db)

        async def batch_skill_reader(skill_id: str) -> tuple[str, int, dict[str, object]]:
            content = await load_skill_content_for_batch(skill_id)
            if content is None:
                raise ValueError(f"SKILL.md not found for skill {skill_id}")
            active = await storage.get_active_version(skill_id)
            version = active.version if active else 1
            return content, version, {}

        snapshot_ok = await rollback_service.create_batch_snapshot(
            batch_id=batch_id,
            skill_ids=request.skill_ids,
            skill_reader=batch_skill_reader,
        )
        if not snapshot_ok:
            raise HTTPException(status_code=500, detail="Failed to create batch snapshots before optimization")

        batch_id = await scheduler.trigger_batch_optimization(
            skill_ids=request.skill_ids,
            priority=request.priority,
            max_concurrent=request.max_concurrent,
            batch_task_id=batch_id,
        )

        batch_repo = BatchTaskRepository(db)
        estimator = TimeEstimator(db)

        estimation = await estimator.estimate_batch_time(request.skill_ids, request.max_concurrent)

        task = await batch_repo.create(
            batch_id=batch_id,
            skill_ids=request.skill_ids,
            priority=request.priority,
            max_concurrent=request.max_concurrent,
            user_id="sandbox",
        )

        audit_repo = AuditLogRepository(db)
        await audit_repo.create_log(
            batch_id=batch_id,
            operation="create",
            status="success",
            details={
                "skill_count": len(request.skill_ids),
                "priority": request.priority,
                "max_concurrent": request.max_concurrent,
            },
            user_id="sandbox",
        )

        async def on_progress(event: str, payload: dict[str, object]) -> None:
            """Handle batch optimization progress events"""
            if payload.get("batch_task_id") != batch_id:
                return

            async with get_session() as session:
                repo = BatchTaskRepository(session)
                await repo.update_progress(
                    batch_id=batch_id,
                    completed_tasks=_int_from_payload(payload, "completed", 0),
                    failed_tasks=_int_from_payload(payload, "failed", 0),
                )
                await session.commit()

        async def on_completed(event: str, payload: dict[str, object]) -> None:
            """Handle batch optimization completion events"""
            if payload.get("batch_task_id") != batch_id:
                return

            async with get_session() as session:
                repo = BatchTaskRepository(session)
                await repo.update_status(batch_id=batch_id, status="completed")
                await repo.update_progress(
                    batch_id=batch_id,
                    completed_tasks=_int_from_payload(payload, "succeeded", 0),
                    failed_tasks=_int_from_payload(payload, "failed", 0),
                )
                await session.commit()

        scheduler.event_emitter.on("batch_optimization_progress", on_progress)
        scheduler.event_emitter.on("batch_optimization_completed", on_completed)

        return {
            "batch_id": batch_id,
            "status": "pending",
            "total_tasks": task.total_tasks,
            "estimated_seconds": estimation.estimated_seconds,
            "estimated_completion": estimation.estimated_completion.isoformat(),
            "confidence": estimation.confidence_level,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create batch task: {e}")
        raise HTTPException(status_code=500, detail="Failed to create batch task") from e


@router.get("/tasks")
async def get_batch_tasks(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Get batch optimization tasks

    Args:
        status: Optional status filter
        limit: Maximum number of tasks to return
        db: Database session

    Returns:
        dict: List of batch tasks
    """
    try:
        batch_repo = BatchTaskRepository(db)

        if status:
            tasks = [t for t in await batch_repo.get_by_user("default", limit) if t.status == status]
        else:
            tasks = await batch_repo.get_by_user("default", limit)

        return {
            "tasks": [
                {
                    "batch_id": t.batch_id,
                    "status": t.status,
                    "priority": t.priority,
                    "max_concurrent": t.max_concurrent,
                    "skill_ids": t.skill_ids,
                    "total_tasks": t.total_tasks,
                    "completed_tasks": t.completed_tasks,
                    "failed_tasks": t.failed_tasks,
                    "cancelled_tasks": t.cancelled_tasks,
                    "total_execution_time": t.total_execution_time,
                    "total_token_consumption": t.total_token_consumption,
                    "estimated_completion_time": t.estimated_completion_time.isoformat() if t.estimated_completion_time else None,
                    "created_at": t.created_at.isoformat(),
                    "started_at": t.started_at.isoformat() if t.started_at else None,
                    "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                }
                for t in tasks
            ],
            "count": len(tasks),
        }

    except Exception as e:
        logger.error(f"Failed to get batch tasks: {e}")
        raise HTTPException(status_code=500, detail="Failed to get batch tasks") from e


@router.get("/tasks/{batch_id}")
async def get_batch_task(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Get a specific batch optimization task

    Args:
        batch_id: Batch task ID
        db: Database session

    Returns:
        dict: Batch task details
    """
    try:
        batch_repo = BatchTaskRepository(db)
        task = await batch_repo.get_by_id(batch_id)

        if not task:
            raise HTTPException(status_code=404, detail="Batch task not found")

        audit_repo = AuditLogRepository(db)
        audit_logs = await audit_repo.get_batch_logs(batch_id)

        return {
            "batch_id": task.batch_id,
            "status": task.status,
            "priority": task.priority,
            "max_concurrent": task.max_concurrent,
            "skill_ids": task.skill_ids,
            "total_tasks": task.total_tasks,
            "completed_tasks": task.completed_tasks,
            "failed_tasks": task.failed_tasks,
            "cancelled_tasks": task.cancelled_tasks,
            "total_execution_time": task.total_execution_time,
            "total_token_consumption": task.total_token_consumption,
            "estimated_completion_time": task.estimated_completion_time.isoformat() if task.estimated_completion_time else None,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "error_message": task.error_message,
            "audit_logs": [
                {
                    "operation": log.operation,
                    "status": log.status,
                    "details": log.details,
                    "created_at": log.created_at.isoformat(),
                }
                for log in audit_logs
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get batch task {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get batch task") from e


@router.post("/tasks/{batch_id}/cancel")
async def cancel_batch_task(
    batch_id: str,
    request: CancelBatchRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Cancel a batch optimization task

    Args:
        batch_id: Batch task ID
        request: Cancel configuration (cleanup strategy)
        db: Database session

    Returns:
        dict: Cancellation result
    """
    try:
        batch_repo = BatchTaskRepository(db)
        task = await batch_repo.get_by_id(batch_id)

        if not task:
            raise HTTPException(status_code=404, detail="Batch task not found")

        if task.status not in ["pending", "running"]:
            raise HTTPException(status_code=400, detail="Can only cancel pending or running tasks")

        from app.core.infra.server_globals import get_optimization_scheduler

        scheduler = get_optimization_scheduler()
        if scheduler:
            await scheduler.cancel_batch_optimization(batch_id)

        await batch_repo.update_status(batch_id, "cancelled")

        rollback_performed = False
        rollback_total_skills = 0
        rollback_rolled_back = 0
        rollback_failed = 0
        rollback_error_message: str | None = None
        if request.cleanup_strategy == "rollback":
            snap_result = await db.execute(select(BatchSnapshot).where(BatchSnapshot.batch_id == batch_id))
            snapshots = list(snap_result.scalars().all())
            if snapshots:
                rollback_service = RollbackService(db)
                storage = get_storage()

                async def skill_writer(skill_id: str, content: str, version: int) -> None:
                    await restore_skill_snapshot(storage, skill_id, content, version)
                    logger.info("Rolled back skill %s to version %s", skill_id, version)

                rollback_result = await rollback_service.rollback_batch(batch_id, skill_writer)
                rollback_performed = rollback_result.success
                rollback_total_skills = rollback_result.total_skills
                rollback_rolled_back = rollback_result.rolled_back
                rollback_failed = rollback_result.failed
                rollback_error_message = rollback_result.error_message

        audit_repo = AuditLogRepository(db)
        await audit_repo.create_log(
            batch_id=batch_id,
            operation="cancel",
            status="success" if request.cleanup_strategy != "rollback" or rollback_performed else "failure",
            details={
                "cleanup_strategy": request.cleanup_strategy,
                "rollback_performed": rollback_performed,
                "total_skills": rollback_total_skills,
                "rolled_back": rollback_rolled_back,
                "failed": rollback_failed,
            },
            user_id="sandbox",
            error_message=rollback_error_message,
        )

        return {
            "batch_id": batch_id,
            "status": "cancelled",
            "cleanup_strategy": request.cleanup_strategy,
            "rollback_performed": rollback_performed,
            "total_skills": rollback_total_skills,
            "rolled_back": rollback_rolled_back,
            "failed": rollback_failed,
            "error_message": rollback_error_message,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel batch task {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel batch task") from e


@router.post("/tasks/{batch_id}/rollback")
async def rollback_batch_task(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Rollback a completed batch optimization task

    Args:
        batch_id: Batch task ID
        db: Database session

    Returns:
        dict: Rollback result
    """
    try:
        batch_repo = BatchTaskRepository(db)
        task = await batch_repo.get_by_id(batch_id)

        if not task:
            raise HTTPException(status_code=404, detail="Batch task not found")

        snap_result = await db.execute(select(BatchSnapshot).where(BatchSnapshot.batch_id == batch_id))
        snapshots = list(snap_result.scalars().all())

        if not snapshots:
            raise HTTPException(status_code=404, detail="No snapshots found for this batch")

        rollback_service = RollbackService(db)
        storage = get_storage()

        async def skill_writer(skill_id: str, content: str, version: int) -> None:
            await restore_skill_snapshot(storage, skill_id, content, version)
            logger.info("Rolled back skill %s to version %s", skill_id, version)

        rollback_result = await rollback_service.rollback_batch(batch_id, skill_writer)

        audit_repo = AuditLogRepository(db)
        await audit_repo.create_log(
            batch_id=batch_id,
            operation="rollback",
            status="success" if rollback_result.success else "failure",
            details={
                "total_skills": rollback_result.total_skills,
                "rolled_back": rollback_result.rolled_back,
                "failed": rollback_result.failed,
            },
            user_id="sandbox",
            error_message=rollback_result.error_message,
        )

        return {
            "batch_id": batch_id,
            "success": rollback_result.success,
            "total_skills": rollback_result.total_skills,
            "rolled_back": rollback_result.rolled_back,
            "failed": rollback_result.failed,
            "error_message": rollback_result.error_message,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rollback batch task {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to rollback batch task") from e


@router.post("/tasks/{batch_id}/retry-failed")
async def retry_failed_tasks(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Retry only the failed tasks in a batch

    Args:
        batch_id: Batch task ID
        db: AsyncSession

    Returns:
        dict: New batch task ID for retrying failed tasks
    """
    try:
        batch_repo = BatchTaskRepository(db)
        task = await batch_repo.get_by_id(batch_id)

        if not task:
            raise HTTPException(status_code=404, detail="Batch task not found")

        if task.failed_tasks == 0:
            raise HTTPException(status_code=400, detail="No failed tasks to retry")

        audit_repo = AuditLogRepository(db)
        logs = await audit_repo.get_batch_logs(batch_id)

        failed_skill_ids = []
        for log in logs:
            if log.status == "failure" and log.operation == "optimize":
                skill_id = log.details.get("skill_id")
                if skill_id:
                    failed_skill_ids.append(skill_id)

        if not failed_skill_ids:
            raise HTTPException(status_code=400, detail="No failed skills found in audit logs")

        estimator = TimeEstimator(db)
        new_batch_id = f"batch-retry-{uuid.uuid4().hex[:8]}"

        estimation = await estimator.estimate_batch_time(failed_skill_ids, task.max_concurrent)

        await batch_repo.create(
            batch_id=new_batch_id,
            skill_ids=failed_skill_ids,
            priority=task.priority + 1,
            max_concurrent=task.max_concurrent,
            user_id="sandbox",
        )

        await audit_repo.create_log(
            batch_id=new_batch_id,
            operation="retry",
            status="success",
            details={
                "original_batch_id": batch_id,
                "retry_count": len(failed_skill_ids),
            },
            user_id="sandbox",
        )

        from app.core.infra.server_globals import get_optimization_scheduler

        scheduler = get_optimization_scheduler()
        if scheduler:
            await scheduler.trigger_batch_optimization(
                skill_ids=failed_skill_ids,
                priority=task.priority + 1,
                max_concurrent=task.max_concurrent,
            )

        return {
            "new_batch_id": new_batch_id,
            "original_batch_id": batch_id,
            "retry_count": len(failed_skill_ids),
            "estimated_seconds": estimation.estimated_seconds,
            "status": "pending",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry failed tasks for batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retry failed tasks") from e
