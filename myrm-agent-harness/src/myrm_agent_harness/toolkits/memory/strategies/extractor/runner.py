"""LLM 驱动的 MemoryExtractor。

[POS]
记忆提取子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from myrm_agent_harness.toolkits.memory.strategies.extractor.models import (
    ConcreteMemory,
    ExtractedMemory,
    ExtractionConfig,
    ExtractionResult,
    LLMFunc,
)
from myrm_agent_harness.toolkits.memory.strategies.extractor.parse import _parse_response
from myrm_agent_harness.toolkits.memory.strategies.extractor.prompt import _build_system_prompt, detect_language
from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    MemoryLifecycle,
    MemoryType,
    ProceduralMemory,
    ProfileEntry,
    SemanticMemory,
    ToolRulePriority,
)

logger = logging.getLogger(__name__)


_ENABLED_TYPE_MAP: dict[MemoryType, str] = {
    MemoryType.PROFILE: "extract_profile",
    MemoryType.SEMANTIC: "extract_semantic",
    MemoryType.EPISODIC: "extract_episodic",
    MemoryType.PROCEDURAL: "extract_procedural",
    MemoryType.TASK_DIGEST: "enable_task_digest",
}


class MemoryExtractor:
    """Extracts memorable information from conversations via LLM."""

    def __init__(
        self, config: ExtractionConfig | None = None, llm_func: LLMFunc | None = None
    ) -> None:
        self.config = config or ExtractionConfig()
        self.llm_func = llm_func
        self._last_detected_language: Literal["zh", "en"] = "en"

    async def extract(
        self,
        messages: Sequence[dict[str, object]],
        context: dict[str, object] | None = None,
        *,
        correction_detected: bool = False,
    ) -> ExtractionResult:
        if not self.llm_func:
            logger.warning("No LLM function provided, skipping extraction")
            return ExtractionResult()

        from myrm_agent_harness.toolkits.memory.strategies.distillation_guards import (
            filter_distillable_messages,
        )

        # Apply deterministic distillation admission guard before token truncation and LLM call
        filtered_messages, rejections = filter_distillable_messages(
            messages,
            allow_other_as_context=True,
        )
        if not filtered_messages:
            logger.info(
                "MemoryExtractor: all %d messages rejected by distillation guards (%d rejections)",
                len(messages),
                len(rejections),
            )
            return ExtractionResult()

        start = datetime.now(UTC)
        total_chars = sum(len(str(m.get("content") or "")) for m in filtered_messages)

        # Single batch fast path for dialogs fitting within budget
        if total_chars <= self.config.max_input_chars:
            return await self._extract_for_message_subset(
                filtered_messages,
                context=context,
                correction_detected=correction_detected,
                start=start,
            )

        # Long conversation lossless path: partition into episodes with causal overlap
        from myrm_agent_harness.toolkits.memory.chunking import EpisodesChunker

        # Chunk budget set conservatively to fit extraction prompt comfortably
        episode_char_budget = max(10, min(self.config.max_input_chars // 2, 32_000))
        chunker = EpisodesChunker(soft_max_chars=episode_char_budget, overlap_turns=1)
        episodes = chunker.split_into_episodes(filtered_messages)

        logger.info(
            "MemoryExtractor: long dialog (%d chars) partitioned into %d episodes without loss",
            total_chars,
            len(episodes),
        )

        profile_memories: dict[str, ExtractedMemory] = {}
        general_memories: list[ExtractedMemory] = []
        seen_general_keys: set[str] = set()
        total_corrections = 0
        last_raw_response = ""

        for ep in episodes:
            ep_res = await self._extract_for_message_subset(
                ep.messages,
                context=context,
                correction_detected=correction_detected,
                start=start,
            )
            total_corrections += ep_res.correction_count
            if ep_res.raw_response:
                last_raw_response = ep_res.raw_response

            for mem in ep_res.memories:
                if mem.profile_key:
                    # Last-Write-Wins: later episodes naturally overwrite earlier preference updates
                    profile_memories[mem.profile_key] = mem
                else:
                    dedup_key = f"{mem.memory_type.value}:{mem.content.strip()}"
                    if dedup_key not in seen_general_keys:
                        seen_general_keys.add(dedup_key)
                        general_memories.append(mem)

        all_memories = list(profile_memories.values()) + general_memories
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
        return ExtractionResult(
            memories=all_memories,
            raw_response=last_raw_response,
            model_used=self.config.extraction_model,
            extraction_time_ms=elapsed,
            correction_signal_detected=correction_detected,
            correction_count=total_corrections,
            truncated=False,
            dropped_message_count=0,
        )

    async def _extract_for_message_subset(
        self,
        messages: list[dict[str, object]],
        *,
        context: dict[str, object] | None,
        correction_detected: bool,
        start: datetime,
    ) -> ExtractionResult:
        if not self.llm_func:
            logger.warning("No LLM function provided, skipping extraction")
            return ExtractionResult()

        full_text = "".join(str(m.get("content") or "") for m in messages)
        detected_language = detect_language(full_text)
        self._last_detected_language = detected_language

        formatted = "\n".join(
            f"[{str(m.get('role') or 'user').upper()}]: {m.get('content', '')}"
            for m in messages
        )
        session_date = start.strftime("%Y-%m-%d (%A)")
        prompt = f"Session date: {session_date}\n\n## Conversation to Analyze\n\n{formatted}\n\n"
        prompt += "## Instructions\n\nAnalyze the conversation. If and ONLY if it contains critical constraints, high-leverage knowledge, or valuable personal facts, output them. Otherwise, output [].\n"
        prompt += "Return ONLY a valid JSON array, no other text.\n"
        if context:
            prompt += f"\n## Additional Context\n{json.dumps(context, indent=2, sort_keys=True)}\n"

        try:
            system_prompt = _build_system_prompt(
                self.config, detected_language, correction_detected=correction_detected
            )
            raw = await self.llm_func(system_prompt, prompt)
            all_parsed = _parse_response(raw)

            digests = [
                m
                for m in all_parsed
                if m.memory_type == MemoryType.TASK_DIGEST
                and m.content.strip()
                and getattr(self.config, _ENABLED_TYPE_MAP.get(m.memory_type, ""), True)
            ][:1]
            fragments = [
                m
                for m in all_parsed
                if m.memory_type != MemoryType.TASK_DIGEST
                and m.confidence >= self.config.min_confidence
                and m.importance >= self.config.min_importance
                and getattr(self.config, _ENABLED_TYPE_MAP.get(m.memory_type, ""), True)
            ]
            memories = fragments[: self.config.max_extractions_per_turn] + digests
            if self.config.enable_task_digest:
                has_digest = any(
                    m.memory_type == MemoryType.TASK_DIGEST for m in memories
                )
                logger.debug(
                    "Task digest %s",
                    "generated" if has_digest else "skipped (no substantive task)",
                )
            elapsed = (datetime.now(UTC) - start).total_seconds() * 1000
            n_corrections = sum(1 for m in memories if m.source_error)
            return ExtractionResult(
                memories=memories,
                raw_response=raw,
                model_used=self.config.extraction_model,
                extraction_time_ms=elapsed,
                correction_signal_detected=correction_detected,
                correction_count=n_corrections,
                truncated=False,
                dropped_message_count=0,
            )
        except Exception as e:
            logger.warning("Memory extraction failed: %s", e)
            return ExtractionResult()

    def to_concrete_memories(
        self, extracted: list[ExtractedMemory], source_chat_id: str | None = None
    ) -> list[ConcreteMemory]:
        result: list[ConcreteMemory] = []
        language = self._last_detected_language
        for m in extracted:
            first_msg_id = (
                m.evidence[0].message_id
                if m.evidence and m.evidence[0].message_id
                else None
            )
            meta: dict[str, str | int | float | bool] = {}
            if m.evidence:
                first_ev = m.evidence[0]
                if first_ev.quote_snippet:
                    meta["evidence_quote"] = first_ev.quote_snippet[:200]
                if first_ev.channel_id:
                    meta["channel_id"] = first_ev.channel_id
                if first_ev.author_id:
                    meta["evidence_author"] = first_ev.author_id
                meta["evidence_count"] = len(m.evidence)

            if (
                m.memory_type == MemoryType.PROFILE
                and m.profile_key
                and m.profile_value
            ):
                result.append(
                    ProfileEntry(
                        key=m.profile_key,
                        value=m.profile_value,
                        language=language,
                        evidence=m.evidence,
                    )
                )
            elif m.memory_type == MemoryType.SEMANTIC:
                pref_type = m.preference_type
                pref_strength = m.preference_strength

                if not pref_type or pref_strength <= 0.0:
                    pass

                result.append(
                    SemanticMemory(
                        content=m.content,
                        importance=m.importance,
                        confidence=m.confidence,
                        source_chat_id=source_chat_id,
                        source_message_id=first_msg_id,
                        preference_type=pref_type,
                        preference_strength=pref_strength,
                        source_error=m.source_error,
                        language=language,
                        expected_valid_days=m.expected_valid_days,
                        evidence=m.evidence,
                        metadata=meta,
                    )
                )
            elif m.memory_type == MemoryType.EPISODIC:
                result.append(
                    EpisodicMemory(
                        content=m.content,
                        event_type="extracted",
                        importance=m.importance,
                        source_chat_id=source_chat_id,
                        source_message_id=first_msg_id,
                        language=language,
                        expected_valid_days=m.expected_valid_days,
                        evidence=m.evidence,
                        metadata=meta,
                    )
                )
            elif m.memory_type == MemoryType.PROCEDURAL and m.trigger and m.action:
                priority_val = (
                    ToolRulePriority(m.tool_rule_priority)
                    if m.tool_rule_priority
                    else ToolRulePriority.NORMAL
                )
                result.append(
                    ProceduralMemory(
                        content=m.content,
                        trigger=m.trigger,
                        action=m.action,
                        reasoning=m.reasoning or "",
                        application=m.application or "",
                        language=language,
                        tool_name=m.tool_name,
                        tool_rule_priority=priority_val,
                        expected_valid_days=m.expected_valid_days,
                        evidence=m.evidence,
                        metadata=meta,
                    )
                )
            elif m.memory_type == MemoryType.TASK_DIGEST:
                result.append(
                    EpisodicMemory(
                        content=m.content,
                        event_type="task_digest",
                        importance=0.85,
                        source_chat_id=source_chat_id,
                        language=language,
                        lifecycle=MemoryLifecycle.new_task_digest(),
                    )
                )
                # Cross-session working state fallback: persist digest as ProfileEntry
                from myrm_agent_harness.toolkits.memory._internal.storage import (
                    WORKING_STATE_PROFILE_KEY,
                    WORKING_STATE_UPDATED_AT_KEY,
                )

                result.append(
                    ProfileEntry(
                        key=WORKING_STATE_PROFILE_KEY,
                        value=m.content,
                        language=language,
                    )
                )
                result.append(
                    ProfileEntry(
                        key=WORKING_STATE_UPDATED_AT_KEY,
                        value=datetime.now(UTC).isoformat(),
                        language=language,
                    )
                )
        return result
