"""System API routes for ingress, LAN, storage diagnostics, and OpenTelemetry posture.

[INPUT]
- app.api.system.schemas::IngressRequirementResponse, StorageInfoResponse, TelemetryPostureResponse (POS: System API Schemas)
- app.services.system.storage_service (POS: Storage Diagnostics Service)
- app.services.system.storage_layout::build_storage_layout (POS: where each storage category lives)
- myrm_agent_harness.infra.tracing::get_telemetry_posture (POS: OpenTelemetry Posture Probe)

[OUTPUT]
- get_system_telemetry_posture: GET /telemetry-posture SRE OpenTelemetry Posture Probe
- get_storage_info: GET /storage
- get_storage_governance_report: GET /storage/governance (space ledger of the whole data directory)
- optimize_storage: POST /storage/optimize
- get_ingress_requirement: GET /ingress/requirement

[POS]
HTTP route handlers for the System API layer.
"""

import asyncio
import logging
import shutil
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from myrm_agent_harness.utils import get_local_ip

from app.api.system.sandbox_recreate import router as sandbox_recreate_router
from app.api.system.schemas import (
    CreateSnapshotRequest,
    IngressRequirementResponse,
    PreUpdateSnapshotRequest,
    SnapshotActionResponse,
    StateSnapshotItem,
    StorageCategoryItem,
    StorageGovernanceReportResponse,
    StorageInfoResponse,
    StorageOptimizePreflightResponse,
    StorageOptimizeRequest,
    StorageOptimizeResponse,
    TelemetryPostureResponse,
)
from app.config.settings import get_settings
from app.core.infra.ingress import get_public_ingress_base_url
from app.core.infra.ingress_requirement import resolve_ingress_requirement
from app.platform_utils.sandbox.entitlements.entitlement_guard import (
    EntitlementGuardError,
    require_public_ingress_entitlement,
)
from app.services.instance_archive import (
    RestorePoint,
    RestorePointError,
    create_pre_update_point,
    create_restore_point,
    delete_restore_point,
    list_restore_points,
    stage_restore,
)
from app.services.instance_archive.policy import MAIN_DB_NAME
from app.services.instance_archive.schema_gate import current_schema_version
from app.services.system.storage_layout import build_storage_layout
from app.services.system.storage_service import (
    check_storage_preflight,
    execute_storage_optimization,
    get_sqlite_breakdown,
)

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(sandbox_recreate_router)


@router.get("/ingress-requirement", response_model=IngressRequirementResponse)
async def get_ingress_requirement() -> IngressRequirementResponse:
    """Whether public Ingress is needed given configured channels and cron webhooks."""
    snapshot = await resolve_ingress_requirement()
    return IngressRequirementResponse(
        required=snapshot.required,
        has_public_ingress=snapshot.has_public_ingress,
        reasons=list(snapshot.reasons),
        channels=dict(snapshot.channels),
    )


@router.get("/ingress-url")
async def get_ingress_url() -> dict[str, str]:
    """Get the computed public ingress base URL.

    Priority:
    1. CP_PUBLIC_INGRESS_URL (from SaaS Control Plane env injection)
    2. UserConfig.personalSettings.publicIngressBaseUrl (user-provided tunnel/proxy URL)
    3. Empty string (fallback to local generation in frontend)
    """
    try:
        require_public_ingress_entitlement()
    except EntitlementGuardError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    url = await get_public_ingress_base_url()
    return {"ingress_url": url}


@router.get("/local-network")
async def get_local_network(
    port: int = Query(3000, ge=1, le=65535, description="WebUI port for LAN URL"),
) -> dict[str, str]:
    """Return LAN URL for same-intranet access."""
    ip = get_local_ip()
    if not ip:
        return {"ip": "", "url": "", "hint": "Could not detect local IP"}
    return {"ip": ip, "url": f"http://{ip}:{port}", "hint": ""}


# ---------------------------------------------------------------------------
# Storage Info & Database Optimization
# ---------------------------------------------------------------------------


@router.get("/storage", response_model=StorageInfoResponse)
def get_storage_info() -> StorageInfoResponse:
    """Return disk usage info for the current data directory."""
    settings = get_settings()
    data_dir = Path(settings.database.state_dir)

    try:
        usage = shutil.disk_usage(data_dir if data_dir.exists() else data_dir.parent)
    except OSError:
        usage = shutil.disk_usage(Path.home())

    return StorageInfoResponse(
        data_dir=str(data_dir),
        disk_total_bytes=usage.total,
        disk_used_bytes=usage.used,
        disk_free_bytes=usage.free,
        db_breakdown=get_sqlite_breakdown(data_dir),
    )


@router.post("/storage/optimize-preflight", response_model=StorageOptimizePreflightResponse)
def optimize_storage_preflight() -> StorageOptimizePreflightResponse:
    """Pre-check disk headroom, database sizes, and active background jobs before optimization."""
    settings = get_settings()
    data_dir = Path(settings.database.state_dir)
    preflight = check_storage_preflight(data_dir)
    return StorageOptimizePreflightResponse(
        data_dir=preflight.data_dir,
        db_breakdown=preflight.db_breakdown,
        disk_free_bytes=preflight.disk_free_bytes,
        can_deep_optimize=preflight.can_deep_optimize,
        recommended_mode=preflight.recommended_mode,
        active_background_jobs=preflight.active_background_jobs,
        is_safe_to_optimize=preflight.is_safe_to_optimize,
        reason=preflight.reason,
    )


@router.post("/storage/optimize", response_model=StorageOptimizeResponse)
async def optimize_storage(request: StorageOptimizeRequest) -> StorageOptimizeResponse:
    """Execute session database optimization and disk reclamation."""
    mode = request.mode.strip().lower()
    if mode not in ("deep", "light"):
        raise HTTPException(
            status_code=400,
            detail="Invalid optimization mode. Must be 'deep' or 'light'.",
        )

    from myrm_agent_harness.api.hooks import count_running_background_shell_jobs

    active_jobs = count_running_background_shell_jobs()
    if active_jobs > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot optimize database while {active_jobs} background job(s) are active.",
        )

    settings = get_settings()
    data_dir = Path(settings.database.state_dir)
    if not (data_dir / "data.db").exists():
        return StorageOptimizeResponse(
            status="ok",
            mode=mode,
            before_bytes=0,
            after_bytes=0,
            reclaimed_bytes=0,
            reclaimed_percentage=0.0,
            backup_path=None,
            duration_ms=0,
            message="No database file exists to optimize.",
        )

    t0 = time.perf_counter()
    try:
        before_bytes, after_bytes, backup_path = await asyncio.to_thread(
            execute_storage_optimization,
            data_dir,
            mode,
            request.create_backup,
        )
    except sqlite3.OperationalError as exc:
        logger.error("Storage optimization failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database optimization failed: {exc}") from exc

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    reclaimed = max(0, before_bytes - after_bytes)
    pct = round((reclaimed / before_bytes * 100), 2) if before_bytes > 0 else 0.0

    msg = (
        f"Reclaimed {reclaimed} bytes ({pct}%) in {elapsed_ms}ms"
        if reclaimed > 0
        else f"Database already optimized; 0 bytes reclaimed ({elapsed_ms}ms)"
    )

    return StorageOptimizeResponse(
        status="ok",
        mode=mode,
        before_bytes=before_bytes,
        after_bytes=after_bytes,
        reclaimed_bytes=reclaimed,
        reclaimed_percentage=pct,
        backup_path=backup_path,
        duration_ms=elapsed_ms,
        message=msg,
    )


# ---------------------------------------------------------------------------
# Support Debug Bundle Export
# ---------------------------------------------------------------------------


@router.get("/debug-bundle")
async def export_support_debug_bundle(
    include_traces: bool = Query(True, description="Include recent redacted session event traces"),
    include_profiles: bool = Query(True, description="Include sanitized active agent profile metadata"),
) -> Response:
    """Generate and download a self-contained, fully redacted diagnostic ZIP bundle for support."""
    from datetime import datetime, timezone

    from app.services.system.support_bundle_service import SupportBundleService

    try:
        zip_bytes = await SupportBundleService.build_bundle_zip(
            include_traces=include_traces,
            include_profiles=include_profiles,
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"myrm-support-debug-{timestamp}.zip"

        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Bundle-Version": "1.0.0",
            },
        )
    except Exception as exc:
        logger.error("Failed to generate support debug bundle: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate support debug bundle") from exc


# ---------------------------------------------------------------------------
# Storage Governance & Restore Points
# ---------------------------------------------------------------------------


@router.get("/storage/governance", response_model=StorageGovernanceReportResponse)
def get_storage_governance_report() -> StorageGovernanceReportResponse:
    """Return the space ledger of the instance's persistent state, by category, with its restore points."""
    from myrm_agent_harness.observability.storage_governance import StorageGovernanceInspector

    settings = get_settings()
    data_dir = Path(settings.database.state_dir)
    snapshots = [point.to_metadata() for point in list_restore_points(data_dir)]
    inspector = StorageGovernanceInspector(data_dir, layout=build_storage_layout(settings.database))
    report = inspector.inspect(snapshots=snapshots)

    return StorageGovernanceReportResponse(
        total_storage_bytes=report.total_storage_bytes,
        disk_total_bytes=report.disk_total_bytes,
        disk_free_bytes=report.disk_free_bytes,
        disk_used_percentage=report.disk_used_percentage,
        categories=[
            StorageCategoryItem(
                category=c.category.value,
                bytes=c.bytes,
                item_count=c.item_count,
                percentage=c.percentage,
            )
            for c in report.categories
        ],
        snapshots=[
            StateSnapshotItem(
                snapshot_id=s.snapshot_id,
                label=s.label,
                size_bytes=s.size_bytes,
                created_at=s.created_at,
                checksum=s.checksum,
                file_count=s.file_count,
            )
            for s in report.snapshots
        ],
        generated_at=report.generated_at,
    )


def _restore_point_error(exc: RestorePointError) -> HTTPException:
    status = {"unknown_restore_point": 404, "operation_pending": 409, "insufficient_space": 507}.get(exc.code, 400)
    return HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)})


def _snapshot_item(point: RestorePoint) -> StateSnapshotItem:
    return StateSnapshotItem(
        snapshot_id=point.snapshot_id,
        label=point.label,
        size_bytes=point.size_bytes,
        created_at=point.created_at,
        checksum="",
        file_count=len(point.files),
    )


@router.post("/storage/snapshots", response_model=SnapshotActionResponse)
def create_state_snapshot(req: CreateSnapshotRequest) -> SnapshotActionResponse:
    """Create a restore point (page-consistent online copy of the databases)."""
    try:
        point = create_restore_point(Path(get_settings().database.state_dir), req.label)
    except RestorePointError as exc:
        raise _restore_point_error(exc) from exc
    return SnapshotActionResponse(
        success=True,
        message=f"Snapshot '{point.snapshot_id}' created successfully.",
        snapshot=_snapshot_item(point),
    )


@router.post("/storage/snapshots/{snapshot_id}/restore", response_model=SnapshotActionResponse)
def restore_state_snapshot(snapshot_id: str) -> SnapshotActionResponse:
    """Queue a restore point for the next start; the live database is never written to."""
    settings = get_settings()
    try:
        stage_restore(Path(settings.database.state_dir), snapshot_id, max_schema_version=current_schema_version())
    except RestorePointError as exc:
        raise _restore_point_error(exc) from exc
    return SnapshotActionResponse(
        success=True,
        message=f"Snapshot '{snapshot_id}' will be restored on the next start.",
        requires_restart=True,
    )


@router.get("/telemetry-posture", response_model=TelemetryPostureResponse)
def get_system_telemetry_posture() -> TelemetryPostureResponse:
    """Return OpenTelemetry posture and active status for SRE diagnostics and Settings card."""
    try:
        from myrm_agent_harness.infra.tracing import get_telemetry_posture

        data = get_telemetry_posture()
        return TelemetryPostureResponse.model_validate(data)
    except Exception as exc:
        logger.warning("Failed to retrieve telemetry posture: %s", exc)
        return TelemetryPostureResponse(
            status="error",
            error=str(exc),
            initialized=False,
            has_sdk=False,
            protocol="unknown",
            headers_configured=False,
            local_trace_only=False,
        )


@router.delete("/storage/snapshots/{snapshot_id}", response_model=SnapshotActionResponse)
def delete_state_snapshot(snapshot_id: str) -> SnapshotActionResponse:
    """Permanently delete a restore point."""
    try:
        deleted = delete_restore_point(Path(get_settings().database.state_dir), snapshot_id)
    except RestorePointError as exc:
        raise _restore_point_error(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail={"code": "unknown_restore_point", "message": "Unknown restore point"})
    return SnapshotActionResponse(success=True, message=f"Snapshot '{snapshot_id}' deleted successfully.")


@router.get("/storage/snapshots")
def list_update_snapshots() -> dict[str, object]:
    """Newest-first restore point inventory for the Stack Update Panel."""
    points = list_restore_points(Path(get_settings().database.state_dir))
    return {
        "snapshots": [
            {
                "snapshot_id": point.snapshot_id,
                "label": point.label,
                "size_bytes": point.size_bytes,
                "created_at": point.created_at,
                "from_version": point.from_version,
                "to_version": point.to_version,
                "extra_files": [name for name in point.files if name != MAIN_DB_NAME],
            }
            for point in points
        ]
    }


@router.post("/storage/snapshots/pre-update")
def create_pre_update_snapshot(req: PreUpdateSnapshotRequest) -> dict[str, object]:
    """Restore point before an update install, then enforce retention."""
    if not req.from_version.strip() or not req.to_version.strip():
        raise HTTPException(status_code=400, detail="from_version and to_version are required.")
    try:
        point = create_pre_update_point(
            Path(get_settings().database.state_dir),
            from_version=req.from_version.strip(),
            to_version=req.to_version.strip(),
            keep_latest=max(1, req.keep_latest),
        )
    except RestorePointError as exc:
        raise _restore_point_error(exc) from exc
    return {
        "snapshot_id": point.snapshot_id,
        "label": point.label,
        "size_bytes": point.size_bytes,
        "created_at": point.created_at,
        "from_version": point.from_version,
        "to_version": point.to_version,
    }
