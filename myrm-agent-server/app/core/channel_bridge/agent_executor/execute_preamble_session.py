"""Channel preamble session resolution and history loading.

[INPUT]
app.core.channel_bridge.executor_helpers (POS: 渠道历史持久化/加载)
execute_preamble_backfill (POS: 冷启动 backfill)

[OUTPUT]
resolve_channel_session_context(): session_key、历史、冷启动标记与 reset 预事件。

[POS]
execute_preamble 子模块：会话键解析、backfill、历史加载与 auto-reset 通知。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.channels.i18n import get_text
from app.channels.types import InboundMessage, OutboundMessage, ProgressUpdate, SessionResetMode, TopicContext
from app.channels.types.thread_sharing import ThreadSharingMode
from app.core.channel_bridge.config_parsers import SessionPolicy, session_policy_from_agent_dict
from app.core.channel_bridge.executor_helpers import (
    build_chat_history_with_metadata,
    load_history_without_persist,
    persist_and_load_history,
)
from app.services.agent.profile_resolver import ResolvedAgentProfile

from .execute_preamble_backfill import maybe_backfill_channel_history
from .session import resolve_session_key

if TYPE_CHECKING:
    from .executor import ChannelAgentExecutor

logger = logging.getLogger(__name__)


@dataclass
class ChannelSessionContext:
    session_key: str
    chat_id: str
    chat_history: list[object]
    session_was_auto_reset: bool
    session_policy: SessionPolicy
    query: str
    pre_events: tuple[ProgressUpdate | OutboundMessage, ...]


async def resolve_channel_session_context(
    executor: "ChannelAgentExecutor",
    msg: InboundMessage,
    *,
    query: str,
    is_resume: bool,
    topic_context: TopicContext | None,
    resolved_agent_id: str | None,
    resolved_profile: ResolvedAgentProfile | None,
    personal_settings_dict: dict[str, object] | None,
) -> ChannelSessionContext:
    pre_events: list[ProgressUpdate | OutboundMessage] = []

    session_policy = extract_session_policy_safe(personal_settings_dict)
    if resolved_profile and resolved_profile.session_policy and isinstance(resolved_profile.session_policy, dict):
        session_policy = session_policy_from_agent_dict(resolved_profile.session_policy)

    force_new = bool(msg.metadata.get("force_new_epoch"))
    thread_sharing_mode = topic_context.thread_sharing_mode if topic_context else ThreadSharingMode.ISOLATED
    session_key = await resolve_session_key(
        msg,
        session_policy,
        agent_id=resolved_agent_id,
        force_new_epoch=force_new,
        thread_sharing_mode=thread_sharing_mode,
    )

    is_cold_start = await _detect_cold_start(session_key)
    await maybe_backfill_channel_history(
        executor,
        msg,
        session_key=session_key,
        is_cold_start=is_cold_start,
        resolved_agent_id=resolved_agent_id,
    )

    session_was_auto_reset = (
        is_cold_start
        and not force_new
        and session_policy.mode != SessionResetMode.PERSISTENT
    )
    working_query = query
    if session_was_auto_reset and session_policy.notify_on_reset:
        context_note = (
            "[System note: This is a fresh conversation with no prior context. "
            "Do not reference any previous conversation.]"
        )
        working_query = f"{context_note}\n{query}"

        if session_policy.mode == SessionResetMode.IDLE:
            reset_label = get_text(
                msg, "session_reset_notify_idle",
                minutes=session_policy.idle_minutes,
            )
        else:
            reset_label = get_text(
                msg, "session_reset_notify_daily",
                hour=session_policy.daily_reset_hour,
            )
        pre_events.append(ProgressUpdate(label=reset_label))

    if is_resume:
        chat_id, history_entries = await load_history_without_persist(
            channel_session_key=session_key,
        )
    else:
        sent_at_utc = datetime.fromtimestamp(msg.sent_at, tz=timezone.utc)
        chat_id, history_entries = await persist_and_load_history(
            channel_session_key=session_key,
            source=msg.channel,
            content=msg.content,
            sent_at=sent_at_utc,
            sent_timezone=msg.sent_timezone,
            agent_id=resolved_agent_id,
        )

    chat_history = build_chat_history_with_metadata(history_entries)
    return ChannelSessionContext(
        session_key=session_key,
        chat_id=chat_id,
        chat_history=chat_history,
        session_was_auto_reset=session_was_auto_reset,
        session_policy=session_policy,
        query=working_query,
        pre_events=tuple(pre_events),
    )


def extract_session_policy_safe(personal_settings_dict: dict[str, object] | None) -> SessionPolicy:
    from app.core.channel_bridge.config_parsers import extract_session_policy

    return extract_session_policy(personal_settings_dict)


async def _detect_cold_start(session_key: str) -> bool:
    from app.services.chat.chat_service import ChatService

    try:
        existing_chat = await ChatService.get_channel_chat_by_key(session_key)
        if not existing_chat:
            return True
        existing_hist = await ChatService.load_channel_history(existing_chat.id, api_key=None)
        return not existing_hist
    except Exception as e:
        logger.warning("Error checking cold-start for session %s: %s", session_key, e)
        return False
