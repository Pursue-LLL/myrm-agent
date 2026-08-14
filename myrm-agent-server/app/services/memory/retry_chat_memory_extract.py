"""Retry memory extraction for one chat turn (GUI manual recovery + auto queue).

[INPUT]
app.services.chat.chat_service::ChatService (POS: chat metadata)
app.services.context.context_assembly::ContextAssemblyService (POS: chat memory binding SSOT)
app.services.memory.resolve_chat_extraction_llm::resolve_chat_extraction_llm (POS: extraction LLM SSOT)
app.services.memory.extract_retry_queue::enqueue (POS: 持久化重试队列)
myrm_agent_harness.api.hooks::auto_extract_memories (POS: harness extract)
app.ai_agents.extensions.extraction_lifecycle::make_extraction_lifecycle_observer (POS: ledger bridge)
app.core.channel_bridge.config_loader::load_user_configs (POS: 用户 personalSettings 配置)

[OUTPUT]
schedule_retry_chat_memory_extract: 幂等入队手动重试，返回 `scheduled` 或 `already_in_flight`。
run_retry_extract_for_chat: 对最新 user/assistant turn 执行压缩轨提取（worker 与手动共用，
手动 source=`manual_retry_extract`，worker 传 `worker_retry_extract`）。

[POS]
Business-layer recovery for failed memory extraction. Enqueues durable tasks consumed
by the background worker, reusing harness extract with factory-aligned memory binding
and extraction LLM. Retries run compressed-track only (enable_verbatim=False) to avoid
duplicating verbatim chunks that the original auto-extract already stored.
When privacy is enabled, the extraction task re-establishes the harness privacy
context (policy + PseudonymStore + regex PII pseudonymizer) so retried memories
are protected exactly like the agent-run path. When the user has additionally
enabled deep PII scan (privacyDeepScan), LLM-based deep scan also applies.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from myrm_agent_harness.agent.security.types import PIIAction
from myrm_agent_harness.utils.chat_utils import ChatHistoryReq

from app.database.dto import MessageDTO
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)

RetryScheduleStatus = Literal["scheduled", "already_in_flight"]


def _safe_pii_action(value: object, default: PIIAction) -> PIIAction:
    """Coerce a persisted PII action string to a valid enum value.

    Falls back to *default* for missing or invalid values so a stale/foreign
    configuration cannot crash the extraction task.
    """
    if value is None:
        return default
    try:
        return PIIAction(str(value))
    except ValueError:
        logger.warning(
            "Invalid PII action %r, falling back to %s", value, default.value
        )
        return default


@contextmanager
def _privacy_deep_scan_context(
    personal_settings: dict[str, object] | None,
    workspace_path: str | None,
) -> Iterator[bool]:
    """Bridge user privacy settings into the harness privacy context.

    When privacy is enabled it installs the PrivacyPolicy and, when S2/S3 use
    PSEUDONYMIZE, the shared PseudonymStore plus the regex PII pseudonymizer so
    retried memory writes are protected exactly like the agent-run path. Yields
    True when LLM-based deep PII scan should also run; on exit the previous
    context is restored so background tasks never leak privacy state across chats.
    """
    from myrm_agent_harness.agent.security.types import PIIAction, PrivacyPolicy
    from myrm_agent_harness.api.hooks import (
        build_pseudonym_store,
        get_privacy_policy,
        get_pseudonym_store,
        install_memory_pseudonymizer,
        restore_memory_pseudonymizer,
        set_privacy_policy,
        set_pseudonym_store,
    )

    settings = personal_settings if isinstance(personal_settings, dict) else {}
    enabled = bool(settings.get("privacyEnabled"))
    deep_scan = bool(settings.get("privacyDeepScan"))
    if not enabled:
        yield False
        return

    policy = PrivacyPolicy(
        enabled=True,
        s2_action=_safe_pii_action(settings.get("privacyS2Action"), PIIAction.WARN),
        s3_action=_safe_pii_action(settings.get("privacyS3Action"), PIIAction.REDACT),
        deep_scan=deep_scan,
    )
    previous_policy = get_privacy_policy()
    previous_store = get_pseudonym_store()
    set_privacy_policy(policy)
    previous_pseudonymizer = None
    store_installed = False
    try:
        needs_store = (
            policy.s2_action == PIIAction.PSEUDONYMIZE
            or policy.s3_action == PIIAction.PSEUDONYMIZE
        )
        if needs_store:
            if workspace_path:
                db_path = str(Path(workspace_path).parent / "pseudonym_store.db")
                store = build_pseudonym_store(db_path)
                set_pseudonym_store(store)
                store_installed = True
                previous_pseudonymizer = install_memory_pseudonymizer(policy, store)
            else:
                logger.warning(
                    "Deep PII scan skipped for retry: no workspace path for pseudonym store"
                )
        yield deep_scan
    finally:
        if previous_pseudonymizer is not None:
            restore_memory_pseudonymizer(previous_pseudonymizer)
        set_privacy_policy(previous_policy)
        if store_installed:
            set_pseudonym_store(previous_store)


def _time_decay_half_life_days(memory_decay_profile: str | None) -> float:
    if memory_decay_profile == "permanent":
        return 3650.0
    if memory_decay_profile == "fast":
        return 7.0
    return 90.0


def _find_last_turn(
    messages: list[MessageDTO],
) -> tuple[MessageDTO, MessageDTO, ChatHistoryReq]:
    active = [message for message in messages if message.is_active]
    last_user_index = -1
    for index, message in enumerate(active):
        if message.role == "user":
            last_user_index = index

    if last_user_index < 0:
        raise ValueError("No user message found for memory retry")

    last_user = active[last_user_index]
    last_assistant = next(
        (
            message
            for message in active[last_user_index + 1 :]
            if message.role == "assistant"
        ),
        None,
    )
    if last_assistant is None:
        raise ValueError("No assistant reply found for memory retry")

    history: ChatHistoryReq = []
    for message in active[:last_user_index]:
        role = "human" if message.role == "user" else "assistant"
        history.append([role, message.content or ""])

    return last_user, last_assistant, history


async def _run_retry_extract(
    chat_id: str,
    query: str,
    history: ChatHistoryReq,
    assistant_reply: str,
    *,
    source: str,
    workspace_path: str | None,
) -> None:
    from myrm_agent_harness.api.hooks import auto_extract_memories

    from app.ai_agents.extensions.extraction_lifecycle import (
        make_extraction_lifecycle_observer,
    )
    from app.core.memory.adapters.setup import (
        create_conflict_callback,
        create_memory_manager,
    )
    from app.services.agent.platform_config import require_platform_embedding_config
    from app.services.context.context_assembly import ContextAssemblyService
    from app.services.memory.resolve_chat_extraction_llm import (
        resolve_chat_extraction_llm,
    )

    binding_context = await ContextAssemblyService.resolve_binding_for_chat(chat_id)
    llm, extraction_llm = await resolve_chat_extraction_llm(chat_id)

    embedding_cfg = await require_platform_embedding_config()
    memory_manager = await create_memory_manager(
        binding_context.binding,
        embedding_cfg,
        approval_required=False,
        dedup_llm=extraction_llm,
        time_decay_half_life_days=_time_decay_half_life_days(
            binding_context.memory_decay_profile
        ),
        on_conflict=create_conflict_callback(agent_id=binding_context.agent_id),
    )

    from app.core.channel_bridge.config_loader import load_user_configs

    configs = await load_user_configs()
    with _privacy_deep_scan_context(
        configs.personal_settings_dict if configs else None,
        workspace_path,
    ) as deep_scan:
        await auto_extract_memories(
            query,
            history,
            memory_manager,
            llm,
            extraction_llm=extraction_llm,
            source_chat_id=chat_id,
            assistant_reply=assistant_reply,
            enable_verbatim=False,
            deep_scan=deep_scan,
            lifecycle_observer=make_extraction_lifecycle_observer(
                chat_id,
                source=source,
                is_retry=True,
            ),
        )


async def run_retry_extract_for_chat(
    chat_id: str, *, source: str = "manual_retry_extract"
) -> bool:
    """Run compressed-track extraction for a chat's latest turn.

    Returns True when extraction was attempted; False when there is nothing to retry
    (chat gone or no complete user/assistant turn).
    """
    chat = await ChatService.get_chat_metadata(chat_id)
    if chat is None:
        return False

    messages = await ChatService.get_all_messages(chat_id)
    if not messages:
        return False

    try:
        last_user, last_assistant, history = _find_last_turn(messages)
    except ValueError:
        return False

    await _run_retry_extract(
        chat_id,
        last_user.content or "",
        history,
        last_assistant.content or "",
        source=source,
        workspace_path=chat.workspace_dir or chat.sandbox_base_dir,
    )
    return True


async def schedule_retry_chat_memory_extract(chat_id: str) -> RetryScheduleStatus:
    """Enqueue a durable background retry for the latest active user/assistant turn."""
    resolved_chat_id = chat_id.strip()
    if not resolved_chat_id:
        raise ValueError("Chat id is required")

    chat = await ChatService.get_chat_metadata(resolved_chat_id)
    if chat is None:
        raise ValueError("Chat not found")
    if chat.is_incognito:
        raise ValueError("Incognito chats do not support memory extraction retry")

    messages = await ChatService.get_all_messages(resolved_chat_id)
    if not messages:
        raise ValueError("Chat has no messages")

    # Fail fast on malformed turns; the worker re-resolves the latest turn at run time.
    _find_last_turn(messages)

    from app.services.memory.extract_retry_queue import enqueue

    result = await enqueue(resolved_chat_id, reset_failed=True)
    if result == "queued":
        from app.services.memory.extract_retry_worker import extract_retry_worker

        extract_retry_worker.wake()
    logger.info("Memory extract retry enqueued for chat %s: %s", resolved_chat_id, result)
    return "already_in_flight" if result == "already_queued" else "scheduled"


__all__ = [
    "RetryScheduleStatus",
    "run_retry_extract_for_chat",
    "schedule_retry_chat_memory_extract",
]
