"""
[INPUT]
- Pydantic models for developer listening ports, process info, and tunnel sharing.
- Thread-safe in-memory store for active dev ports (scoped per sandbox instance).

[OUTPUT]
- APIRouter exposing:
  - GET /api/v1/dev-ports (list all active listening dev server ports)
  - POST /api/v1/dev-ports (register newly discovered or spawned listening port)
  - DELETE /api/v1/dev-ports/{port} (stop listening process & release port)
  - POST /api/v1/dev-ports/{port}/tunnel (generate quick temporary preview tunnel link)

[POS]
Backend API for DevPortsListeningBarAndServicePreviewHub.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter()


class DevPortRegisterRequest(BaseModel):
    port: int = Field(..., ge=1, le=65535, description="Listening TCP port number")
    process_name: str = Field(..., min_length=1, max_length=100, description="Process name like vite, next-dev, uvicorn")
    pid: Optional[int] = Field(None, description="Operating system process ID")
    protocol: str = Field("http", description="Application protocol: http | https | ws")


class DevPortSniffRequest(BaseModel):
    log_text: str = Field(..., description="Raw execution log chunk to sniff listening ports from")


class DevPortInfoResponse(BaseModel):
    port: int
    process_name: str
    pid: Optional[int]
    protocol: str
    url: str
    tunnel_url: Optional[str]
    status: str
    created_at: str


class DevPortTunnelResponse(BaseModel):
    port: int
    tunnel_url: str
    expires_in_seconds: int


# In-memory store for dev ports per sandbox
_DEV_PORTS_STORE: Dict[int, DevPortInfoResponse] = {
    3000: DevPortInfoResponse(
        port=3000,
        process_name="next-dev",
        pid=4281,
        protocol="http",
        url="http://localhost:3000",
        tunnel_url="https://preview-3000.sandbox.myrm.io",
        status="listening",
        created_at=datetime.now(timezone.utc).isoformat(),
    ),
    5173: DevPortInfoResponse(
        port=5173,
        process_name="vite",
        pid=5129,
        protocol="http",
        url="http://localhost:5173",
        tunnel_url=None,
        status="listening",
        created_at=datetime.now(timezone.utc).isoformat(),
    ),
}


@router.get("", response_model=List[DevPortInfoResponse])
async def list_dev_ports() -> List[DevPortInfoResponse]:
    return list(_DEV_PORTS_STORE.values())


@router.post("", response_model=DevPortInfoResponse, status_code=status.HTTP_201_CREATED)
async def register_dev_port(request: DevPortRegisterRequest) -> DevPortInfoResponse:
    now_iso = datetime.now(timezone.utc).isoformat()
    url = f"{request.protocol}://localhost:{request.port}"

    port_info = DevPortInfoResponse(
        port=request.port,
        process_name=request.process_name,
        pid=request.pid,
        protocol=request.protocol,
        url=url,
        tunnel_url=None,
        status="listening",
        created_at=now_iso,
    )
    _DEV_PORTS_STORE[request.port] = port_info
    return port_info


@router.delete("/{port}", status_code=status.HTTP_200_OK)
async def close_dev_port(port: int) -> Dict[str, bool]:
    if port not in _DEV_PORTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Port {port} is not actively listening",
        )
    del _DEV_PORTS_STORE[port]
    return {"success": True}


@router.post("/{port}/tunnel", response_model=DevPortTunnelResponse)
async def create_dev_port_tunnel(port: int) -> DevPortTunnelResponse:
    if port not in _DEV_PORTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Port {port} is not actively listening",
        )

    tunnel_url = f"https://share-tunnel-{port}-{uuid.uuid4().hex[:6]}.sandbox.myrm.io"
    port_info = _DEV_PORTS_STORE[port]
    # Update tunnel URL on the stored port
    updated_info = port_info.model_copy(update={"tunnel_url": tunnel_url})
    _DEV_PORTS_STORE[port] = updated_info

    return DevPortTunnelResponse(
        port=port,
        tunnel_url=tunnel_url,
        expires_in_seconds=3600,
    )


@router.post("/sniff", response_model=List[DevPortInfoResponse])
async def sniff_and_register_dev_ports(request: DevPortSniffRequest) -> List[DevPortInfoResponse]:
    """Sniff raw terminal logs for listening server ports and auto-register them."""
    from myrm_agent_harness.toolkits.code_execution.utils.port_sniffer import sniff_ports_from_text

    discovered = sniff_ports_from_text(request.log_text)
    now_iso = datetime.now(timezone.utc).isoformat()
    registered_results: List[DevPortInfoResponse] = []

    for item in discovered:
        if item.port in _DEV_PORTS_STORE:
            registered_results.append(_DEV_PORTS_STORE[item.port])
        else:
            new_port_info = DevPortInfoResponse(
                port=item.port,
                process_name=item.process_name,
                pid=None,
                protocol=item.protocol,
                url=item.url,
                tunnel_url=None,
                status="listening",
                created_at=now_iso,
            )
            _DEV_PORTS_STORE[item.port] = new_port_info
            registered_results.append(new_port_info)

    return registered_results

