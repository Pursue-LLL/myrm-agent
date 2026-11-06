"""[INPUT]
- myrm_agent_harness.toolkits.llms.adapters.thinking_adapter::ThinkingModelReasoningAdapter (POS: Thinking model reasoning content unpacking and scrubbing adapter.)
- myrm_agent_harness.toolkits.memory.strategies.extractor.models::ExtractedMemory (POS: 记忆提取子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.toolkits.memory.types::EvidenceReference / MemoryType (POS: Memory type system foundation. Provides type-safe schema definitions for all)
- myrm_agent_harness.utils.json_parsing::parse_llm_json_list (POS: Robust LLM JSON extraction. Business-config-independent helpers shared by all verifier/semantic layers.)

[OUTPUT]
- _parse_response: _parse_response

[POS]
记忆提取子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.llms.adapters.thinking_adapter import (
    ThinkingModelReasoningAdapter,
)
from myrm_agent_harness.toolkits.memory.strategies.extractor.models import ExtractedMemory
from myrm_agent_harness.toolkits.memory.types import (
    EvidenceReference,
    MemoryType,
)
from myrm_agent_harness.utils.json_parsing import parse_llm_json_list

logger = logging.getLogger(__name__)


def _parse_response(raw: str) -> list[ExtractedMemory]:
    cleaned = ThinkingModelReasoningAdapter.scrub_thinking_tags(raw)
    data = parse_llm_json_list(cleaned)
    if data is None:
        extracted_block = ThinkingModelReasoningAdapter.extract_json_block(cleaned)
        if extracted_block:
            data = parse_llm_json_list(extracted_block)
    if data is None:
        logger.warning("Failed to parse extraction response as JSON array")
        return []
    result: list[ExtractedMemory] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            raw_pref_type = item.get("preference_type")
            pref_type = (
                raw_pref_type if raw_pref_type in ("explicit", "implicit") else None
            )
            raw_source_error = item.get("source_error") or item.get("sourceError")
            raw_tool_name = item.get("tool_name")
            raw_tool_priority = item.get("tool_rule_priority")
            tool_priority = (
                str(raw_tool_priority)
                if raw_tool_priority in ("critical", "high", "normal")
                else None
            )
            raw_evd = item.get("expected_valid_days")
            evd: int | None = None
            if (
                isinstance(raw_evd, (int, float))
                and not isinstance(raw_evd, bool)
                and raw_evd > 0
            ):
                evd = min(int(raw_evd), 730)

            parsed_evidences: list[EvidenceReference] = []
            raw_evidence = item.get("evidence")
            if isinstance(raw_evidence, list):
                for ev in raw_evidence:
                    if isinstance(ev, dict) and ev.get("source_id"):
                        parsed_evidences.append(
                            EvidenceReference(
                                source_id=str(ev.get("source_id")),
                                message_id=(
                                    str(ev.get("message_id"))
                                    if ev.get("message_id")
                                    else None
                                ),
                                channel_id=(
                                    str(ev.get("channel_id"))
                                    if ev.get("channel_id")
                                    else None
                                ),
                                quote_snippet=(
                                    str(ev.get("quote_snippet"))
                                    if ev.get("quote_snippet")
                                    else None
                                ),
                                author_id=(
                                    str(ev.get("author_id"))
                                    if ev.get("author_id")
                                    else None
                                ),
                            )
                        )

            result.append(
                ExtractedMemory(
                    memory_type=MemoryType(item.get("memory_type", "semantic")),
                    content=item.get("content", ""),
                    confidence=float(item.get("confidence", 0.5)),
                    importance=float(item.get("importance", 0.5)),
                    expected_valid_days=evd,
                    profile_key=item.get("profile_key"),
                    profile_value=item.get("profile_value"),
                    trigger=item.get("trigger"),
                    action=item.get("action"),
                    tool_name=str(raw_tool_name) if raw_tool_name else None,
                    tool_rule_priority=tool_priority,
                    reasoning=item.get("reasoning"),
                    preference_type=pref_type,
                    preference_strength=float(item.get("preference_strength", 0.0)),
                    source_error=(
                        raw_source_error if isinstance(raw_source_error, str) else None
                    ),
                    evidence=parsed_evidences,
                )
            )
        except Exception as e:
            logger.warning("Failed to parse memory item: %s", e)
    return result
