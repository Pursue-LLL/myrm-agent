"""WeChat and WhatsApp specific status/login/logout endpoints.

[INPUT]
- api.channels.schemas::WhatsAppStatusResponse, WeChatStatusResponse (POS: Channel API 请求响应模型)
- api.channels.instances::_delete_instance_credentials (POS: 频道实例管理路由)
- api.channels.router::_channel_config_key (POS: 频道凭证配置键映射)
- database.connection::get_session (POS: 异步数据库会话管理)
- database.models::UserConfig (POS: 用户配置数据模型)

[OUTPUT]
- router: WhatsApp/WeChat 状态查询、登录触发、登出端点

[POS]
WeChat/WhatsApp 专用路由。提供扫码登录、QR 码获取、连接状态查询和登出操作。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.api.channels.schemas import (
    WeChatStatusResponse,
    WhatsAppStatusResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/whatsapp/status", response_model=WhatsAppStatusResponse)
async def whatsapp_status() -> WhatsAppStatusResponse:
    """Get WhatsApp connection status and QR code as base64 PNG for pairing."""
    from app.core.channel_bridge import channel_gateway

    channel = channel_gateway.bus.get_channel("whatsapp")
    if not channel:
        raise HTTPException(status_code=404, detail="WhatsApp channel not registered")

    from app.core.channel_bridge import check_channel_connected

    connected = check_channel_connected(channel)

    qr_data = getattr(channel, "qr_code", None)
    qr_png: str | None = None
    if qr_data and not connected:
        qr_png = _qr_to_base64_png(qr_data)

    return WhatsAppStatusResponse(
        connected=connected,
        status=channel.status.value,
        qr_code=qr_png,
        phone_number=getattr(channel, "phone_number", None),
    )


@router.get("/wechat/status", response_model=WeChatStatusResponse)
async def wechat_status() -> WeChatStatusResponse:
    """Get WeChat connection status and QR code."""
    return await _get_wechat_instance_status("wechat")


@router.get("/{channel_name}/wechat-status", response_model=WeChatStatusResponse)
async def wechat_instance_status(
    channel_name: str,
) -> WeChatStatusResponse:
    """Get WeChat instance status by channel name."""
    return await _get_wechat_instance_status(channel_name)


async def _get_wechat_instance_status(channel_name: str) -> WeChatStatusResponse:
    from app.core.channel_bridge import channel_gateway

    channel = channel_gateway.bus.get_channel(channel_name)
    if not channel:
        return WeChatStatusResponse(connected=False)

    if not hasattr(channel, "get_status_info"):
        from app.core.channel_bridge import check_channel_connected

        return WeChatStatusResponse(connected=check_channel_connected(channel))

    status_info = channel.get_status_info()
    connected = bool(status_info.get("connected", False))

    qr_data = status_info.get("qr_code")
    qr_png: str | None = None
    if qr_data and isinstance(qr_data, (str, dict)) and not connected:
        qr_str = qr_data if isinstance(qr_data, str) else str(qr_data.get("qr_image_base64", ""))
        if qr_str:
            qr_png = _qr_to_base64_png(qr_str)

    bot_id = status_info.get("bot_id")
    status_str = str(status_info.get("status", "disconnected"))
    return WeChatStatusResponse(
        connected=connected,
        qr_code=qr_png,
        bot_id=str(bot_id) if bot_id else None,
        status=status_str,
    )


@router.post("/wechat/login")
async def wechat_trigger_login() -> dict[str, str]:
    """Trigger WeChat login (default instance)."""
    return await _trigger_wechat_instance_login("wechat")


@router.post("/{channel_name}/wechat-login")
async def wechat_instance_trigger_login(
    channel_name: str,
) -> dict[str, str]:
    """Trigger WeChat login for a specific instance."""
    return await _trigger_wechat_instance_login(channel_name)


_login_tasks: dict[str, asyncio.Task[None]] = {}


async def _trigger_wechat_instance_login(channel_name: str) -> dict[str, str]:
    from app.channels.protocols import LoginMethod, LoginStatus
    from app.core.channel_bridge import channel_gateway

    channel = channel_gateway.bus.get_channel(channel_name)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_name}' not found")

    if LoginMethod.QR_CODE not in getattr(channel, "supported_login_methods", []):
        raise HTTPException(status_code=400, detail=f"Channel '{channel_name}' does not support QR login")

    existing_task = _login_tasks.get(channel_name)
    if existing_task and not existing_task.done():
        existing_task.cancel()
        try:
            await existing_task
        except (asyncio.CancelledError, Exception):
            pass

    try:
        await channel.stop()
    except Exception as exc:
        logger.debug("Channel stop failed during restart: %s", exc)

    qr_ready: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def _consume_login_events() -> None:
        """Background task: consume the full login generator until completion."""
        try:
            async for event in channel.start_login(LoginMethod.QR_CODE):
                if event.state.status == LoginStatus.WAITING_USER_ACTION and event.state.qr_code_base64:
                    qr_png = f"data:image/png;base64,{event.state.qr_code_base64}"
                    if not qr_ready.done():
                        qr_ready.set_result(qr_png)
                elif event.state.status == LoginStatus.SUCCESS:
                    logger.info("WeChat login completed for '%s'", channel_name)
                    await _persist_login_credentials(channel_name, channel)
                    if not qr_ready.done():
                        qr_ready.set_result("")
                    return
                elif event.state.status == LoginStatus.FAILED:
                    err = event.state.error_message or "Login failed"
                    logger.warning("WeChat login failed for '%s': %s", channel_name, err)
                    if not qr_ready.done():
                        qr_ready.set_exception(HTTPException(status_code=502, detail=err))
                    return

            if not qr_ready.done():
                qr_ready.set_exception(HTTPException(status_code=504, detail="QR code not received within timeout"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("WeChat login background task error for '%s': %s", channel_name, exc)
            if not qr_ready.done():
                qr_ready.set_exception(HTTPException(status_code=502, detail=f"Login error: {exc}"))
        finally:
            _login_tasks.pop(channel_name, None)

    task = asyncio.create_task(_consume_login_events())
    _login_tasks[channel_name] = task

    qr_code = await qr_ready
    if qr_code:
        return {"status": "qr_ready", "qr_code": qr_code}
    return {"status": "connected"}


@router.post("/{channel_name}/wechat-logout")
async def wechat_instance_logout(
    channel_name: str,
) -> dict[str, str]:
    """Logout from a WeChat instance."""
    from app.core.channel_bridge import channel_gateway

    from .instances import _delete_instance_credentials

    channel = channel_gateway.bus.get_channel(channel_name)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_name}' not found")

    try:
        await channel.stop()
    except Exception:
        logging.getLogger(__name__).warning("Error stopping channel '%s' during logout", channel_name)

    await _delete_instance_credentials(channel_name)
    return {"status": "logged_out"}


async def _persist_login_credentials(channel_name: str, channel: object) -> None:
    """Persist channel credentials to DB after successful QR login.

    Uses ConfigService to ensure proper encryption for sensitive credentials.
    """
    client = getattr(channel, "_client", None)
    creds = getattr(client, "credentials", None) if client else None
    if not creds:
        logger.warning("No credentials to persist for '%s' after login", channel_name)
        return

    from app.api.channels.router import _channel_config_key

    config_key = _channel_config_key(channel_name)
    if not config_key:
        config_key = f"{channel_name}Credentials"

    camel_creds: dict[str, object] = {
        "botToken": creds.bot_token,
        "ilinkBotId": creds.ilink_bot_id,
        "baseUrl": creds.base_url,
    }
    if creds.ilink_user_id:
        camel_creds["ilinkUserId"] = creds.ilink_user_id

    try:
        from app.services.config.service import ConfigService

        service = ConfigService()
        await service.set(config_key, camel_creds, device_id="qr_login")
        logger.info("Credentials persisted for channel '%s'", channel_name)
    except Exception as exc:
        logger.error("Failed to persist credentials for '%s': %s", channel_name, exc)


def _qr_to_base64_png(qr_data: str) -> str | None:
    """Convert a QR code string to a base64-encoded PNG data URI."""
    try:
        import base64
        import io

        import qrcode

        img = qrcode.make(qr_data, box_size=8, border=2)
        buffer = io.BytesIO()
        img.save(buffer, kind="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        logging.getLogger(__name__).warning("Failed to convert QR code to PNG", exc_info=True)
        return None
