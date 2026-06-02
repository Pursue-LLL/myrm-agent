"""
@input: 依赖 app.config.settings.settings 获取网关配置，依赖 app.core.infra 的 Tunnel 控制
@output: 对外提供公网 ingress 获取、Gateway 健康探测代理和 Tunnel 生命周期控制端点
@pos: HTTP 入口层的 System API

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""
import httpx
from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.utils import get_local_ip
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.core.infra.ingress import get_public_ingress_base_url
from app.core.infra.tunnel import get_tunnel_manager
from app.core.infra.tunnel.manager import TunnelError, TunnelStatus
from app.platform_utils.sandbox.entitlements.entitlement_guard import EntitlementGuardError, require_public_ingress_entitlement

router = APIRouter()


class TunnelStartRequest(BaseModel):
    port: int = Field(..., ge=1, le=65535, description="WebUI port to expose via Quick Tunnel")
    password_protection_enabled: bool = Field(
        ...,
        description="Must be true — public tunnel requires WebUI password protection",
    )


class TunnelStatusResponse(BaseModel):
    running: bool
    url: str | None
    target_port: int | None
    ingress_synced: bool


def _to_tunnel_response(status: TunnelStatus) -> TunnelStatusResponse:
    return TunnelStatusResponse(
        running=status.running,
        url=status.url,
        target_port=status.target_port,
        ingress_synced=status.ingress_synced,
    )


class GatewayHealthRequest(BaseModel):
    gateway_token: str | None = Field(
        None,
        min_length=1,
        max_length=512,
        pattern=r"^[A-Za-z0-9_\-\.\~]+$",
        description="Unified Tool Gateway Token (PAT)"
    )


@router.post("/gateway/health")
async def get_gateway_health(
    body: GatewayHealthRequest,
) -> dict[str, object]:
    """Check health of the Unified Tool Gateway and available platforms."""
    gateway_token = body.gateway_token
    # Control Plane URL is required
    control_plane_url = settings.control_plane.effective_url()
    if not control_plane_url:
        return {
            "status": "error",
            "message": "Control Plane URL is not configured."
        }

    if not gateway_token:
        return {
            "status": "error",
            "message": "Gateway PAT token is required."
        }
        
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{control_plane_url}/v1/tool_relay/health",
                headers={"Authorization": f"Bearer {gateway_token}"},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        return {
            "status": "error",
            "message": f"Gateway returned error: {e.response.status_code}",
            "details": e.response.text
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to connect to Gateway: {str(e)}"
        }


@router.get("/ingress-url")
async def get_ingress_url() -> dict[str, str]:
    """Get the computed public ingress base URL.

    Priority:
    1. CP_PUBLIC_INGRESS_URL (from SaaS Control Plane env injection)
    2. Active Quick Tunnel runtime URL (when tunnel is running)
    3. UserConfig.personalSettings.publicIngressBaseUrl (from user configuration)
    4. Empty string (fallback to local generation in frontend)
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
    """Return LAN URL for same-intranet access (bypasses blocked Quick Tunnel domains)."""
    ip = get_local_ip()
    if not ip:
        return {"ip": "", "url": "", "hint": "Could not detect local IP"}
    return {"ip": ip, "url": f"http://{ip}:{port}", "hint": ""}


@router.get("/tunnel/status", response_model=TunnelStatusResponse)
async def get_tunnel_status() -> TunnelStatusResponse:
    """Return Quick Tunnel runtime status."""
    manager = get_tunnel_manager()
    status = await manager.get_status()
    return _to_tunnel_response(status)


@router.post("/tunnel/start", response_model=TunnelStatusResponse)
async def start_tunnel(body: TunnelStartRequest) -> TunnelStatusResponse:
    """Start a Cloudflare Quick Tunnel to the given WebUI port."""
    manager = get_tunnel_manager()
    try:
        status = await manager.start(
            body.port,
            password_protection_enabled=body.password_protection_enabled,
        )
    except TunnelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_tunnel_response(status)


@router.post("/tunnel/stop", response_model=TunnelStatusResponse)
async def stop_tunnel() -> TunnelStatusResponse:
    """Stop the active Quick Tunnel and restore the previous ingress URL."""
    manager = get_tunnel_manager()
    try:
        status = await manager.stop()
    except TunnelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_tunnel_response(status)
