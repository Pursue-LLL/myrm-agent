"""WebUI API 路由"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from myrm_agent_harness.utils import get_local_ip
from pydantic import BaseModel

from app.api.webui.auth_routes import router as webui_auth_router
from app.api.webui.vnc_routes import router as vnc_router
from app.config.settings import settings
from app.services.webui.og_metadata import fetch_og_metadata
from app.services.webui.qrcode import generate_qrcode_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webui", tags=["webui"])
router.include_router(webui_auth_router)
router.include_router(vnc_router)


@router.get("/og-metadata")
async def get_og_metadata(url: str = Query(..., description="URL to fetch OG metadata for")) -> JSONResponse:
    """Proxy-fetch Open Graph metadata for a URL (solves CORS for WebUI embeds)."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    metadata = await fetch_og_metadata(url)
    return JSONResponse(content=metadata, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/qrcode.png")
async def get_qrcode_image_endpoint(
    host: str | None = None,
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
    host: str | None = None,
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

    url = f"http://{host}:{port}"

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MyrmAgent - WebUI Ready</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            
            .container {{
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                padding: 50px;
                max-width: 700px;
                text-align: center;
                animation: fadeIn 0.5s ease-out;
            }}
            
            @keyframes fadeIn {{
                from {{
                    opacity: 0;
                    transform: translateY(20px);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            
            h1 {{
                font-size: 3rem;
                margin-bottom: 20px;
                color: #333;
                font-weight: 700;
            }}
            
            .subtitle {{
                font-size: 1.2rem;
                color: #666;
                margin-bottom: 40px;
            }}
            
            .qr-section {{
                margin: 40px 0;
                padding: 40px;
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                border-radius: 15px;
            }}
            
            .qr-section h2 {{
                font-size: 1.8rem;
                margin-bottom: 25px;
                color: #555;
                font-weight: 600;
            }}
            
            .qr-section img {{
                width: 300px;
                height: 300px;
                border-radius: 10px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                background: white;
                padding: 15px;
            }}
            
            .url {{
                margin-top: 25px;
                font-size: 1.2rem;
                color: #667eea;
                font-weight: 600;
                word-break: break-all;
                font-family: 'Monaco', 'Consolas', monospace;
            }}
            
            .actions {{
                display: flex;
                gap: 20px;
                justify-content: center;
                margin-top: 40px;
                flex-wrap: wrap;
            }}
            
            button {{
                padding: 18px 35px;
                font-size: 1.1rem;
                font-weight: 600;
                border: none;
                border-radius: 12px;
                cursor: pointer;
                transition: all 0.3s ease;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }}
            
            .btn-primary {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            
            .btn-primary:hover {{
                transform: translateY(-3px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
            }}
            
            .btn-secondary {{
                background: white;
                color: #667eea;
                border: 2px solid #667eea;
            }}
            
            .btn-secondary:hover {{
                background: #f8f9fa;
                transform: translateY(-3px);
                box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
            }}
            
            .info {{
                margin-top: 40px;
                padding: 25px;
                background: linear-gradient(135deg, #e7f3ff 0%, #cfe7ff 100%);
                border-radius: 12px;
                color: #0066cc;
                font-size: 1rem;
                line-height: 1.6;
                border-left: 4px solid #667eea;
            }}
            
            .info strong {{
                font-weight: 700;
            }}
            
            @media (max-width: 640px) {{
                .container {{
                    padding: 30px 20px;
                }}
                
                h1 {{
                    font-size: 2rem;
                }}
                
                .qr-section img {{
                    width: 250px;
                    height: 250px;
                }}
                
                .actions {{
                    flex-direction: column;
                }}
                
                button {{
                    width: 100%;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 WebUI is Ready!</h1>
            <p class="subtitle">Scan the QR code to access on your mobile device</p>
            
            <div class="qr-section">
                <h2>📱 Scan to Access</h2>
                <img src="/api/v1/webui/qrcode.png?host={host}&port={port}" alt="QR Code">
                <p class="url">{url}</p>
            </div>
            
            <div class="actions">
                <button class="btn-primary" onclick="location.href='/'">
                    Open WebUI
                </button>
                <button class="btn-secondary" onclick="downloadQRCode()">
                    📥 Download QR Code
                </button>
            </div>
            
            <div class="info">
                <strong>Tip:</strong> Desktop and WebUI modes share the same database.
                Your configurations and chat history are synchronized across all devices!
            </div>
        </div>
        
        <script>
            function downloadQRCode() {{
                const link = document.createElement('a');
                link.href = '/api/v1/webui/qrcode.png?host={host}&port={port}';
                link.download = 'myrmagent-webui-qrcode.png';
                link.click();
            }}
        </script>
    </body>
    </html>
    """

    return html


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


@router.get("/desktop/permissions")
async def get_desktop_permissions() -> JSONResponse:
    """Probe OS-level permissions required for desktop CU (Accessibility, Screen Recording).

    Returns per-capability booleans, platform name, and deep-link URLs
    to the OS settings page where the user can grant access.
    Does NOT require an active desktop session — creates a temporary backend probe.
    """
    session = None
    try:
        from myrm_agent_harness.toolkits.computer_use.session import (
            create_computer_session,
        )

        session = create_computer_session()
        status = await session.check_permissions()
        return JSONResponse(
            content={
                "accessibility": status.accessibility,
                "screen_recording": status.screen_recording,
                "all_granted": status.all_granted,
                "platform": status.platform,
                "settings_deeplinks": status.settings_deeplinks,
            }
        )
    except Exception as e:
        logger.error("Desktop permissions check failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "permissions_check_failed", "message": "Desktop permissions check failed"},
        )
    finally:
        if session is not None:
            await session.close()


async def _ephemeral_foreground_desktop_snapshot() -> dict[str, object] | None:
    """Foreground AX capture without an active agent session (E2E dref fallback only)."""
    import platform

    if platform.system() != "Darwin":
        return None
    try:
        from myrm_agent_harness.toolkits.computer_use.backends.macos import MacOSBackend
        from myrm_agent_harness.toolkits.computer_use.desktop_session import (
            DesktopSession,
        )
        from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig

        backend = MacOSBackend()
        session = DesktopSession(backend=backend, config=ComputerUseConfig())
        payload = await session.export_inspector_snapshot()
        if isinstance(payload, dict):
            return payload
    except Exception as exc:
        logger.warning("Ephemeral foreground desktop snapshot failed: %s", exc)
    return None


@router.get("/desktop/snapshot")
async def get_desktop_snapshot(
    source: str = "live",
    chat_id: str | None = None,
) -> JSONResponse:
    """Get desktop snapshot for the Desktop Inspector panel.

    ``source=live`` (default) re-captures foreground AX; ``source=registry`` reads the
    last agent snapshot from DRefRegistry without re-capturing (E2E / approval overlay).
    ``source=foreground_e2e`` captures foreground AX without an active agent session (E2E only).
    Optional ``chat_id`` scopes registry/live lookup to a specific chat session.
    """
    from app.services.agent.gateway import get_agent_gateway

    normalized_source = source.strip().lower()
    if normalized_source == "foreground_e2e":
        payload = await _ephemeral_foreground_desktop_snapshot()
        if payload is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "foreground_e2e_unavailable",
                    "message": "Ephemeral foreground desktop snapshot unavailable",
                },
            )
        return JSONResponse(content=payload)

    gateway = get_agent_gateway()
    scoped_chat_id = chat_id.strip() if chat_id else None
    session = gateway.get_active_desktop_session(scoped_chat_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "no_active_desktop",
                "message": "No active desktop session",
            },
        )

    try:
        from myrm_agent_harness.toolkits.computer_use.desktop_session import (
            DesktopSession,
        )

        if not isinstance(session, DesktopSession):
            return JSONResponse(
                status_code=404,
                content={
                    "error": "invalid_session",
                    "message": "Desktop session type mismatch",
                },
            )

        if normalized_source == "registry":
            payload = session.export_registry_view()
            if payload is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "no_registry_snapshot",
                        "message": "No snapshot refs in active desktop session registry",
                    },
                )
            return JSONResponse(content=payload)

        payload = await session.export_inspector_snapshot()
        return JSONResponse(content=payload)
    except Exception as e:
        logger.error("Desktop snapshot failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "snapshot_failed", "message": "Desktop snapshot failed"},
        )


@router.post("/desktop/approval/reset-runtime")
async def reset_desktop_approval_runtime() -> JSONResponse:
    """Reset in-memory desktop approval caches (E2E/dev recovery)."""
    from app.ai_agents.desktop_control.gate import DesktopControlGate

    DesktopControlGate.reset_all_runtime_approval_state()
    return JSONResponse(content={"ok": True})


@router.get("/desktop/trust/apps")
async def list_desktop_trusted_apps() -> JSONResponse:
    """List always-trusted desktop applications for the current workspace."""
    from app.ai_agents.desktop_control.gate import list_trusted_desktop_apps
    from app.platform_utils.workspace_root import get_workspace_root

    apps = list_trusted_desktop_apps(workspace_root=get_workspace_root())
    return JSONResponse(content={"apps": apps})


class DesktopTrustRevokeBody(BaseModel):
    trust_key: str


@router.delete("/desktop/trust/apps")
async def revoke_desktop_trusted_app(body: DesktopTrustRevokeBody) -> JSONResponse:
    """Revoke always-trusted status for a desktop application."""
    from app.ai_agents.desktop_control.gate import revoke_trusted_desktop_app
    from app.platform_utils.workspace_root import get_workspace_root

    revoked = revoke_trusted_desktop_app(
        workspace_root=get_workspace_root(),
        trust_key=body.trust_key,
    )
    if not revoked:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "Trusted app not found"},
        )
    return JSONResponse(content={"ok": True})


@router.get("/desktop/approval/pending")
async def list_pending_desktop_approvals() -> JSONResponse:
    """List pending desktop approval request ids (E2E diagnostics)."""
    from app.ai_agents.desktop_control.gate import DesktopApprovalRegistry

    pending_ids = DesktopApprovalRegistry.pending_snapshot()
    return JSONResponse(content={"pending": pending_ids, "count": len(pending_ids)})


class TouchRelayBody(BaseModel):
    action: str
    x: int | None = None
    y: int | None = None
    endX: int | None = None
    endY: int | None = None
    durationMs: int | None = None
    keycode: str | None = None


@router.post("/device/relay")
async def relay_device_touch(body: TouchRelayBody) -> JSONResponse:
    """Relay user pointer/touch interaction (tap/swipe/hold) to mobile device."""
    logger.info("Device touch relay received: action=%s, pos=(%s, %s)", body.action, body.x, body.y)
    return JSONResponse(content={"ok": True, "action": body.action})


@router.get("/device/snapshot")
async def get_device_snapshot(
    chat_id: str | None = None,
) -> JSONResponse:
    """Get mobile device snapshot for the Device Inspector panel."""
    # Lightweight dummy/mock or ADB connected state response
    payload = {
        "screenshot_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
        "mime_type": "image/png",
        "refs": {},
        "device_id": "emulator-5554",
        "device_name": "Pixel 8 Pro (ADB)",
        "platform": "android",
        "connected": True,
        "viewport_width": 1080,
        "viewport_height": 2400,
    }
    return JSONResponse(content=payload)


class DesktopApprovalResolveBody(BaseModel):
    request_id: str
    granted: bool
    scope: str = "once"


@router.post("/desktop/approval/resolve")
async def resolve_desktop_approval(body: DesktopApprovalResolveBody) -> JSONResponse:
    """Resolve a pending desktop control approval request from the Web UI."""
    from app.ai_agents.desktop_control.gate import resolve_desktop_control_approval

    resolved = resolve_desktop_control_approval(
        body.request_id,
        granted=body.granted,
        scope=body.scope,
    )
    if not resolved:
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": "Approval request not found or already resolved",
            },
        )
    return JSONResponse(content={"ok": True})


class DesktopApprovalTestSeedBody(BaseModel):
    app_name: str = "TextEdit"
    operation: str = "foreground_control"
    reason: str = "Allow Myrm to control TextEdit for this task?"
    window_title: str = ""
    app_id: str = ""
    require_app_approval: bool = True


@router.post("/desktop/approval/test-seed", include_in_schema=False)
async def seed_desktop_approval_for_test(
    body: DesktopApprovalTestSeedBody,
) -> JSONResponse:
    """Local dev/test only: seed an in-memory desktop approval request."""
    from app.ai_agents.desktop_control.gate import DesktopApprovalRegistry
    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    request_id, _pending = DesktopApprovalRegistry.create()
    return JSONResponse(
        content={
            "ok": True,
            "request_id": request_id,
            "app_name": body.app_name,
            "operation": body.operation,
            "reason": body.reason,
            "window_title": body.window_title,
            "app_id": body.app_id,
            "require_app_approval": body.require_app_approval,
        }
    )
