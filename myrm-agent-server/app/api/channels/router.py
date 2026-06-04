"""Channel management core endpoints: status, toggle, pairings, groups.

[INPUT]
- api.channels.schemas::ChannelStatusResponse, PairingCreate/Response, GroupInfoResponse, etc. (POS: Channel API 请求响应模型)
- api.dependencies::get_deploy_identity (POS: 用户身份认证依赖)
- database.connection::get_db (POS: 数据库连接管理)
- database.models::ChannelPairingModel, UserConfig (POS: ORM 模型)

[OUTPUT]
- router: Channel 状态/切换/Pairings/群组管理端点
- _channel_config_key: 频道名到 UserConfig key 的映射（被其他子模块引用）

[POS]
Channel 管理核心路由。提供频道状态查询、启用/禁用切换、账号绑定 CRUD 和群组管理。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from nanoid import generate as nanoid
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.channels.schemas import (
    ChannelInstallDependenciesResponse,
    ChannelIssueResponse,
    ChannelStatusResponse,
    ChannelToggleRequest,
    ChannelToggleResponse,
    EnabledGroupsUpdate,
    GroupInfoResponse,
    PairingCreate,
    PairingResponse,
    PairingStatusUpdate,
)
from app.channels import ChannelStatus
from app.database.connection import get_db
from app.database.models import ChannelPairingModel

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Channel Config Key Mapping (shared by sub-modules) ──────────────

_CHANNEL_CONFIG_KEYS: dict[str, str] = {
    "feishu": "feishuCredentials",
    "dingtalk": "dingtalkCredentials",
    "slack": "slackCredentials",
    "qq": "qqCredentials",
    "discord": "discordCredentials",
    "wecom": "wecomCredentials",
    "wecom_aibot": "wecomAibotCredentials",
    "teams": "teamsCredentials",
    "matrix": "matrixCredentials",
    "telegram": "telegramCredentials",
    "googlechat": "googlechatCredentials",
    "wechat": "wechatCredentials",
    "whatsapp": "whatsappCredentials",
    "voice": "voiceCredentials",
    "signal": "signalCredentials",
    "line": "lineCredentials",
    "imessage": "imessageCredentials",
    "irc": "ircCredentials",
    "zalo": "zaloCredentials",
    "email": "emailCredentials",
    "mattermost": "mattermostCredentials",
    "onebot": "onebotCredentials",
    "sms": "smsCredentials",
}


def _channel_config_key(channel_name: str) -> str | None:
    """Map a channel name to its credential config_key in UserConfig."""
    return _CHANNEL_CONFIG_KEYS.get(channel_name)


# ── Status & Toggle ──────────────────────────────────────────


@router.get("/status", response_model=list[ChannelStatusResponse])
async def list_channel_status() -> list[ChannelStatusResponse]:
    """Get runtime status of all registered channels."""
    from app.core.channel_bridge import channel_gateway

    statuses = channel_gateway.get_status()
    all_issues = channel_gateway.collect_all_issues()
    result: list[ChannelStatusResponse] = []
    for name, ch_status in statuses.items():
        ch = channel_gateway.bus.get_channel(name)
        activity = ch.activity if ch else None
        issues = [
            ChannelIssueResponse(
                kind=i.kind,
                severity=i.severity,
                message=i.message,
                fix=i.fix,
            )
            for i in all_issues.get(name, [])
        ]
        base_type = channel_gateway._resolve_channel_type(ch) if ch else name
        connected = False
        if ch and ch_status == ChannelStatus.RUNNING:
            from app.core.channel_bridge import check_channel_connected

            connected = check_channel_connected(ch)
        status_val = ch_status.value if isinstance(ch_status, ChannelStatus) else str(ch_status)
        result.append(
            ChannelStatusResponse(
                name=name,
                status=status_val,
                connected=connected,
                channelType=base_type,
                instanceId=ch.instance_id if ch else "",
                displayName=ch.display_name if ch else "",
                last_inbound_at=activity.last_inbound_at if activity else None,
                last_outbound_at=activity.last_outbound_at if activity else None,
                last_active_at=activity.last_active_at if activity else None,
                issues=issues,
            )
        )
    return result


@router.post(
    "/{channel_name}/install-dependencies",
    response_model=ChannelInstallDependenciesResponse,
)
async def install_channel_dependencies(
    channel_name: str,
) -> ChannelInstallDependenciesResponse:
    """Lazy-install optional packages for a channel (GUI one-click)."""
    from app.core.channel_bridge import channel_gateway
    from app.services.channels.dependency_install import (
        install_channel_dependencies as run_install,
    )

    all_issues = channel_gateway.collect_all_issues()
    raw_issues = all_issues.get(channel_name, [])
    ok, message = await asyncio.to_thread(run_install, channel_name, raw_issues)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return ChannelInstallDependenciesResponse(ok=True, message=message)


@router.patch("/{channel_name}/toggle", response_model=ChannelToggleResponse)
async def toggle_channel(
    channel_name: str,
    body: ChannelToggleRequest,
    db: AsyncSession = Depends(get_db),
) -> ChannelToggleResponse:
    """Enable or disable a channel at runtime without removing credentials."""
    from app.core.channel_bridge import channel_gateway
    from app.database.models import UserConfig

    spec_key = _channel_config_key(channel_name)
    if not spec_key:
        raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_name}")

    row = (
        await db.execute(
            select(UserConfig).where(
                UserConfig.config_key == spec_key,
            )
        )
    ).scalar_one_or_none()

    if row and isinstance(row.config_value, dict):
        config = dict(row.config_value)
    else:
        config = {}

    config["enabled"] = body.enabled
    if row:
        row.config_value = config
    else:
        row = UserConfig(
            id=nanoid(size=16),
            config_key=spec_key,
            config_value=config,
            version=f"{int(asyncio.get_running_loop().time() * 1000)}_0",
            last_device_id="web",
            is_encrypted=False,
        )
        db.add(row)
    await db.commit()

    if body.enabled:
        await channel_gateway.enable_channel(channel_name)
    else:
        await channel_gateway.disable_channel(channel_name)

    ch = channel_gateway.bus.get_channel(channel_name)
    status_val = ch.status.value if ch else "unknown"
    connected = False
    if ch and ch.status == ChannelStatus.RUNNING:
        from app.core.channel_bridge import check_channel_connected

        connected = check_channel_connected(ch)
    return ChannelToggleResponse(name=channel_name, enabled=body.enabled, status=status_val, connected=connected)


# ── Pairings CRUD ──────────────────────────────────────────


@router.get("/pairings", response_model=list[PairingResponse])
async def list_pairings(
    db: AsyncSession = Depends(get_db),
) -> list[PairingResponse]:
    """List all channel pairings for the current user."""
    rows = (await db.execute(select(ChannelPairingModel).order_by(ChannelPairingModel.created_at.desc()))).scalars().all()

    return [
        PairingResponse(
            id=r.id,
            channel=r.channel,
            sender_id=r.sender_id,
            user_id="sandbox",
            status=r.status,
            display_name=r.display_name,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post("/pairings", response_model=PairingResponse, status_code=201)
async def create_pairing(
    body: PairingCreate,
    db: AsyncSession = Depends(get_db),
) -> PairingResponse:
    """Bind an external channel identity to the current user."""
    sender_id = _normalize_sender_id(body.channel, body.sender_id)
    existing = (
        await db.execute(
            select(ChannelPairingModel).where(
                ChannelPairingModel.channel == body.channel,
                ChannelPairingModel.sender_id == sender_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        return PairingResponse(
            id=existing.id,
            channel=existing.channel,
            sender_id=existing.sender_id,
            user_id="sandbox",
            status=existing.status,
            display_name=existing.display_name,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )

    row = ChannelPairingModel(
        id=nanoid(size=16),
        channel=body.channel,
        sender_id=sender_id,
        status="active",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    return PairingResponse(
        id=row.id,
        channel=row.channel,
        sender_id=row.sender_id,
        user_id="sandbox",
        status=row.status,
        display_name=row.display_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/pairings/{pairing_id}", status_code=204)
async def delete_pairing(
    pairing_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a channel pairing."""
    result = await db.execute(delete(ChannelPairingModel).where(ChannelPairingModel.id == pairing_id))
    rowcount = getattr(result, "rowcount", None)
    deleted = int(rowcount) if isinstance(rowcount, int) else 0
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Pairing not found")
    await db.commit()


@router.patch("/pairings/{pairing_id}", response_model=PairingResponse)
async def update_pairing_status(
    pairing_id: str,
    body: PairingStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> PairingResponse:
    """Update the status and/or display_name of a channel pairing."""
    if body.status is None and body.display_name is None:
        raise HTTPException(status_code=422, detail="Nothing to update")

    row = (await db.execute(select(ChannelPairingModel).where(ChannelPairingModel.id == pairing_id))).scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Pairing not found")

    was_pending = row.status == "pending"
    if body.status is not None:
        row.status = body.status
    if body.display_name is not None:
        row.display_name = body.display_name
    await db.commit()
    await db.refresh(row)

    if was_pending and body.status == "active":
        await _notify_pairing_approved(row.channel, row.sender_id)

    return PairingResponse(
        id=row.id,
        channel=row.channel,
        sender_id=row.sender_id,
        user_id="sandbox",
        status=row.status,
        display_name=row.display_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ── Groups ──────────────────────────────────────────


@router.get("/groups", response_model=list[GroupInfoResponse])
async def list_groups(
    force_refresh: bool = False,
) -> list[GroupInfoResponse]:
    """List all groups the bot participates in, with enabled status."""
    from app.core.channel_bridge import channel_gateway

    enabled_set = await _load_enabled_groups()
    all_groups = await channel_gateway.list_channel_groups(force_refresh=force_refresh)

    results: list[GroupInfoResponse] = [
        GroupInfoResponse(
            jid=g.jid,
            name=g.name,
            channel=g.channel,
            is_enabled=enabled_set is None or g.jid in enabled_set,
        )
        for g in all_groups
    ]
    results.sort(key=lambda g: g.name.lower())
    return results


@router.put("/groups", status_code=200)
async def update_enabled_groups(
    body: EnabledGroupsUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update the list of enabled groups in the channels config."""
    from app.database.models import UserConfig

    row = (
        await db.execute(
            select(UserConfig).where(
                UserConfig.config_key == "channels",
            )
        )
    ).scalar_one_or_none()

    if row and isinstance(row.config_value, dict):
        config = dict(row.config_value)
    else:
        config = {}

    config["enabledGroups"] = body.enabled_groups
    if row:
        row.config_value = config
    else:
        row = UserConfig(
            id=nanoid(size=16),
            config_key="channels",
            config_value=config,
            version=f"{int(asyncio.get_running_loop().time() * 1000)}_0",
            last_device_id="web",
            is_encrypted=False,
        )
        db.add(row)

    await db.commit()

    from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider

    SqlChannelPolicyProvider._invalidate_cache()

    return {"status": "ok"}


# ── Helpers (private) ──────────────────────────────────────────


async def _load_enabled_groups() -> set[str] | None:
    """Load enabled groups from the channels config."""

    from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider

    provider = SqlChannelPolicyProvider()
    return await provider.get_enabled_groups()


def _normalize_sender_id(channel: str, sender_id: str) -> str:
    """Normalize and validate sender_id for a given channel."""
    if channel != "whatsapp":
        return sender_id
    if "@" in sender_id:
        return sender_id
    digits = "".join(c for c in sender_id if c.isdigit())
    if len(digits) < 7 or len(digits) > 15:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid phone number: expected 7-15 digits, got {len(digits)}",
        )
    return f"{digits}@s.whatsapp.net"


async def _notify_pairing_approved(channel: str, sender_id: str) -> None:
    """Best-effort send approval notification to the sender via their IM channel."""
    try:
        from app.channels.types import OutboundMessage
        from app.core.channel_bridge import channel_gateway

        msg = OutboundMessage(
            channel=channel,
            recipient_id=sender_id,
            content="✅ 您的访问已获批准，现在可以发送消息了。\nYour access has been approved. You can now send messages.",
            user_id="",
        )
        asyncio.create_task(channel_gateway.bus.publish_outbound(msg))
    except Exception:
        logging.getLogger(__name__).debug("Failed to send approval notification", exc_info=True)
