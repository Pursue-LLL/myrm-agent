"""WebUI API 路由"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from myrm_agent_harness.utils import get_local_ip
from pydantic import BaseModel

from app.config.settings import settings
from app.services.webui.qrcode import generate_qrcode_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webui", tags=["webui"])


class AuthStatusResponse(BaseModel):
    is_setup_done: bool
    is_authenticated: bool
    user_id: str
    username: str
    role: str


@router.get("/auth/status")
async def get_auth_status() -> AuthStatusResponse:
    """Local mode auth status endpoint.

    Returns local user info so the frontend doesn't get a 404.
    Sandbox mode auth is handled by the control plane, not here.
    """
    return AuthStatusResponse(
        is_setup_done=True,
        is_authenticated=True,
        user_id="local-user",
        username="Local User",
        role="admin",
    )


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
async def get_browser_snapshot() -> JSONResponse:
    """Get the latest browser snapshot (screenshot + ARIA refs with BBox data).

    Returns screenshot, page metadata, and interactive element bounding boxes
    for the Browser Inspector panel in the frontend.
    """
    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    session = gateway.get_active_browser_session()
    if session is None:
        return JSONResponse(
            status_code=404,
            content={"error": "no_active_browser", "message": "No active browser session"},
        )

    try:
        from myrm_agent_harness.toolkits.browser.session import BrowserSession

        if not isinstance(session, BrowserSession):
            return JSONResponse(
                status_code=404,
                content={"error": "invalid_session", "message": "Browser session type mismatch"},
            )

        snapshot_result = await session.snapshot(include_bbox=True)

        from myrm_agent_harness.toolkits.browser.session.snapshot_result import SnapshotResult

        if isinstance(snapshot_result, str):
            refs_data: dict[str, dict[str, object]] = {}
        elif isinstance(snapshot_result, tuple):
            refs_data = {}
        elif isinstance(snapshot_result, SnapshotResult):
            refs_data = {
                ref_id: {
                    "role": info.role,
                    "name": info.name,
                    "nth": info.nth,
                    "bbox": (
                        {
                            "x": info.bbox.x,
                            "y": info.bbox.y,
                            "width": info.bbox.width,
                            "height": info.bbox.height,
                            "centerX": info.bbox.centerX,
                            "centerY": info.bbox.centerY,
                            "viewport_width": info.bbox.viewport_width,
                            "viewport_height": info.bbox.viewport_height,
                        }
                        if info.bbox
                        else None
                    ),
                    "position": info.position,
                }
                for ref_id, info in snapshot_result.refs.items()
            }
        else:
            refs_data = {}

        screenshot_b64 = await session.extract_screenshot(scale=1.0)

        page_url = ""
        page_title = ""
        viewport_width = 1280
        viewport_height = 720

        for info in refs_data.values():
            bbox = info.get("bbox")
            if isinstance(bbox, dict) and bbox.get("viewport_width"):
                viewport_width = int(bbox["viewport_width"])
                viewport_height = int(bbox["viewport_height"])
                break

        try:
            tab_ctrl = getattr(session, "_tab_controller", None)
            if tab_ctrl is not None:
                page = tab_ctrl.get_active_page()
                if page is not None:
                    page_url = page.url
                    page_title = await page.title()
        except Exception:
            pass

        return JSONResponse(
            content={
                "screenshot_base64": screenshot_b64,
                "mime_type": "image/jpeg",
                "refs": refs_data,
                "page_url": page_url,
                "page_title": page_title,
                "viewport_width": viewport_width,
                "viewport_height": viewport_height,
            }
        )
    except Exception as e:
        logger.error("Browser snapshot failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "snapshot_failed", "message": str(e)},
        )


@router.get("/desktop/snapshot")
async def get_desktop_snapshot() -> JSONResponse:
    """Get the latest desktop snapshot for the Desktop Inspector panel."""
    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    session = gateway.get_active_desktop_session()
    if session is None:
        return JSONResponse(
            status_code=404,
            content={"error": "no_active_desktop", "message": "No active desktop session"},
        )

    try:
        from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession

        if not isinstance(session, DesktopSession):
            return JSONResponse(
                status_code=404,
                content={"error": "invalid_session", "message": "Desktop session type mismatch"},
            )

        payload = await session.export_inspector_snapshot()
        return JSONResponse(content=payload)
    except Exception as e:
        logger.error("Desktop snapshot failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "snapshot_failed", "message": str(e)},
        )
