"""Channel instance endpoints: list, create, delete and rename instances, and the per-type capacity.

[INPUT]
- api.channels.schemas::ChannelInstanceCreate/Response, DisplayNameUpdate (POS: Channel API 请求响应模型)
- api.channels.router::channel_credentials_key (POS: Channel 管理路由层)
- core.channel_bridge::channel_gateway (POS: 应用级渠道网关单例)
- core.channel_bridge.channel_factory::create_channel_instance, generate_instance_id, load_persisted_instances, save_persisted_instances (POS: 业务层渠道装配，连接框架工厂与应用的数据库凭据来源)
- services.config.service::ConfigService (POS: 用户配置的存储与同步)
- database.connection::get_session (POS: 数据库连接管理)
- database.models::UserConfig (POS: ORM 模型)

[OUTPUT]
- router: 频道实例列表、创建、删除、显示名更新与容量元数据端点
- _delete_instance_credentials: 删除某个实例的凭据记录（微信登出路径复用）

[POS]
频道实例管理路由。多实例 CRUD、显示名更新与每类型实例上限；凭据与配置端点在 `instances_credentials.py`。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.channels.router import channel_credentials_key
from app.api.channels.schemas import (
    ChannelInstanceCreate,
    ChannelInstanceResponse,
    DisplayNameUpdate,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Instance CRUD ──────────────────────────────────────────


@router.get("/instances/meta")
async def get_channel_instances_meta() -> dict[str, int]:
    """Return channel instance capacity metadata (e.g. per-type limit)."""
    from app.core.channel_bridge import channel_gateway

    return {
        "maxInstancesPerType": channel_gateway.max_instances_per_type,
    }


@router.get("/instances", response_model=list[ChannelInstanceResponse])
async def list_channel_instances(
    channel_type: str | None = None,
) -> list[ChannelInstanceResponse]:
    """List all channel instances, optionally filtered by type."""
    from app.core.channel_bridge import channel_gateway

    results: list[ChannelInstanceResponse] = []
    for name, channel in channel_gateway.bus.channels.items():
        base_type = channel_gateway._resolve_channel_type(channel)
        if channel_type and base_type != channel_type:
            continue
        inst_id = channel.instance_id
        results.append(
            ChannelInstanceResponse(
                instanceId=inst_id or name,
                channelType=base_type,
                channelName=name,
                displayName=channel.display_name,
                status=channel.status,
            )
        )
    return results


@router.post("/instances", response_model=ChannelInstanceResponse, status_code=201)
async def create_channel_instance(
    body: ChannelInstanceCreate,
) -> ChannelInstanceResponse:
    """Create a new channel instance (hot-add at runtime)."""
    from app.core.channel_bridge import channel_gateway
    from app.core.channel_bridge.channel_factory import (
        create_channel_instance as factory_create,
    )
    from app.core.channel_bridge.channel_factory import (
        generate_instance_id,
        load_persisted_instances,
        save_persisted_instances,
    )

    instance_id = generate_instance_id()

    try:
        channel = await factory_create(
            channel_type=body.channel_type,
            instance_id=instance_id,
            credentials=body.credentials,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if body.display_name:
        channel.display_name = body.display_name

    try:
        channel_name = await channel_gateway.add_channel(channel)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if body.credentials:
        from app.services.config.service import ConfigService

        config_key = channel_credentials_key(channel_name)
        await ConfigService().set(config_key, dict(body.credentials), device_id="web")

    current = await load_persisted_instances()
    current.append(
        {
            "channelType": body.channel_type,
            "instanceId": instance_id,
            "displayName": body.display_name,
        }
    )
    await save_persisted_instances(current)

    return ChannelInstanceResponse(
        instanceId=instance_id,
        channelType=body.channel_type,
        channelName=channel_name,
        displayName=body.display_name,
        status=channel.status,
    )


@router.delete("/instances/{instance_id}", status_code=204)
async def delete_channel_instance(
    instance_id: str,
) -> None:
    """Remove a channel instance (hot-remove at runtime)."""
    from app.core.channel_bridge import channel_gateway
    from app.core.channel_bridge.channel_factory import load_persisted_instances, save_persisted_instances

    target_name: str | None = None
    for name in channel_gateway.bus.channels:
        if name.endswith(f"_{instance_id}"):
            target_name = name
            break

    if not target_name:
        raise HTTPException(status_code=404, detail=f"Instance '{instance_id}' not found")

    removed = await channel_gateway.remove_channel(target_name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Failed to remove instance '{instance_id}'")

    current = await load_persisted_instances()
    current = [i for i in current if i.get("instanceId") != instance_id]
    await save_persisted_instances(current)

    await _delete_instance_credentials(target_name)


async def _delete_instance_credentials(channel_name: str) -> None:
    """Remove instance-specific credentials from UserConfig."""
    from sqlalchemy import delete

    from app.database.connection import get_session
    from app.database.models import UserConfig

    config_key = channel_credentials_key(channel_name)
    try:
        async with get_session() as session:
            await session.execute(delete(UserConfig).where(UserConfig.config_key == config_key))
            await session.commit()
    except Exception:
        logger.warning("Failed to delete credentials for %s", channel_name)


@router.patch("/{channel_name}/display-name", response_model=ChannelInstanceResponse)
async def update_channel_display_name(
    channel_name: str,
    body: DisplayNameUpdate,
) -> ChannelInstanceResponse:
    """Update the display name of a channel instance."""
    from app.core.channel_bridge import channel_gateway
    from app.core.channel_bridge.channel_factory import load_persisted_instances, save_persisted_instances

    ch = channel_gateway.bus.get_channel(channel_name)
    if not ch:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_name}' not found")

    base_type = channel_gateway._resolve_channel_type(ch)
    inst_id = ch.instance_id
    ch.display_name = body.display_name

    current = await load_persisted_instances()
    if inst_id:
        for entry in current:
            if entry.get("instanceId") == inst_id:
                entry["displayName"] = body.display_name
                entry.pop("label", None)
                break
    else:
        matched = False
        for entry in current:
            if entry.get("channelName") == channel_name:
                entry["displayName"] = body.display_name
                matched = True
                break
        if not matched:
            current.append(
                {
                    "channelType": base_type,
                    "channelName": channel_name,
                    "displayName": body.display_name,
                }
            )
    await save_persisted_instances(current)

    return ChannelInstanceResponse(
        instanceId=inst_id or channel_name,
        channelType=base_type,
        channelName=channel_name,
        displayName=ch.display_name,
        status=ch.status,
    )
