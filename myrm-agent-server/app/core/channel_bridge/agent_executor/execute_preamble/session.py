"""Channel preamble session resolution and history loading.

[INPUT]
app.core.channel_bridge.executor_helpers (POS: 渠道历史持久化/加载)
backfill (POS: 冷启动 backfill)

[OUTPUT]
resolve_channel_session_context(): session_key、历史、冷启动标记与 reset 预事件。

[POS]
preamble 子模块：会话键解析、backfill、历史加载与 auto-reset 通知。审批续跑回合不重算会话键：沿用提问回合的会话
（``METADATA_RESUME_SESSION_KEY``），不落库、不 backfill、不播报 reset；该会话的聊天已不存在时如实答复。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.channels.i18n import get_text
from app.channels.types import (
    METADATA_RESUME_SESSION_KEY,
    InboundMessage,
    OutboundMessage,
    ProgressUpdate,
    SessionPolicy,
    SessionResetMode,
    TopicContext,
)
from app.channels.types.thread_sharing import ThreadSharingMode
from app.core.channel_bridge.config_parsers import session_policy_from_agent_dict
from app.core.channel_bridge.executor_helpers import (
    ChannelChatHistory,
    build_chat_history_with_metadata,
    load_history_without_persist,
    persist_and_load_history,
)
from app.core.channel_bridge.executor_helpers.topic_workspace_sync import ChannelWorkspaceSyncError
from app.services.agent.profile.profile_resolver import ResolvedAgentProfile

from ..execute_errors import build_early_failure_reply
from ..session import resolve_session_key
from .backfill import maybe_backfill_channel_history

if TYPE_CHECKING:
    from ..executor import ChannelAgentExecutor

logger = logging.getLogger(__name__)


@dataclass
class ChannelSessionContext:
    session_key: str
    chat_id: str
    chat_history: ChannelChatHistory
    session_was_auto_reset: bool
    session_policy: SessionPolicy
    query: str | list[dict[str, object]]
    pre_events: tuple[ProgressUpdate | OutboundMessage, ...]


async def resolve_channel_session_context(
    executor: "ChannelAgentExecutor",
    msg: InboundMessage,
    *,
    query: str | list[dict[str, object]],
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

    asked_session_key = _asking_turn_session_key(msg) if is_resume else None
    if asked_session_key is not None:
        return await _continue_asking_session(
            msg, asked_session_key, query=query, topic_context=topic_context, session_policy=session_policy
        )

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

    session_was_auto_reset = is_cold_start and not force_new and session_policy.mode != SessionResetMode.PERSISTENT
    working_query: str | list[dict[str, object]] = query
    if session_was_auto_reset and session_policy.notify_on_reset:
        context_note = (
            "[System note: This is a fresh conversation with no prior context. Do not reference any previous conversation.]"
        )
        if isinstance(query, str):
            working_query = f"{context_note}\n{query}"
        else:
            head_part: dict[str, object] = {"type": "text", "text": context_note}
            working_query = [head_part, *query]

        if session_policy.mode == SessionResetMode.IDLE:
            reset_label = get_text(
                msg,
                "session_reset_notify_idle",
                minutes=session_policy.idle_minutes,
            )
        else:
            reset_label = get_text(
                msg,
                "session_reset_notify_daily",
                hour=session_policy.daily_reset_hour,
            )
        pre_events.append(ProgressUpdate(label=reset_label))

    if is_resume:
        try:
            chat_id, history_entries = await load_history_without_persist(
                channel_session_key=session_key,
                topic_context=topic_context,
            )
        except ChannelWorkspaceSyncError as exc:
            logger.warning("Workspace sync failed for channel session: %s", exc)
            pre_events.append(_workspace_unavailable_reply(msg))
            return ChannelSessionContext(
                session_key=session_key,
                chat_id="",
                chat_history=[],
                session_was_auto_reset=session_was_auto_reset,
                session_policy=session_policy,
                query=working_query,
                pre_events=tuple(pre_events),
            )
    else:
        sent_at_utc = datetime.fromtimestamp(msg.sent_at, tz=timezone.utc)
        try:
            chat_id, history_entries = await persist_and_load_history(
                channel_session_key=session_key,
                source=msg.channel,
                content=msg.content,
                sent_at=sent_at_utc,
                sent_timezone=msg.sent_timezone,
                agent_id=resolved_agent_id,
                topic_context=topic_context,
            )
        except ChannelWorkspaceSyncError as exc:
            logger.warning("Workspace sync failed for channel session: %s", exc)
            pre_events.append(_workspace_unavailable_reply(msg))
            return ChannelSessionContext(
                session_key=session_key,
                chat_id="",
                chat_history=[],
                session_was_auto_reset=session_was_auto_reset,
                session_policy=session_policy,
                query=working_query,
                pre_events=tuple(pre_events),
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


def _asking_turn_session_key(msg: InboundMessage) -> str | None:
    """The channel session key of the turn that asked for the approval this message resumes; None when it named none."""
    key = msg.metadata.get(METADATA_RESUME_SESSION_KEY)
    return key if isinstance(key, str) and key else None


def _workspace_unavailable_reply(msg: InboundMessage) -> OutboundMessage:
    return build_early_failure_reply(
        msg,
        get_text(msg, "topic_workspace_unavailable", error="workspace sync failed"),
        "workspace_unavailable",
    )


async def _continue_asking_session(
    msg: InboundMessage,
    session_key: str,
    *,
    query: str | list[dict[str, object]],
    topic_context: TopicContext | None,
    session_policy: SessionPolicy,
) -> ChannelSessionContext:
    """The context of a resume turn: the session of the turn that asked, as that turn left it.

    The asking turn stored the member's message and opened the session, so nothing is stored, backfilled or announced
    as a reset here. A chat that no longer exists ends the turn with a reply that says so; the run cannot continue.
    """
    chat_id = ""
    chat_history: ChannelChatHistory = []
    pre_events: tuple[ProgressUpdate | OutboundMessage, ...] = ()
    try:
        chat_id, history_entries = await load_history_without_persist(
            channel_session_key=session_key,
            topic_context=topic_context,
        )
    except ChannelWorkspaceSyncError as exc:
        logger.warning("Workspace sync failed for channel session: %s", exc)
        pre_events = (_workspace_unavailable_reply(msg),)
    else:
        if chat_id:
            chat_history = build_chat_history_with_metadata(history_entries)
        else:
            pre_events = (build_early_failure_reply(msg, get_text(msg, "approval_session_gone"), "approval_session_gone"),)
    return ChannelSessionContext(
        session_key=session_key,
        chat_id=chat_id,
        chat_history=chat_history,
        session_was_auto_reset=False,
        session_policy=session_policy,
        query=query,
        pre_events=pre_events,
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
