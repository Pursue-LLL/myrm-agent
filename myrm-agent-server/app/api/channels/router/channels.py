"""[INPUT]
- .common (POS: shared router and helpers)

[OUTPUT]
- list_channel_status, install_channel_dependencies, toggle_channel

[POS]
Channel management API: channel status, dependency install and enable toggle.
"""

from __future__ import annotations

import asyncio

from fastapi import Depends, HTTPException
from nanoid import generate as nanoid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.channels.schemas import (
    ChannelInstallDependenciesResponse,
    ChannelStatusResponse,
    ChannelToggleRequest,
    ChannelToggleResponse,
)
from app.channels import ChannelStatus
from app.database.connection import get_db

from .common import (
    _channel_config_key,
    _issues_to_response,
    _merged_issues_for_channel,
    router,
)


@router.get("/status", response_model=list[ChannelStatusResponse])
async def list_channel_status() -> list[ChannelStatusResponse]:
    """Get runtime status of registered channels plus SDK-unavailable catalog entries."""
    from app.channels.providers.registry import probe_sdk_channel_issues
    from app.core.channel_bridge import channel_gateway
    from app.core.infra.ingress_requirement import resolve_ingress_requirement, supplement_ingress_issues

    statuses = channel_gateway.get_status()
    probe_map = probe_sdk_channel_issues()
    ingress_snapshot = await resolve_ingress_requirement()
    result: list[ChannelStatusResponse] = []
    for name, ch_status in statuses.items():
        ch = channel_gateway.bus.get_channel(name)
        activity = ch.activity if ch else None
        merged = _merged_issues_for_channel(name, probe_map=probe_map)
        merged = supplement_ingress_issues(name, merged, ingress_snapshot)
        issues = _issues_to_response(merged)
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
    for name, probed in probe_map.items():
        if name in statuses:
            continue
        result.append(
            ChannelStatusResponse(
                name=name,
                status="unavailable",
                connected=False,
                channelType=name,
                issues=_issues_to_response(probed),
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
    from app.services.channels.dependency_install import (
        install_channel_dependencies as run_install,
    )

    raw_issues = _merged_issues_for_channel(channel_name)
    ok, message = await asyncio.to_thread(run_install, channel_name, raw_issues)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    from app.services.channels.sdk_registration import hot_register_channel

    registered = await hot_register_channel(channel_name)
    if not registered:
        message = (
            f"{message}; packages installed but channel could not be registered — "
            "restart the server or retry after configuring credentials"
        )
    return ChannelInstallDependenciesResponse(ok=True, message=message, registered=registered)


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

    if body.enabled:
        from app.services.channels.dependency_install import ensure_channel_dependencies_ready
        from app.services.channels.sdk_registration import hot_register_channel

        pre_issues = _merged_issues_for_channel(channel_name)
        ready, detail = await asyncio.to_thread(
            ensure_channel_dependencies_ready,
            channel_name,
            pre_issues,
        )
        if not ready:
            raise HTTPException(status_code=409, detail=detail or "Channel dependencies not installed")
        if channel_gateway.bus.get_channel(channel_name) is None:
            await hot_register_channel(channel_name)

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

    if body.enabled:
        await db.flush()
        enabled = await channel_gateway.enable_channel(channel_name)
        if not enabled:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Channel dependencies installed but channel is not registered; configure credentials and retry",
            )
        await db.commit()
    else:
        await db.commit()
        await channel_gateway.disable_channel(channel_name)

    ch = channel_gateway.bus.get_channel(channel_name)
    status_val = ch.status.value if ch else "unknown"
    connected = False
    if ch and ch.status == ChannelStatus.RUNNING:
        from app.core.channel_bridge import check_channel_connected

        connected = check_channel_connected(ch)
    return ChannelToggleResponse(name=channel_name, enabled=body.enabled, status=status_val, connected=connected)
