"""Chat message → Wiki pending compound SSOT (server business layer).

[INPUT]
- app.services.chat.chat_service::ChatService (POS: chat message persistence)
- myrm_agent_harness.toolkits.wiki.pipeline.chat_compound (POS: pending draft staging)
- app.services.wiki.memory_to_wiki::MemoryToWikiArchiver (POS: vault + pending manager)

[OUTPUT]
- stage_chat_compound_from_message(): load assistant message from DB and stage pending edit
- ChatCompoundServiceError: structured failures for REST mapping
- load_assistant_message(): reject missing/inactive/incognito/non-assistant messages

[POS]
Server-side SSOT for POST /wiki/compound. Hydrates Q&A and trust signals from persisted
messages; REST callers must not supply assistant body or trust hints.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.toolkits.wiki.pipeline.chat_compound import (
    ChatCompoundError,
    ChatCompoundRequest,
    ChatCompoundResult,
    ChatCompoundTrustContext,
    stage_chat_compound,
)
from myrm_agent_harness.utils.text_sanitizer import extract_and_strip_think_blocks

from app.database.dto import MessageDTO
from app.services.chat.chat_service import ChatService
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver

_NO_PRECEDING_USER = "(No preceding user message captured)"


@dataclass(frozen=True, slots=True)
class ChatCompoundServiceError(Exception):
    """Structured chat compound failure for REST callers."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def _extract_knowledge_sources(extra_data: dict[str, object] | None) -> list[dict[str, object]]:
    if not extra_data:
        return []
    raw_sources = extra_data.get("sources")
    if not isinstance(raw_sources, list):
        return []
    knowledge: list[dict[str, object]] = []
    for item in raw_sources:
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "knowledge":
            knowledge.append(item)
    return knowledge


def build_trust_context(extra_data: dict[str, object] | None) -> ChatCompoundTrustContext:
    """Derive wiki trust signals from persisted message citation metadata."""
    knowledge_sources = _extract_knowledge_sources(extra_data)
    has_verified = any(
        str(source.get("snapshot_status") or "").strip() == "verified"
        for source in knowledge_sources
    )
    return ChatCompoundTrustContext(
        has_knowledge_sources=bool(knowledge_sources),
        has_verified_snapshot=has_verified,
    )


def resolve_preceding_user_question(
    messages: list[MessageDTO],
    assistant_message_id: str,
) -> str:
    """Return the nearest preceding non-empty user message before the assistant reply."""
    assistant_index = next(
        (index for index, message in enumerate(messages) if message.id == assistant_message_id),
        None,
    )
    if assistant_index is None:
        return _NO_PRECEDING_USER
    for index in range(assistant_index - 1, -1, -1):
        candidate = messages[index]
        if candidate.role == "user" and candidate.content.strip():
            return candidate.content.strip()
    return _NO_PRECEDING_USER


def normalize_assistant_content(content: str) -> str:
    """Strip think blocks using the same sanitizer as chat message APIs."""
    normalized, _ = extract_and_strip_think_blocks(content)
    return normalized.strip()


async def load_assistant_message(chat_id: str, message_id: str) -> MessageDTO:
    """Load and validate the assistant message referenced by a compound request."""
    chat = await ChatService.get_chat_metadata(chat_id)
    if chat is None:
        raise ChatCompoundServiceError("message_not_found", "Chat session not found")
    if chat.is_incognito:
        raise ChatCompoundServiceError(
            "incognito_forbidden",
            "Incognito chats cannot be compounded into the wiki",
        )

    message = await ChatService.get_message_by_id(chat_id, message_id)
    if message is None:
        raise ChatCompoundServiceError("message_not_found", "Chat message not found")
    if not message.is_active:
        raise ChatCompoundServiceError(
            "message_not_found",
            "Chat message is no longer active",
        )
    if message.role != "assistant":
        raise ChatCompoundServiceError(
            "invalid_role",
            "Only assistant messages can be compounded into wiki pending edits",
        )

    assistant_content = normalize_assistant_content(message.content)
    if not assistant_content:
        raise ChatCompoundServiceError(
            "invalid_request",
            "Assistant message has no compoundable content",
        )
    return message


async def stage_chat_compound_from_message(
    archiver: MemoryToWikiArchiver,
    *,
    concept_name: str,
    source_chat: str,
    source_message: str,
) -> ChatCompoundResult:
    """Stage a chat assistant message into wiki pending edits using DB SSOT."""
    assistant_message = await load_assistant_message(source_chat.strip(), source_message.strip())
    assistant_content = normalize_assistant_content(assistant_message.content)
    all_messages = await ChatService.get_all_messages(source_chat.strip())
    user_question = resolve_preceding_user_question(all_messages, assistant_message.id)
    trust = build_trust_context(assistant_message.extra_data)

    compound_request = ChatCompoundRequest(
        concept_name=concept_name.strip(),
        user_question=user_question,
        assistant_answer=assistant_content,
        source_chat=source_chat.strip(),
        source_message=source_message.strip(),
        trust=trust,
    )
    try:
        return await stage_chat_compound(
            archiver._structure,
            archiver._query_engine._indexer,
            archiver._pending_mgr,
            compound_request,
        )
    except ChatCompoundError as exc:
        raise ChatCompoundServiceError(exc.code, exc.message) from exc
