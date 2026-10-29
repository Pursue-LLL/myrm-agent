"""WebUI API aggregate router: og-metadata proxy, QR code, welcome page, browser snapshot.

[INPUT]
- auth_routes / vnc_routes / desktop_routes (POS: mounted sub-routers)
- welcome_page::render_welcome_page (POS: LAN start-up page)

[OUTPUT]
- router: APIRouter ``/webui`` carrying every WebUI endpoint

[POS]
Single mount point for ``app.main``; page and desktop-panel logic live in their own modules.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from myrm_agent_harness.utils import get_local_ip

from app.api.webui.auth_routes import router as webui_auth_router
from app.api.webui.desktop_routes import router as desktop_router
from app.api.webui.vnc_routes import router as vnc_router
from app.api.webui.welcome_page import render_welcome_page
from app.config.settings import settings
from app.services.webui.og_metadata import fetch_og_metadata
from app.services.webui.qrcode import generate_qrcode_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webui", tags=["webui"])
router.include_router(webui_auth_router)
router.include_router(vnc_router)
router.include_router(desktop_router)

# ``/welcome`` is served without login and writes the host into HTML and script, so only
# hostname and IP-literal characters are accepted (empty keeps the local-IP default).
HostParam = Annotated[
    str | None,
    Query(max_length=255, pattern=r"^[A-Za-z0-9._:\[\]-]*$", description="Hostname or IP literal"),
]


@router.get("/og-metadata")
async def get_og_metadata(url: str = Query(..., description="URL to fetch OG metadata for")) -> JSONResponse:
    """Proxy-fetch Open Graph metadata for a URL (solves CORS for WebUI embeds)."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    metadata = await fetch_og_metadata(url)
    return JSONResponse(content=metadata, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/qrcode.png")
async def get_qrcode_image_endpoint(
    host: HostParam = None,
    port: int | None = None,
    url: str | None = None,
) -> Response:
    """获取二维码图片（PNG）

    Args:
        host: 主机地址（可选，默认使用本机 IP）
        port: 端口（可选，默认使用配置的端口）
        url: 完整的 URL（可选，如果提供则优先使用）

    Returns:
        PNG 格式的二维码图片

    用于浏览器显示或下载。
    """
    try:
        if url:
            target_url = url
        else:
            # 使用提供的参数或默认值
            if not host:
                host = get_local_ip()
            if not port:
                port = settings.webui.port
            target_url = f"http://{host}:{port}"

        # 生成 URL（不包含 Token，安全考虑）

        # 生成二维码图片
        qr_image = generate_qrcode_image(target_url, size=settings.webui.qrcode_size)

        return Response(
            content=qr_image,
            media_type="image/png",
            headers={
                "Content-Disposition": "inline; filename=webui-qrcode.png",
                "Cache-Control": "public, max-age=3600",  # 缓存 1 小时
            },
        )
    except ValueError as e:
        logger.warning(f"Invalid QR code parameters: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate QR code") from e


@router.get("/welcome", response_class=HTMLResponse)
async def welcome_page(
    host: HostParam = None,
    port: int | None = None,
) -> str:
    """欢迎页面（显示二维码和访问信息）

    Args:
        host: 主机地址（可选，默认使用本机 IP）
        port: 端口（可选，默认 25808）

    Returns:
        HTML 欢迎页面
    """
    if not host:
        host = get_local_ip()
    if not port:
        port = settings.webui.port

    return render_welcome_page(host, port)


@router.get("/browser/snapshot")
async def get_browser_snapshot(chat_id: str | None = None) -> JSONResponse:
    """Get the latest browser snapshot (screenshot + ARIA refs with BBox data).

    Returns screenshot, page metadata, and interactive element bounding boxes
    for the Browser Inspector panel in the frontend.
    Requires ``chat_id`` to scope the lookup to the active chat session.
    """
    from app.services.agent.browser_snapshot import (
        BrowserSnapshotUnavailableError,
        collect_browser_snapshot_payload,
    )

    try:
        payload = await collect_browser_snapshot_payload(chat_id=chat_id)
    except BrowserSnapshotUnavailableError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "message": exc.message},
        )
    except Exception as exc:
        logger.error("Browser snapshot failed: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "snapshot_failed", "message": "Browser snapshot failed"},
        )

    return JSONResponse(content=payload)
