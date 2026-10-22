"""Cited-memory influence evidence for the memory command center.

[INPUT]
app.database.models.chat::Message (POS: 会话消息 ORM)
app.schemas.memory.command_center::MemoryCommandInfluenceItem, MemoryCommandInfluenceRef (POS: 记忆指挥中心 API Schema 层)
app.services.memory.command_center.command_center_projection_utils::dict_int, optional_float, optional_str, preview_content (POS: 指挥中心轻量解析)

[OUTPUT]
load_influence: recent assistant answers that cite memories, with token usage and cache hits.

[POS]
个人大脑指挥中心的影响证据投影。从消息 extra_data 的 citedMemoryRefs 与 usage / tokenEconomics / contextBudget 提取「哪些记忆影响了哪条回答」及其注入成本。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chat import Message
from app.schemas.memory.command_center import MemoryCommandInfluenceItem, MemoryCommandInfluenceRef
from app.services.memory.command_center.command_center_projection_utils import (
    dict_int,
    optional_float,
    optional_str,
    preview_content,
)

_MESSAGE_SCAN_LIMIT = 40
_INFLUENCE_ITEM_LIMIT = 8


async def load_influence(db: AsyncSession) -> list[MemoryCommandInfluenceItem]:
    result = await db.execute(
        select(Message).where(Message.extra_data.is_not(None)).order_by(Message.created_at.desc()).limit(_MESSAGE_SCAN_LIMIT)
    )
    items: list[MemoryCommandInfluenceItem] = []
    for message in result.scalars().all():
        extra_data = message.extra_data or {}
        refs = _extract_influence_refs(extra_data)
        if not refs:
            continue
        prompt_tokens, cached_tokens, _completion_tokens = _extract_token_counts(extra_data)
        items.append(
            MemoryCommandInfluenceItem(
                id=f"message:{message.id}",
                chat_id=message.chat_id,
                message_id=message.id,
                occurred_at=message.created_at,
                answer_preview=preview_content(message.content, limit=220),
                influence_refs=refs,
                prompt_tokens=prompt_tokens,
                cached_tokens=cached_tokens,
            )
        )
        if len(items) >= _INFLUENCE_ITEM_LIMIT:
            break
    return items


def _extract_influence_refs(extra_data: dict[str, object]) -> list[MemoryCommandInfluenceRef]:
    raw_refs = extra_data.get("citedMemoryRefs")
    if not isinstance(raw_refs, list):
        return []
    refs: list[MemoryCommandInfluenceRef] = []
    for raw_ref in raw_refs:
        if not isinstance(raw_ref, dict):
            continue
        memory_id = raw_ref.get("id")
        memory_type = raw_ref.get("memory_type")
        if not isinstance(memory_id, str) or not isinstance(memory_type, str):
            continue
        primary_namespace = optional_str(raw_ref.get("primary_namespace"))
        raw_namespaces = raw_ref.get("namespaces")
        if primary_namespace is None and isinstance(raw_namespaces, list) and raw_namespaces:
            primary_namespace = optional_str(raw_namespaces[0])
        refs.append(
            MemoryCommandInfluenceRef(
                memory_id=memory_id,
                memory_type=memory_type,
                score=optional_float(raw_ref.get("score")),
                content_preview=preview_content(str(raw_ref.get("content") or ""), limit=180),
                primary_namespace=primary_namespace,
                source_chat_id=optional_str(raw_ref.get("source_chat_id")),
                source_message_id=optional_str(raw_ref.get("source_message_id")),
                reason="memory_search_tool",
            )
        )
    return refs


def _extract_token_counts(extra_data: dict[str, object]) -> tuple[int, int, int]:
    usage = extra_data.get("usage")
    token_economics = extra_data.get("tokenEconomics")
    context_budget = extra_data.get("contextBudget")
    prompt_tokens = dict_int(usage, "prompt_tokens") + dict_int(token_economics, "prompt_tokens")
    cached_tokens = dict_int(usage, "cached_tokens") + dict_int(token_economics, "cached_tokens")
    completion_tokens = dict_int(usage, "completion_tokens") + dict_int(token_economics, "completion_tokens")
    if prompt_tokens == 0:
        prompt_tokens = dict_int(context_budget, "used_tokens")
    return (prompt_tokens, cached_tokens, completion_tokens)
