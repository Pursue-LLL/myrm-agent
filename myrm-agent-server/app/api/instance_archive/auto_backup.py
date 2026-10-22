"""Scheduled whole-instance backup API.

[INPUT]
- app.services.instance_archive.auto_backup (POS: settings, state, background runs)
- app.api.instance_archive.schemas (POS: wire contracts)

[OUTPUT]
- GET /auto-backup: settings, last outcome, whether the folder can be read, stored backups
- PUT /auto-backup: save settings (turning on or changing the folder backs up right away if due)
- POST /auto-backup/run: back up now in the background

[POS]
Thin HTTP layer mounted under ``/instance-archive`` by ``router.py``. Where scheduled
backups are not offered (cloud sandbox, nonstandard layout) GET answers
``supported: false`` and the writers answer 409, so the UI can hide the card without
guessing. Failures carry only stable ``code`` values; wording lives in the frontend.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.instance_archive.schemas import (
    AutoBackupResponse,
    AutoBackupSettingsRequest,
    BackupFileResponse,
)
from app.services.instance_archive import ExportBusyError
from app.services.instance_archive.auto_backup import (
    AutoBackupError,
    AutoBackupService,
    AutoBackupSettings,
    AutoBackupView,
    Frequency,
    get_auto_backup_service,
)

router = APIRouter()


def _require_service() -> AutoBackupService:
    service = get_auto_backup_service()
    if service is None:
        raise HTTPException(status_code=409, detail={"code": "unsupported_layout", "message": "Not available here"})
    return service


def _response(view: AutoBackupView) -> AutoBackupResponse:
    settings, state, last = view.settings, view.state, view.last
    return AutoBackupResponse(
        supported=True,
        enabled=settings.enabled,
        frequency=settings.frequency.value,
        keep=settings.keep,
        directory=str(view.directory),
        default_directory=settings.directory is None,
        folder_available=view.reachable,
        running=view.running,
        overdue=view.overdue,
        last_success_at=last.created_at.isoformat() if last else None,
        last_success_size=last.size_bytes if last else None,
        consecutive_failures=state.consecutive_failures,
        last_error_code=state.last_error_code,
        backups=[
            BackupFileResponse(name=b.name, created_at=b.created_at.isoformat(), size_bytes=b.size_bytes) for b in view.backups
        ],
    )


def _refused(exc: AutoBackupError | ExportBusyError) -> HTTPException:
    if isinstance(exc, ExportBusyError):
        return HTTPException(status_code=409, detail={"code": "export_busy", "message": str(exc)})
    return HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@router.get("", response_model=AutoBackupResponse)
async def get_auto_backup() -> AutoBackupResponse:
    service = get_auto_backup_service()
    if service is None:
        return AutoBackupResponse(supported=False)
    return _response(await service.get_view())


@router.put("", response_model=AutoBackupResponse)
async def put_auto_backup(body: AutoBackupSettingsRequest) -> AutoBackupResponse:
    service = _require_service()
    settings = AutoBackupSettings(
        enabled=body.enabled, frequency=Frequency(body.frequency), keep=body.keep, directory=body.directory
    )
    try:
        return _response(await service.apply(settings))
    except AutoBackupError as exc:
        raise _refused(exc) from exc


@router.post("/run", response_model=AutoBackupResponse)
async def run_auto_backup() -> AutoBackupResponse:
    service = _require_service()
    try:
        await service.start_run()
    except (AutoBackupError, ExportBusyError) as exc:
        raise _refused(exc) from exc
    return _response(await service.get_view())
