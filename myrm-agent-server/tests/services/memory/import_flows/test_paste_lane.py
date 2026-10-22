"""Coverage for the optional model-assisted paste lane."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.memory import MemoryType

from app.services.memory.operations.crud.import_flows.dry_run_preview import (
    _COMPETITOR_AVG_SKILL_TOKENS,
    _MYRM_AVG_INDEX_TOKENS,
)
from app.services.memory.operations.crud.import_flows.paste_lane import (
    _is_paste_payload,
    _with_model_extracted_paste_items,
)


def _memory(
    memory_type: MemoryType,
    content: str,
    *,
    importance: float = 0.5,
    confidence: float = 0.5,
) -> SimpleNamespace:
    return SimpleNamespace(
        memory_type=memory_type,
        content=content,
        importance=importance,
        confidence=confidence,
        profile_key=None,
        profile_value=None,
        trigger=None,
    )


def test_paste_payload_detection() -> None:
    assert _is_paste_payload({"text": "hello"}, "auto") is True
    assert _is_paste_payload({"text": "   "}, "auto") is False
    assert _is_paste_payload({"text": "hello"}, "pasted_memory") is True
    assert _is_paste_payload({}, "auto") is False


@pytest.mark.asyncio
async def test_paste_model_lane_degrades_without_text_model_or_budget() -> None:
    empty = await _with_model_extracted_paste_items({"text": "  "}, agent_id=None)
    assert "_model_extraction_failed" not in empty

    oversized = await _with_model_extracted_paste_items({"text": "x" * 40_001}, agent_id=None)
    assert oversized["_model_extraction_failed"] is True

    no_model = AsyncMock(return_value=None)
    with patch(
        "app.services.memory.extract_retry.resolve_chat_extraction_llm.resolve_import_extraction_llm",
        no_model,
    ):
        missing = await _with_model_extracted_paste_items({"text": "## FACTS\n- x"}, agent_id=None)
    assert missing["_model_extraction_failed"] is True
    no_model.assert_awaited_once_with(None)


@pytest.mark.asyncio
async def test_paste_model_lane_flags_extraction_failures() -> None:
    with (
        patch(
            "app.services.memory.extract_retry.resolve_chat_extraction_llm.resolve_import_extraction_llm",
            AsyncMock(return_value=object()),
        ),
        patch(
            "myrm_agent_harness.toolkits.memory.strategies.extractor.extract_memories_from_conversation",
            AsyncMock(side_effect=RuntimeError("model down")),
        ),
    ):
        failed = await _with_model_extracted_paste_items({"text": "## FACTS\n- x"}, agent_id="agent-1")

    assert failed["_model_extraction_failed"] is True


@pytest.mark.asyncio
async def test_paste_model_lane_runs_the_completion_callback() -> None:
    extraction = SimpleNamespace(memories=[_memory(MemoryType.SEMANTIC, "Prefers small diffs.")])
    llm = SimpleNamespace(ainvoke=AsyncMock(return_value=object()))

    async def fake_extract(
        _conversation: object,
        complete: Callable[[str, str], Awaitable[str]],
    ) -> SimpleNamespace:
        assert await complete("system", "user") == "answer"
        return extraction

    with (
        patch(
            "app.services.memory.extract_retry.resolve_chat_extraction_llm.resolve_import_extraction_llm",
            AsyncMock(return_value=llm),
        ),
        patch(
            "myrm_agent_harness.toolkits.memory.strategies.extractor.extract_memories_from_conversation",
            fake_extract,
        ),
        patch(
            "myrm_agent_harness.utils.chat_utils.extract_answer_text",
            return_value="answer",
        ),
    ):
        enriched = await _with_model_extracted_paste_items({"text": "## FACTS\n- x"}, agent_id=None)

    llm.ainvoke.assert_awaited_once()
    assert enriched["_model_items"] == [
        {
            "content": "Prefers small diffs.",
            "bucket": "semantic",
            "importance": 0.5,
            "confidence": 0.5,
            "profile_key": None,
            "profile_value": None,
            "trigger": None,
        }
    ]


@pytest.mark.asyncio
async def test_paste_model_lane_falls_back_when_extraction_is_empty() -> None:
    extraction = SimpleNamespace(memories=[_memory(MemoryType.CONVERSATION, "Dropped bucket.")])

    with (
        patch(
            "app.services.memory.extract_retry.resolve_chat_extraction_llm.resolve_import_extraction_llm",
            AsyncMock(return_value=object()),
        ),
        patch(
            "myrm_agent_harness.toolkits.memory.strategies.extractor.extract_memories_from_conversation",
            AsyncMock(return_value=extraction),
        ),
    ):
        enriched = await _with_model_extracted_paste_items({"text": "## FACTS\n- x"}, agent_id=None)

    assert enriched["_model_extraction_failed"] is True
    assert "_model_items" not in enriched


@pytest.mark.asyncio
async def test_paste_model_lane_maps_only_supported_non_empty_buckets() -> None:
    extraction = SimpleNamespace(
        memories=[
            _memory(MemoryType.SEMANTIC, "Prefers small diffs.", importance=0.8, confidence=0.9),
            _memory(MemoryType.CONVERSATION, "Dropped bucket."),
            _memory(MemoryType.SEMANTIC, "   "),
        ]
    )
    extractor = AsyncMock(return_value=extraction)

    with (
        patch(
            "app.services.memory.extract_retry.resolve_chat_extraction_llm.resolve_import_extraction_llm",
            AsyncMock(return_value=object()),
        ),
        patch(
            "myrm_agent_harness.toolkits.memory.strategies.extractor.extract_memories_from_conversation",
            extractor,
        ),
    ):
        enriched = await _with_model_extracted_paste_items({"text": "## FACTS\n- x"}, agent_id=None)

    assert enriched["_model_items"] == [
        {
            "content": "Prefers small diffs.",
            "bucket": "semantic",
            "importance": 0.8,
            "confidence": 0.9,
            "profile_key": None,
            "profile_value": None,
            "trigger": None,
        }
    ]
    assert "_model_extraction_failed" not in enriched
    assert _COMPETITOR_AVG_SKILL_TOKENS == 500
    assert _MYRM_AVG_INDEX_TOKENS == 30
