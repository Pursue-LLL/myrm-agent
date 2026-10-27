"""Forced direct delegation: a turn addressed to one named external agent runs there, or fails visibly.

[INPUT]
- myrm_agent_harness.agent.security.{config,engine,types} (POS: 权限策略评估) [lazy]
- app.services.external_agents.delegation::agent_unavailable_event, delegate_denied_event, delegate_failed_event (POS: 直连委托失败的用户指引)

[OUTPUT]
- stream_forced_delegate: 安全闸门 → 可用性检查 → 直连流式转发；每条失败路径都以带处置指引的错误事件结束
- denial_reason: 安全策略不让用户委托给该外部 Agent 的原因，允许则为 None

[POS]
`execute_stream_pipeline` 里 `force_external_agent` 分支（用户在输入框指定了某个外部 Agent）的实现。用户指定了
哪个 Agent 就只由它回答：被安全策略拦下、不可用、中途出意外，都明确报错，不换成主 Agent 或别的 Agent 作答。
用户的原话原样交给 CLI：这条路径不加给主 Agent 模型看的路由横幅，日志里也不记用户的消息内容。
"""

from __future__ import annotations

import logging
from contextlib import aclosing
from typing import TYPE_CHECKING

from app.services.external_agents.delegation import (
    agent_unavailable_event,
    delegate_denied_event,
    delegate_failed_event,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

    from app.ai_agents.general_agent.agent import GeneralAgent

logger = logging.getLogger(__name__)


def denial_reason(agent_wrapper: GeneralAgent, agent_name: str) -> str | None:
    """Why the security policy does not let this chat delegate to ``agent_name`` (None: it may)."""
    from myrm_agent_harness.agent.security.config import parse_security_config
    from myrm_agent_harness.agent.security.engine import evaluate_tool_call
    from myrm_agent_harness.agent.security.types import PermissionAction

    config = parse_security_config(agent_wrapper.security_config_raw)
    if config is None:
        return "invoke_external_agent denied: security config missing"
    action, reason = evaluate_tool_call("invoke_external_agent", {"agent": agent_name}, config)
    if action != PermissionAction.ALLOW:
        return reason or f"invoke_external_agent {action.value} by security policy"
    return None


async def stream_forced_delegate(
    agent_wrapper: GeneralAgent,
    query: object,
    agent_name: str,
    *,
    cancel_token: CancellationToken | None,
    chat_id: str | None,
) -> AsyncGenerator[dict[str, object]]:
    """Run the turn on ``agent_name`` and stream its events; any failure ends it with one guided error event."""
    locale = agent_wrapper.locale or "en"

    reason = denial_reason(agent_wrapper, agent_name)
    if reason:
        # The user is sent to the security settings; the policy engine's own wording stays in the log.
        logger.warning("Direct external delegate blocked by security policy: agent=%s reason=%s", agent_name, reason)
        yield delegate_denied_event(agent_name, locale)
        return

    if agent_wrapper._runtime_pool is None:
        await agent_wrapper._ensure_runtime_pool()
    pool = agent_wrapper._runtime_pool
    if pool is None or agent_name not in pool.available_backends:
        logger.warning("Direct external delegate unavailable: agent=%s", agent_name)
        yield agent_unavailable_event(agent_name, locale)
        return

    logger.info("Direct routing to external agent: agent=%s chat_id=%s", agent_name, chat_id or "")
    try:
        async with aclosing(
            agent_wrapper._direct_delegate_stream(agent_name, query, cancel_token=cancel_token, chat_id=chat_id)
        ) as delegate_events:
            async for event in delegate_events:
                yield event
    except Exception:
        logger.error("Direct delegate failed: agent=%s", agent_name, exc_info=True)
        yield delegate_failed_event(agent_name, locale)
