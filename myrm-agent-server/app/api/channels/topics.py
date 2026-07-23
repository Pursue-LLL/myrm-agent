"""Channel topic discovery and binding endpoints.

[INPUT]
- api.channels.schemas::BindTopicRequest, TopicBindingResponse, ChannelTopicsResponse (POS: Channel API 请求响应模型)
- api.dependencies::get_deploy_identity (POS: 用户身份认证依赖)
- core.channel_bridge.topic_config::SqlTopicManager (POS: Topic 配置管理器)

[OUTPUT]
- router: Topic 发现、绑定和默认 Agent 设置端点

[POS]
频道 Topic 路由。Topic 列表与 Settings 绑定 API；Channel 绑定规则 SSOT 在 `core/channel_bridge/topic_config.py` `bind_topic`。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.api.channels.schemas import (
    BindTopicRequest,
    ChannelTopicsResponse,
    TopicBindingResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _as_meta_mapping(meta: object) -> dict[str, object]:
    if isinstance(meta, dict):
        return {str(k): v for k, v in meta.items()}
    return {}


def _meta_str_list(meta: dict[str, object], key: str) -> list[str]:
    raw = meta.get(key, [])
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        out.append(item if isinstance(item, str) else str(item))
    return out


@router.get("/{channel}/topics", response_model=ChannelTopicsResponse)
async def list_channel_topics(
    channel: str,
) -> ChannelTopicsResponse:
    """List all discovered topics and their bindings for a channel."""
    from app.core.channel_bridge.topic_config import _CHANNEL_LEVEL_KEY, SqlTopicManager

    manager = SqlTopicManager()
    config = await manager.get_all_topics(channel)

    topics: list[TopicBindingResponse] = []
    global_agent_id = None

    for chat_id, group_topics in config.items():
        if not isinstance(group_topics, dict):
            continue

        if chat_id == "__global__":
            global_agent_id = str(group_topics.get(_CHANNEL_LEVEL_KEY, {}).get("agentId", "")) or None
            continue

        for thread_id, topic_cfg in group_topics.items():
            if not isinstance(topic_cfg, dict):
                continue

            actual_thread_id = None if thread_id == _CHANNEL_LEVEL_KEY else thread_id
            topic_id = f"{chat_id}:{actual_thread_id}" if actual_thread_id else chat_id

            topics.append(
                TopicBindingResponse(
                    topicId=topic_id,
                    agentId=str(topic_cfg.get("agentId", "")) or None,
                    enabled=bool(topic_cfg.get("enabled", True)),
                    boundAt=str(topic_cfg.get("boundAt", "")) or None,
                    displayName=str(topic_cfg.get("displayName", "")) or None,
                    avatarUrl=str(topic_cfg.get("avatarUrl", "")) or None,
                    threadSharingMode=str(topic_cfg.get("threadSharingMode", "isolated")),
                    replyMode=str(topic_cfg.get("replyMode", "auto")),
                    draftTimeoutMinutes=int(topic_cfg.get("draftTimeoutMinutes", 5)),
                    draftTimeoutAction=str(topic_cfg.get("draftTimeoutAction", "auto_reject")),
                )
            )

    return ChannelTopicsResponse(
        channel=channel,
        globalAgentId=global_agent_id,
        topics=topics,
    )


@router.post("/{channel}/topics/{topic_id:path}/bind", response_model=TopicBindingResponse)
async def bind_channel_topic(
    channel: str,
    topic_id: str,
    body: BindTopicRequest,
) -> TopicBindingResponse:
    """Bind an agent to a specific topic/group in a channel."""
    from app.core.channel_bridge.topic_config import SqlTopicManager
    from app.database.connection import get_session
    from app.services.agent.agent_service import AgentService

    parts = topic_id.split(":", 1)
    chat_id = parts[0]
    thread_id = parts[1] if len(parts) > 1 else None

    if body.agent_id:
        async with get_session() as _db:
            agent = await AgentService.get_agent_by_id(body.agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")

            from app.core.channel_bridge import channel_gateway as gateway

            channel_caps = gateway.get_channel_capabilities(channel)

            meta_map = _as_meta_mapping(agent.metadata)
            if channel_caps and meta_map.get("required_capabilities") is not None:
                required_caps = _meta_str_list(meta_map, "required_capabilities")
                for cap in required_caps:
                    if not getattr(channel_caps, cap, False):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Channel '{channel}' does not support required capability '{cap}' for this Agent.",
                        )

            high_risk_tools = {"bash", "file_io", "shell"}
            agent_tools = set(_meta_str_list(meta_map, "enabled_builtin_tools"))
            if agent_tools.intersection(high_risk_tools):
                logger.warning(f"Security Warning: Binding high-risk agent {agent.id} to channel {channel} topic {topic_id}")

    from app.channels.types import DraftTimeoutAction, ReplyMode

    reply_mode = ReplyMode(body.reply_mode) if body.reply_mode else ReplyMode.AUTO
    draft_timeout_action = DraftTimeoutAction(body.draft_timeout_action) if body.draft_timeout_action else DraftTimeoutAction.AUTO_REJECT

    manager = SqlTopicManager()
    try:
        ctx = await manager.bind_topic(
            channel=channel,
            chat_id=chat_id,
            thread_id=thread_id,
            agent_id=body.agent_id,
            display_name=body.display_name,
            avatar_url=body.avatar_url,
            thread_sharing_mode=body.thread_sharing_mode or "isolated",
            reply_mode=reply_mode,
            draft_timeout_minutes=body.draft_timeout_minutes or 5,
            draft_timeout_action=draft_timeout_action,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return TopicBindingResponse(
        topicId=topic_id,
        agentId=ctx.agent_id,
        enabled=ctx.enabled,
        boundAt=ctx.bound_at,
        displayName=body.display_name,
        avatarUrl=body.avatar_url,
        threadSharingMode=ctx.thread_sharing_mode,
        replyMode=ctx.reply_mode.value,
        draftTimeoutMinutes=ctx.draft_timeout_minutes,
        draftTimeoutAction=ctx.draft_timeout_action.value,
    )


@router.post("/{channel}/default-agent", response_model=TopicBindingResponse)
async def set_channel_default_agent(
    channel: str,
    body: BindTopicRequest,
) -> TopicBindingResponse:
    """Set the default agent for an entire channel."""
    from app.core.channel_bridge.topic_config import SqlTopicManager
    from app.database.connection import get_session
    from app.services.agent.agent_service import AgentService

    if body.agent_id:
        async with get_session() as _db:
            agent = await AgentService.get_agent_by_id(body.agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")

            from app.core.channel_bridge import channel_gateway as gateway

            channel_caps = gateway.get_channel_capabilities(channel)

            meta_map = _as_meta_mapping(agent.metadata)
            if channel_caps and meta_map.get("required_capabilities") is not None:
                required_caps = _meta_str_list(meta_map, "required_capabilities")
                for cap in required_caps:
                    if not getattr(channel_caps, cap, False):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Channel '{channel}' does not support required capability '{cap}' for this Agent.",
                        )

    manager = SqlTopicManager()
    try:
        ctx = await manager.bind_topic(
            channel=channel,
            chat_id="__global__",
            thread_id=None,
            agent_id=body.agent_id,
            display_name=body.display_name,
            avatar_url=body.avatar_url,
            thread_sharing_mode=body.thread_sharing_mode or "isolated",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return TopicBindingResponse(
        topicId="__global__",
        agentId=ctx.agent_id,
        enabled=ctx.enabled,
        boundAt=ctx.bound_at,
        displayName=body.display_name,
        avatarUrl=body.avatar_url,
        threadSharingMode=body.thread_sharing_mode or "isolated",
    )
