"""
@input: 依赖 app.core.infra.ingress 与 entitlement 模块、DatabaseSettings
@output: 对外提供公网 ingress 获取、Ingress 需求判定、存储信息、沙箱容器重建端点
@pos: HTTP 入口层的 System API

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

import logging
import shutil
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query, Response
from myrm_agent_harness.utils import get_local_ip
from pydantic import BaseModel

from app.config.settings import get_settings
from app.core.infra.ingress import get_public_ingress_base_url
from app.core.infra.ingress_requirement import resolve_ingress_requirement
from app.platform_utils.deployment_capabilities import get_deployment_capabilities
from app.platform_utils.sandbox.entitlements.entitlement_guard import (
    EntitlementGuardError,
    require_public_ingress_entitlement,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class IngressRequirementResponse(BaseModel):
    required: bool
    has_public_ingress: bool
    reasons: list[str]
    channels: dict[str, str]


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
# Storage Info
# ---------------------------------------------------------------------------


def _dir_size_bytes(path: Path) -> int:
    """Recursively sum file sizes under *path*. Returns 0 if path doesn't exist."""
    if not path.is_dir():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


class SubdirUsage(BaseModel):
    name: str
    bytes: int


class StorageInfoResponse(BaseModel):
    data_dir: str
    disk_total_bytes: int
    disk_used_bytes: int
    disk_free_bytes: int
    subdirs: list[SubdirUsage]


@router.get("/storage", response_model=StorageInfoResponse)
def get_storage_info() -> StorageInfoResponse:
    """Return disk usage info for the current data directory."""
    settings = get_settings()
    data_dir = Path(settings.database.state_dir)

    try:
        usage = shutil.disk_usage(data_dir if data_dir.exists() else data_dir.parent)
    except OSError:
        usage = shutil.disk_usage(Path.home())

    subdir_names = ["qdrant", "harness", "event_logs", "memory"]
    subdirs = [
        SubdirUsage(name=name, bytes=_dir_size_bytes(data_dir / name)) for name in subdir_names if (data_dir / name).exists()
    ]

    db_file = data_dir / "data.db"
    if db_file.exists():
        subdirs.insert(0, SubdirUsage(name="data.db", bytes=db_file.stat().st_size))

    return StorageInfoResponse(
        data_dir=str(data_dir),
        disk_total_bytes=usage.total,
        disk_used_bytes=usage.used,
        disk_free_bytes=usage.free,
        subdirs=subdirs,
    )


# ---------------------------------------------------------------------------
# Sandbox Container Recreate (SaaS only)
# ---------------------------------------------------------------------------


class SandboxRecreateResponse(BaseModel):
    status: str
    message: str


@router.post("/sandbox/recreate", response_model=SandboxRecreateResponse)
async def recreate_sandbox_container() -> SandboxRecreateResponse:
    """Trigger container recreation via the Control Plane.

    Preserves the persistent volume (workspace files) while resetting
    system-level state (global packages, OS config). SaaS mode only.

    The server process will terminate when the old container is destroyed,
    so this endpoint fires the CP request and returns immediately.
    """
    caps = get_deployment_capabilities()
    if not caps.is_sandbox_instance:
        raise HTTPException(
            status_code=403,
            detail="Container recreate is only available in sandbox mode",
        )

    settings = get_settings()
    cp_url = settings.control_plane.effective_url()
    sandbox_id = settings.control_plane.sandbox_id
    token = settings.control_plane.telemetry_token.get_secret_value()

    if not sandbox_id or not token:
        raise HTTPException(
            status_code=503,
            detail="Control plane connectivity not configured",
        )

    from myrm_agent_harness.api.hooks import count_running_background_shell_jobs

    running = count_running_background_shell_jobs()
    if running > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot recreate container while {running} background shell job(s) are still running. "
                "Cancel or wait for them to finish first."
            ),
        )

    recreate_url = f"{cp_url}/api/internal/sandboxes/{sandbox_id}/recreate"
    headers = {
        "X-Telemetry-Token": token,
        "X-Sandbox-Id": sandbox_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(recreate_url, headers=headers)

        if resp.status_code >= 400:
            logger.error(
                "CP recreate request failed: %s %s",
                resp.status_code,
                resp.text[:200],
            )
            raise HTTPException(
                status_code=502,
                detail=f"Control plane returned {resp.status_code}",
            )

        return SandboxRecreateResponse(
            status="accepted",
            message="Container recreation initiated. The environment will restart shortly.",
        )
    except httpx.HTTPError as exc:
        logger.error("CP recreate request error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to reach control plane",
        ) from exc


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
# Personal Data Sovereignty & Takeout Export
# ---------------------------------------------------------------------------


@router.get("/takeout")
async def export_personal_data_takeout(
    include_db: bool = Query(True, description="Include SQLite database consistent backup"),
    include_wiki: bool = Query(True, description="Include Wiki Markdown knowledge vault"),
    include_skills: bool = Query(True, description="Include custom and downloaded skills"),
    include_deliverables: bool = Query(True, description="Include final workspace deliverables and artifacts"),
) -> Response:
    """Generate and download a self-contained, portable Takeout ZIP of all user personal data assets."""
    from datetime import datetime, timezone

    from app.services.system.takeout_service import UserTakeoutService

    try:
        zip_bytes = await UserTakeoutService.build_takeout_zip(
            include_db=include_db,
            include_wiki=include_wiki,
            include_skills=include_skills,
            include_deliverables=include_deliverables,
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"myrm-takeout-{timestamp}.zip"

        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Takeout-Version": "1.0.0",
            },
        )
    except Exception as exc:
        logger.error("Failed to generate personal data takeout archive: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate personal data takeout archive") from exc



# ---------------------------------------------------------------------------
# Storage Governance & Compaction Suite
# ---------------------------------------------------------------------------


class StorageCategoryItem(BaseModel):
    category: str
    display_name: str
    bytes: int
    item_count: int
    percentage: float
    details: dict[str, int] = {}


class StateSnapshotItem(BaseModel):
    snapshot_id: str
    label: str
    size_bytes: int
    created_at: str
    checksum: str
    file_count: int


class StorageGovernanceReportResponse(BaseModel):
    total_storage_bytes: int
    disk_total_bytes: int
    disk_free_bytes: int
    disk_used_percentage: float
    categories: list[StorageCategoryItem]
    snapshots: list[StateSnapshotItem]
    recommended_actions: list[str]
    is_growth_healthy: bool
    generated_at: str


class StorageCompactionRequest(BaseModel):
    purge_orphan_checkpoints: bool = True
    incremental_pages: int = 500


class StorageCompactionResponse(BaseModel):
    success: bool
    initial_bytes: int
    final_bytes: int
    freed_bytes: int
    purged_checkpoints: int
    wal_truncated: bool
    duration_ms: float
    message: str


class CreateSnapshotRequest(BaseModel):
    label: str


class SnapshotActionResponse(BaseModel):
    success: bool
    message: str
    snapshot: StateSnapshotItem | None = None


@router.get("/storage/governance", response_model=StorageGovernanceReportResponse)
def get_storage_governance_report() -> StorageGovernanceReportResponse:
    """Return detailed multi-dimensional storage breakdown and governance insights."""
    from myrm_agent_harness.observability.storage_governance import (
        StateSnapshotManager,
        StorageGovernanceInspector,
    )

    settings = get_settings()
    data_dir = Path(settings.database.state_dir)
    snapshot_mgr = StateSnapshotManager(data_dir)
    snapshots = snapshot_mgr.list_snapshots()
    inspector = StorageGovernanceInspector(data_dir)
    report = inspector.inspect(snapshots=snapshots)

    return StorageGovernanceReportResponse(
        total_storage_bytes=report.total_storage_bytes,
        disk_total_bytes=report.disk_total_bytes,
        disk_free_bytes=report.disk_free_bytes,
        disk_used_percentage=report.disk_used_percentage,
        categories=[
            StorageCategoryItem(
                category=c.category.value,
                display_name=c.display_name,
                bytes=c.bytes,
                item_count=c.item_count,
                percentage=c.percentage,
                details=c.details,
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
        recommended_actions=report.recommended_actions,
        is_growth_healthy=report.is_growth_healthy,
        generated_at=report.generated_at,
    )


@router.post("/storage/compaction", response_model=StorageCompactionResponse)
def execute_storage_compaction(
    req: StorageCompactionRequest,
) -> StorageCompactionResponse:
    """Execute safe non-blocking storage compaction, incremental vacuum, and checkpoint pruning."""
    from myrm_agent_harness.observability.storage_governance import (
        StateStorageCompactor,
    )

    settings = get_settings()
    data_dir = Path(settings.database.state_dir)
    compactor = StateStorageCompactor(data_dir)
    result = compactor.compact(
        purge_orphan_checkpoints=req.purge_orphan_checkpoints,
        incremental_pages=req.incremental_pages,
    )

    return StorageCompactionResponse(
        success=result.success,
        initial_bytes=result.initial_bytes,
        final_bytes=result.final_bytes,
        freed_bytes=result.freed_bytes,
        purged_checkpoints=result.purged_checkpoints,
        wal_truncated=result.wal_truncated,
        duration_ms=result.duration_ms,
        message=result.message,
    )


@router.post("/storage/snapshots", response_model=SnapshotActionResponse)
def create_state_snapshot(req: CreateSnapshotRequest) -> SnapshotActionResponse:
    """Create an immutable point-in-time state snapshot."""
    from myrm_agent_harness.observability.storage_governance import StateSnapshotManager

    settings = get_settings()
    data_dir = Path(settings.database.state_dir)
    snapshot_mgr = StateSnapshotManager(data_dir)
    try:
        meta = snapshot_mgr.create_snapshot(label=req.label)
        return SnapshotActionResponse(
            success=True,
            message=f"Snapshot '{meta.snapshot_id}' created successfully.",
            snapshot=StateSnapshotItem(
                snapshot_id=meta.snapshot_id,
                label=meta.label,
                size_bytes=meta.size_bytes,
                created_at=meta.created_at,
                checksum=meta.checksum,
                file_count=meta.file_count,
            ),
        )
    except Exception as exc:
        logger.error("Failed to create snapshot: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to create snapshot: {exc}") from exc


@router.post("/storage/snapshots/{snapshot_id}/restore", response_model=SnapshotActionResponse)
def restore_state_snapshot(snapshot_id: str) -> SnapshotActionResponse:
    """Restore database state to a specific historical snapshot."""
    from myrm_agent_harness.observability.storage_governance import StateSnapshotManager

    settings = get_settings()
    data_dir = Path(settings.database.state_dir)
    snapshot_mgr = StateSnapshotManager(data_dir)
    success = snapshot_mgr.restore_snapshot(snapshot_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to restore snapshot '{snapshot_id}'.")
    return SnapshotActionResponse(
        success=True,
        message=f"State successfully restored from snapshot '{snapshot_id}'.",
    )


@router.delete("/storage/snapshots/{snapshot_id}", response_model=SnapshotActionResponse)
def delete_state_snapshot(snapshot_id: str) -> SnapshotActionResponse:
    """Permanently delete a state snapshot."""
    from myrm_agent_harness.observability.storage_governance import StateSnapshotManager

    settings = get_settings()
    data_dir = Path(settings.database.state_dir)
    snapshot_mgr = StateSnapshotManager(data_dir)
    success = snapshot_mgr.delete_snapshot(snapshot_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found.")
    return SnapshotActionResponse(
        success=True,
        message=f"Snapshot '{snapshot_id}' deleted successfully.",
    )
