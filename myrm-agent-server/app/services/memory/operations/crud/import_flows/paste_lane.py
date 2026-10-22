"""Model-assisted paste lane for the import dry-run.

[INPUT]
app.services.memory.extract_retry.resolve_chat_extraction_llm (POS: 迁移导入抽取模型解析)
myrm_agent_harness.toolkits.memory.strategies.extractor (POS: 记忆抽取器)

[OUTPUT]
_is_paste_payload, _with_model_extracted_paste_items: enrich a paste payload with
model-extracted items, or flag the deterministic fallback.

[POS]
Optional capability of the paste lane: it never writes anything and never
bypasses the review session, and it degrades to the deterministic parser when no
model is configured, the text exceeds the budget, or extraction fails.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Model extraction is a single LLM call, so the pasted text is only sent when it
# fits a bounded budget; longer pastes keep the deterministic parser instead of
# risking a failed or oversized call.
_MODEL_EXTRACTION_MAX_CHARS = 40_000


def _is_paste_payload(payload: dict[str, object], source: str) -> bool:
    """True when the payload is the wizard paste lane (free text, no discovery)."""

    if source == "pasted_memory":
        return True
    text = payload.get("text")
    return source == "auto" and isinstance(text, str) and bool(text.strip())


async def _with_model_extracted_paste_items(
    payload: dict[str, object],
    *,
    agent_id: str | None,
) -> dict[str, object]:
    """Return the paste payload enriched with model-extracted items.

    The model is optional by design: when nothing is configured, the call fails
    or it finds no memories, the payload keeps its deterministic path and gains
    the ``pasted_model_extraction_failed`` warning so the user is told why.
    """

    from app.services.memory.extract_retry.resolve_chat_extraction_llm import (
        resolve_import_extraction_llm,
    )
    from app.services.memory.imports.import_pasted_model import MODEL_BUCKETS

    enriched = dict(payload)
    text = str(payload.get("text", "")).strip()
    if not text:
        return enriched
    if len(text) > _MODEL_EXTRACTION_MAX_CHARS:
        enriched["_model_extraction_failed"] = True
        return enriched

    from langchain_core.messages import HumanMessage, SystemMessage
    from myrm_agent_harness.toolkits.memory.strategies.extractor import (
        extract_memories_from_conversation,
    )
    from myrm_agent_harness.utils.chat_utils import extract_answer_text

    llm = await resolve_import_extraction_llm(agent_id)
    if llm is None:
        enriched["_model_extraction_failed"] = True
        return enriched

    async def _complete(system_prompt: str, user_prompt: str) -> str:
        response = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
        )
        return extract_answer_text(response)

    try:
        extraction = await extract_memories_from_conversation(
            [{"role": "user", "content": text}],
            _complete,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Model-assisted paste extraction failed: %s", exc)
        enriched["_model_extraction_failed"] = True
        return enriched

    items = [
        {
            "content": memory.content,
            "bucket": memory.memory_type.value,
            "importance": memory.importance,
            "confidence": memory.confidence,
            "profile_key": memory.profile_key,
            "profile_value": memory.profile_value,
            "trigger": memory.trigger,
        }
        for memory in extraction.memories
        if memory.memory_type.value in MODEL_BUCKETS and memory.content.strip()
    ]
    if not items:
        enriched["_model_extraction_failed"] = True
        return enriched

    enriched["_model_items"] = items
    return enriched
