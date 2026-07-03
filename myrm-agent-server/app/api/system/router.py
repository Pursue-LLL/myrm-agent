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
from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.utils import get_local_ip
from pydantic import BaseModel

from app.config.settings import get_settings
from app.core.infra.ingress import get_public_ingress_base_url
from app.core.infra.ingress_requirement import resolve_ingress_requirement
from app.platform_utils.deployment_capabilities import get_deployment_capabilities
from app.platform_utils.sandbox.entitlements.entitlement_guard import EntitlementGuardError, require_public_ingress_entitlement

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
        SubdirUsage(name=name, bytes=_dir_size_bytes(data_dir / name))
        for name in subdir_names
        if (data_dir / name).exists()
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
