"""RetryHandler / UndoHandler implementations for IM /retry and /undo commands.

[INPUT]
- app.channels.protocols.turn_management::RetryHandler, RetryResult, UndoHandler, UndoResult
- app.channels.types::InboundMessage
- app.core.channel_bridge.agent_executor::resolve_session_key
- app.core.channel_bridge.config_loader::load_user_configs
- app.core.channel_bridge.config_parsers::extract_session_policy, session_policy_from_agent_dict
- app.database.connection::get_session
- app.services.chat.chat_service::ChatService
- app.services.files.revert_hydrate::cleanup_persisted_snapshots (POS: Server-side revert snapshot disk hydrate and cleanup)
- myrm_agent_harness.agent.meta_tools.file_ops.revert_service::RevertService

[OUTPUT]
- ChannelRetryHandler: RetryHandler 业务实现
- ChannelUndoHandler: UndoHandler 业务实现
- _revert_messages: best-effort file revert + restore_inbox notify

[POS]
将框架层的 RetryHandler / UndoHandler 协议映射到 ChatService 的
retry_last_turn / undo_last_turn 方法，并联动 RevertService 还原关联文件快照。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from myrm_agent_harness.agent.meta_tools.file_ops.revert_service import RevertService

from app.channels.protocols.turn_management import RetryResult, UndoResult
from app.channels.types import InboundMessage, SessionPolicy
from app.core.channel_bridge.agent_executor import resolve_session_key
from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_parsers import (
    extract_session_policy,
    session_policy_from_agent_dict,
)
from app.database.connection import get_session
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RevertMessagesOutcome:
    reverted_count: int
    not_revertible_count: int


async def _resolve_session_with_agent(msg: InboundMessage) -> tuple[str, str | None]:
    """Resolve session key and agent_id, respecting per-agent session policy."""
    configs = await load_user_configs()
    session_policy = SessionPolicy()
    if configs.personal_settings_dict:
        session_policy = extract_session_policy(configs.personal_settings_dict)

    from app.core.channel_bridge.compact_handler import ChannelCompactHandler

    agent_id = await ChannelCompactHandler._resolve_bound_agent_id(msg)

    if agent_id:
        from app.services.agent.profile_resolver import get_agent_profile_resolver

        profile = await get_agent_profile_resolver().resolve(agent_id)
        if profile and profile.session_policy and isinstance(profile.session_policy, dict):
            session_policy = session_policy_from_agent_dict(profile.session_policy)

    session_key = await resolve_session_key(msg, session_policy, agent_id=agent_id)
    return session_key, agent_id


async def _revert_messages(session_id: str, message_ids: list[str]) -> RevertMessagesOutcome:
    """Best-effort revert file snapshots for deleted messages."""
    from app.services.files.revert_hydrate import (
        cleanup_persisted_snapshots,
        ensure_session_snapshots_hydrated,
    )

    await ensure_session_snapshots_hydrated(session_id)

    reverted_total = 0
    not_revertible_total = 0
    reverted_paths: list[str] = []
    for mid in message_ids:
        try:
            changes = await RevertService.get_message_changes(session_id, mid)
            not_revertible_paths = {c.path for c in changes if not c.revertible}
            not_revertible_total += len(not_revertible_paths)

            result = await RevertService.revert_message(session_id, mid)
            reverted_total += len(result.reverted_files)
            if result.reverted_files:
                reverted_paths.extend(result.reverted_files)
                await cleanup_persisted_snapshots(session_id, mid)
            if result.warnings:
                logger.debug("Revert warnings for message %s: %s", mid, result.warnings)
        except Exception:
            logger.warning("Failed to revert snapshots for message %s", mid, exc_info=True)

    if reverted_paths:
        from app.services.files.revert_agent_notify import notify_agent_of_turn_revert

        notify_agent_of_turn_revert(
            session_id=session_id,
            message_id=None,
            reverted_files=list(dict.fromkeys(reverted_paths)),
        )

    return RevertMessagesOutcome(
        reverted_count=reverted_total,
        not_revertible_count=not_revertible_total,
    )


class ChannelRetryHandler:
    """Business-layer RetryHandler for /retry command."""

    async def __call__(self, msg: InboundMessage, user_id: str) -> RetryResult:
        session_key, _ = await _resolve_session_with_agent(msg)

        async with get_session() as _db:
            chat = await ChatService.get_channel_chat_by_key("sandbox", session_key)
            if not chat:
                return RetryResult(success=False)
            svc_result = await ChatService.retry_last_turn(chat.id, "sandbox")

        revert_outcome = RevertMessagesOutcome(reverted_count=0, not_revertible_count=0)
        if svc_result.success and svc_result.deleted_message_ids:
            revert_outcome = await _revert_messages(chat.id, svc_result.deleted_message_ids)
            if revert_outcome.reverted_count:
                logger.info(
                    "ChannelRetryHandler: reverted %d files for chat %s",
                    revert_outcome.reverted_count,
                    chat.id,
                )

        return RetryResult(
            success=svc_result.success,
            query=svc_result.query,
            deleted_count=svc_result.deleted_count,
            reverted_count=revert_outcome.reverted_count,
            files_not_revertible=revert_outcome.not_revertible_count,
        )


class ChannelUndoHandler:
    """Business-layer UndoHandler for /undo command."""

    async def __call__(self, msg: InboundMessage, user_id: str) -> UndoResult:
        session_key, _ = await _resolve_session_with_agent(msg)

        async with get_session() as _db:
            chat = await ChatService.get_channel_chat_by_key("sandbox", session_key)
            if not chat:
                return UndoResult(success=False)
            svc_result = await ChatService.undo_last_turn(chat.id, "sandbox")

        revert_outcome = RevertMessagesOutcome(reverted_count=0, not_revertible_count=0)
        if svc_result.success and svc_result.deleted_message_ids:
            revert_outcome = await _revert_messages(chat.id, svc_result.deleted_message_ids)
            if revert_outcome.reverted_count:
                logger.info(
                    "ChannelUndoHandler: reverted %d files for chat %s",
                    revert_outcome.reverted_count,
                    chat.id,
                )

        return UndoResult(
            success=svc_result.success,
            deleted_count=svc_result.deleted_count,
            reverted_count=revert_outcome.reverted_count,
            files_not_revertible=revert_outcome.not_revertible_count,
        )
