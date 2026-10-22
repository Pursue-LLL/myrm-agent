"""Instance archive API: export, chunked import, one-time outcome and rollback.

[INPUT]
- app.services.instance_archive (POS: export jobs, importer, upload store, swap queue)
- app.services.config.encryption::get_encryption_service (POS: config key, local mode only)
- app.api.instance_archive.auto_backup (POS: scheduled backup endpoints mounted at /auto-backup)

[OUTPUT]
- GET /status, GET /outcome, POST /outcome/acknowledge, POST /rollback
- POST /exports, GET|DELETE /exports/{id}, GET /exports/{id}/download
- POST /imports, PUT /imports/{id}/chunks/{index}, GET|DELETE /imports/{id},
  POST /imports/{id}/stage, POST /imports/{id}/confirm
- /auto-backup/*: scheduled backup (see auto_backup.py)

[POS]
Thin HTTP layer. Heavy work runs in worker threads (export) or ``to_thread``
(chunk write / verify / stage). Pair tokens are default-denied: these paths are
not on the mobile allow-list, so only the owner identity reaches them.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.instance_archive.auto_backup import router as auto_backup_router
from app.api.instance_archive.schemas import (
    ArchiveStatusResponse,
    ConfirmImportRequest,
    CreateUploadRequest,
    ExportJobResponse,
    OutcomeEnvelope,
    OutcomeResponse,
    QueuedSwapResponse,
    StageImportRequest,
    StartExportRequest,
    UploadSessionResponse,
)
from app.config.deploy_mode import get_deploy_mode, is_local_mode, is_sandbox
from app.config.settings import get_settings
from app.services.config.encryption import get_encryption_service
from app.services.instance_archive import (
    ArchivePaths,
    ExportBusyError,
    ExportJob,
    ImportEnvironment,
    ImportRejectedError,
    InstanceImporter,
    PendingPromotion,
    RestorePointError,
    UploadError,
    UploadSession,
    UploadStore,
    acknowledge_outcome,
    get_export_manager,
    latest_aside,
    prepare_rollback,
    read_outcome,
)
from app.services.instance_archive.policy import is_standard_layout
from app.services.instance_archive.schema_gate import current_schema_version

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(auto_backup_router, prefix="/auto-backup")

_STATUS_BY_CODE = {
    "unknown_session": 404,
    "unknown_restore_point": 404,
    "operation_pending": 409,
    "not_staged": 409,
    "not_uploading": 409,
    "upload_incomplete": 409,
    "acknowledgement_required": 409,
    "insufficient_space": 507,
}


def _paths() -> ArchivePaths:
    return ArchivePaths(Path(get_settings().database.state_dir))


def _standard_layout(paths: ArchivePaths) -> bool:
    return is_standard_layout(paths.state_dir, Path(get_settings().database.sqlite_path))


def _require_supported() -> ArchivePaths:
    paths = _paths()
    if not _standard_layout(paths):
        raise HTTPException(status_code=409, detail={"code": "unsupported_layout", "message": "Unsupported layout"})
    return paths


def _fail(exc: ImportRejectedError | UploadError | RestorePointError | ExportBusyError) -> HTTPException:
    code = "export_busy" if isinstance(exc, ExportBusyError) else exc.code
    return HTTPException(
        status_code=409 if isinstance(exc, ExportBusyError) else _STATUS_BY_CODE.get(code, 400),
        detail={"code": code, "message": str(exc)},
    )


def _importer(paths: ArchivePaths, request: Request) -> tuple[InstanceImporter, UploadStore]:
    service = get_encryption_service()
    env = ImportEnvironment(
        paths=paths,
        user_id=str(request.state.user_id),
        max_schema_version=current_schema_version(),
        target_key=service.raw_key if is_local_mode() else None,
    )
    store = UploadStore(paths)
    return InstanceImporter(env, store), store


def _session_response(session: UploadSession) -> UploadSessionResponse:
    return UploadSessionResponse(
        session_id=session.session_id,
        size_bytes=session.size_bytes,
        chunk_bytes=session.chunk_bytes,
        chunk_count=session.chunk_count,
        received=sorted(session.received),
        state=session.state,
        report=session.report,
    )


def _job_response(job: ExportJob) -> ExportJobResponse:
    progress, result = job.progress, job.result
    return ExportJobResponse(
        job_id=job.job_id,
        state=job.state.value,
        files_done=progress.files_done if progress else 0,
        files_total=progress.files_total if progress else 0,
        bytes_done=progress.bytes_done if progress else 0,
        bytes_total=progress.bytes_total if progress else 0,
        size_bytes=result.size_bytes if result else None,
        error_code=job.error_code,
        reentry=list(result.reentry) if result else [],
        config_key_carried=result.config_key_carried if result else False,
        unreadable_count=len(result.unreadable) if result else 0,
    )


def _queued(pending: PendingPromotion) -> QueuedSwapResponse:
    return QueuedSwapResponse(operation=pending.operation.value)


@router.get("/status", response_model=ArchiveStatusResponse)
def get_status() -> ArchiveStatusResponse:
    paths = _paths()
    pending = PendingPromotion.load(paths.pending)
    return ArchiveStatusResponse(
        supported=_standard_layout(paths),
        can_protect_secrets=is_local_mode() and get_encryption_service().has_key,
        restart_mode="sandbox" if is_sandbox() else "process",
        pending_operation=pending.operation.value if pending else None,
        rollback_available=latest_aside(paths.state_dir) is not None,
    )


@router.post("/exports", response_model=ExportJobResponse)
def start_export(body: StartExportRequest, request: Request) -> ExportJobResponse:
    paths = _require_supported()
    service = get_encryption_service()
    if body.passphrase and not (is_local_mode() and service.has_key):
        raise HTTPException(status_code=400, detail={"code": "secrets_unavailable", "message": "Not supported here"})
    try:
        job = get_export_manager(paths).start(
            user_id=str(request.state.user_id),
            app_version=get_settings().app_version,
            deploy_mode=get_deploy_mode().value,
            config_key=service.raw_key if body.passphrase else None,
            passphrase=body.passphrase,
        )
    except ExportBusyError as exc:
        raise _fail(exc) from exc
    return _job_response(job)


def _job_or_404(job_id: str) -> ExportJob:
    job = get_export_manager(_paths()).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_export", "message": "Unknown export"})
    return job


@router.get("/exports/{job_id}", response_model=ExportJobResponse)
def get_export(job_id: str) -> ExportJobResponse:
    return _job_response(_job_or_404(job_id))


@router.get("/exports/{job_id}/download")
def download_export(job_id: str) -> FileResponse:
    path = get_export_manager(_paths()).archive_path(_job_or_404(job_id))
    if path is None:
        raise HTTPException(status_code=409, detail={"code": "export_not_ready", "message": "Export is not ready"})
    return FileResponse(path, media_type="application/zip", filename=f"myrm-backup-{datetime.now():%Y%m%d-%H%M}.zip")


@router.delete("/exports/{job_id}", status_code=204)
def discard_export(job_id: str) -> None:
    manager = get_export_manager(_paths())
    manager.cancel(job_id)
    manager.discard(job_id)


@router.post("/imports", response_model=UploadSessionResponse)
async def create_import(body: CreateUploadRequest, request: Request) -> UploadSessionResponse:
    paths = _require_supported()
    _, store = _importer(paths, request)
    try:
        session = await asyncio.to_thread(store.create, body.size_bytes, body.chunk_bytes)
    except UploadError as exc:
        raise _fail(exc) from exc
    return _session_response(session)


@router.put("/imports/{session_id}/chunks/{index}", response_model=UploadSessionResponse)
async def upload_chunk(session_id: str, index: int, request: Request) -> UploadSessionResponse:
    _, store = _importer(_require_supported(), request)
    data = await request.body()
    try:
        session = await asyncio.to_thread(store.write_chunk, session_id, index, data)
    except UploadError as exc:
        raise _fail(exc) from exc
    return _session_response(session)


@router.get("/imports/{session_id}", response_model=UploadSessionResponse)
def get_import(session_id: str, request: Request) -> UploadSessionResponse:
    _, store = _importer(_require_supported(), request)
    try:
        return _session_response(store.get(session_id))
    except UploadError as exc:
        raise _fail(exc) from exc


@router.post("/imports/{session_id}/stage")
async def stage_import(session_id: str, body: StageImportRequest, request: Request) -> dict[str, object]:
    importer, _ = _importer(_require_supported(), request)
    try:
        report = await asyncio.to_thread(importer.stage, session_id, passphrase=body.passphrase, skip_secrets=body.skip_secrets)
    except (ImportRejectedError, UploadError) as exc:
        raise _fail(exc) from exc
    return report.to_dict()


@router.post("/imports/{session_id}/confirm", response_model=QueuedSwapResponse)
async def confirm_import(session_id: str, body: ConfirmImportRequest, request: Request) -> QueuedSwapResponse:
    importer, _ = _importer(_require_supported(), request)
    try:
        pending = await asyncio.to_thread(importer.confirm, session_id, acknowledge_executables=body.acknowledge_executables)
    except (ImportRejectedError, UploadError) as exc:
        raise _fail(exc) from exc
    return _queued(pending)


@router.delete("/imports/{session_id}", status_code=204)
async def cancel_import(session_id: str, request: Request) -> None:
    importer, _ = _importer(_require_supported(), request)
    try:
        await asyncio.to_thread(importer.cancel, session_id)
    except UploadError as exc:
        raise _fail(exc) from exc


@router.get("/outcome", response_model=OutcomeEnvelope)
def get_outcome() -> OutcomeEnvelope:
    outcome = read_outcome(_paths().state_dir)
    if outcome is None:
        return OutcomeEnvelope()
    return OutcomeEnvelope(
        outcome=OutcomeResponse(
            operation=outcome.operation.value,
            status=outcome.status.value,
            completed_at=outcome.completed_at,
            summary=outcome.summary,
            reentry=list(outcome.reentry),
            error_code=outcome.error_code,
            rollback_available=outcome.rollback_available,
        )
    )


@router.post("/outcome/acknowledge", status_code=204)
def acknowledge() -> None:
    acknowledge_outcome(_paths().state_dir)


@router.post("/rollback", response_model=QueuedSwapResponse)
def queue_rollback() -> QueuedSwapResponse:
    pending = prepare_rollback(_require_supported().state_dir)
    if pending is None:
        raise HTTPException(status_code=409, detail={"code": "nothing_to_undo", "message": "Nothing to undo"})
    return _queued(pending)


__all__ = ["router"]
