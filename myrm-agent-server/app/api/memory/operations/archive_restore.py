"""Memory Archive restore operations.

[INPUT]
app.schemas.memory.archive::*ArchiveRestore* (POS: 记忆归档与导入 API Schema 层)
app.services.memory.archive_restore::MemoryArchiveRestoreService (POS: 单用户归档恢复服务)

[OUTPUT]
router: Myrm Memory Archive restore dry-run, confirm, rollback preview, and rollback endpoints.

[POS]
记忆归档恢复 API 操作层。只编排请求/响应和错误映射，恢复语义由服务层负责。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.memory.utils import get_crud_memory_manager
from app.database.connection import get_session
from app.schemas.memory.archive import (
    MemoryArchiveRestoreConfirmRequest,
    MemoryArchiveRestoreConfirmResponse,
    MemoryArchiveRestoreDryRunRequest,
    MemoryArchiveRestoreDryRunResponse,
    MemoryArchiveRestoreRollbackPreviewResponse,
    MemoryArchiveRestoreRollbackRequest,
    MemoryArchiveRestoreRollbackResponse,
)
from app.services.memory.archive_restore import MemoryArchiveRestoreService
from app.services.memory.archive_restore_common import MemoryArchiveRestoreError
from app.services.memory.command_center import MemoryCommandCenterService
from app.services.memory.diagnostics import MemoryDiagnosticsService

router = APIRouter(prefix="/archive/restore")
logger = logging.getLogger(__name__)


@router.post("/dry-run", response_model=MemoryArchiveRestoreDryRunResponse)
async def dry_run_archive_restore(body: MemoryArchiveRestoreDryRunRequest) -> MemoryArchiveRestoreDryRunResponse:
    """Preview a Myrm Memory Archive restore without writing state."""

    async with get_session() as db:
        try:
            result = await MemoryArchiveRestoreService(db).dry_run_restore(body.archive, sections=body.sections)
        except MemoryArchiveRestoreError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MemoryArchiveRestoreDryRunResponse(result=result)


@router.post("/confirm", response_model=MemoryArchiveRestoreConfirmResponse)
async def confirm_archive_restore(
    body: MemoryArchiveRestoreConfirmRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryArchiveRestoreConfirmResponse:
    """Execute a safe-merge Myrm Memory Archive restore."""

    async with get_session() as db:
        try:
            service = MemoryArchiveRestoreService(db)
            result = await service.restore_archive(
                body.archive,
                manager=manager,
                sections=body.sections,
                skip_duplicates=body.skip_duplicates,
                expected_payload_hash=body.payload_hash,
                expected_plan_hash=body.plan_hash,
            )
            try:
                snapshot = await MemoryCommandCenterService(db, manager).build_snapshot()
                diagnostic_run = await MemoryDiagnosticsService(db, manager).run_diagnostics(
                    health_cache_status=snapshot.health.cache_status,
                    runtime=snapshot.runtime,
                )
                await service.save_post_restore_diagnostic(
                    restore_batch_id=result.restore_batch_id,
                    diagnostic_run_id=diagnostic_run.id,
                    diagnostic_status=diagnostic_run.status,
                    failed_count=diagnostic_run.failed_count,
                )
                result.diagnostic_status = diagnostic_run.status
                result.diagnostic_run_id = diagnostic_run.id
                result.diagnostic_failed_count = diagnostic_run.failed_count
            except Exception as exc:
                logger.warning("Post-restore diagnostics failed for %s: %s", result.restore_batch_id, exc)
                diagnostic_status = "failed"
                diagnostic_run_id = "post-restore-diagnostic:failed"
                diagnostic_failed_count = 1
                result.diagnostic_status = diagnostic_status
                result.diagnostic_run_id = diagnostic_run_id
                result.diagnostic_failed_count = diagnostic_failed_count
                try:
                    await service.save_post_restore_diagnostic(
                        restore_batch_id=result.restore_batch_id,
                        diagnostic_run_id=diagnostic_run_id,
                        diagnostic_status=diagnostic_status,
                        failed_count=diagnostic_failed_count,
                    )
                except Exception as save_exc:
                    logger.warning("Post-restore diagnostic failure state was not persisted: %s", save_exc)
        except MemoryArchiveRestoreError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MemoryArchiveRestoreConfirmResponse(result=result)


@router.post("/rollback/dry-run", response_model=MemoryArchiveRestoreRollbackPreviewResponse)
async def dry_run_archive_restore_rollback(
    body: MemoryArchiveRestoreRollbackRequest,
) -> MemoryArchiveRestoreRollbackPreviewResponse:
    """Preview rollback impact for a confirmed archive restore batch."""

    async with get_session() as db:
        try:
            result = await MemoryArchiveRestoreService(db).preview_rollback(body.restore_batch_id)
        except MemoryArchiveRestoreError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MemoryArchiveRestoreRollbackPreviewResponse(result=result)


@router.post("/rollback", response_model=MemoryArchiveRestoreRollbackResponse)
async def rollback_archive_restore(
    body: MemoryArchiveRestoreRollbackRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryArchiveRestoreRollbackResponse:
    """Rollback a confirmed archive restore batch."""

    async with get_session() as db:
        try:
            result = await MemoryArchiveRestoreService(db).rollback_restore(body.restore_batch_id, manager=manager)
        except MemoryArchiveRestoreError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MemoryArchiveRestoreRollbackResponse(result=result)
