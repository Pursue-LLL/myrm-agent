"""会话/目标执行轨迹的批量提取入口。

[POS]
记忆提取子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from myrm_agent_harness.toolkits.memory.strategies.extractor.models import (
    ExtractedMemory,
    ExtractionConfig,
    ExtractionResult,
    LLMFunc,
)
from myrm_agent_harness.toolkits.memory.strategies.extractor.parse import _parse_response
from myrm_agent_harness.toolkits.memory.strategies.extractor.prompt import detect_language
from myrm_agent_harness.toolkits.memory.strategies.extractor.runner import MemoryExtractor
from myrm_agent_harness.toolkits.memory.types import (
    EvidenceReference,
)

logger = logging.getLogger(__name__)


async def extract_memories_from_conversation(
    messages: Sequence[Mapping[str, object]],
    llm_func: LLMFunc,
    config: ExtractionConfig | None = None,
    *,
    correction_detected: bool = False,
) -> ExtractionResult:
    """Convenience: extract memories from a conversation.

    Admits only distillable messages, runs LLM extraction, then keeps the
    memories that are grounded in the user's own words.
    """
    from myrm_agent_harness.toolkits.memory.strategies.distillation_guards import (
        filter_distillable_messages,
    )

    # 1. Distillation Admission Guard: filter bot/alert/unconfirmed messages
    filtered_messages, rejections = filter_distillable_messages(
        messages,
        allow_other_as_context=True,
    )
    if not filtered_messages:
        logger.info(
            "All %d messages rejected by distillation guards (%d rejections)",
            len(messages),
            len(rejections),
        )
        return ExtractionResult()

    user_corpus = [
        str(m.get("content") or "")
        for m in filtered_messages
        if m.get("role") == "user" and not m.get("_third_party_context")
    ]

    extractor = MemoryExtractor(config=config, llm_func=llm_func)
    result = await extractor.extract(
        filtered_messages, correction_detected=correction_detected
    )

    # Provenance anchor fallback: ensure all LLM extracted memories carry evidence
    for m in result.memories:
        if not m.evidence and filtered_messages:
            last_user = next(
                (
                    m_dict
                    for m_dict in reversed(filtered_messages)
                    if m_dict.get("role") == "user"
                ),
                None,
            )
            if last_user:
                m.evidence.append(
                    EvidenceReference(
                        source_id="conversation_turn",
                        message_id=str(
                            last_user.get("id") or last_user.get("message_id") or ""
                        )
                        or None,
                        quote_snippet=str(last_user.get("content") or "")[:160],
                    )
                )

    from myrm_agent_harness.toolkits.memory.strategies.distillation_guards import (
        filter_memories_with_evidence,
    )

    verified_llm_memories, ungrounded = filter_memories_with_evidence(
        result.memories,
        allowed_verbatim_corpus=user_corpus if user_corpus else None,
    )
    if ungrounded:
        logger.warning(
            "Distillation guard dropped %d ungrounded or hallucinated memories",
            len(ungrounded),
        )

    return ExtractionResult(
        memories=verified_llm_memories,
        extraction_time_ms=result.extraction_time_ms,
        raw_response=result.raw_response,
    )


# ---------------------------------------------------------------------------
# Goal Learnings Extraction
# ---------------------------------------------------------------------------

_GOAL_LEARNINGS_PROMPT = """You are a post-mortem analyst. After a goal-based autonomous agent completes a task,
you extract forward-looking, actionable learnings from the full execution trace.

## Objective
Extract learnings that will help FUTURE runs of similar goals succeed faster and avoid repeated mistakes.

## Categories (extract at least one from each category if evidence exists)

1. **Patterns**: Recurring approaches that worked well.
   Example: "This project uses Pydantic models for all API schemas — always check existing models before creating new ones"

2. **Gotchas**: Pitfalls, errors, or surprises encountered.
   Example: "Modifying locale files requires running `bun run i18n:check` afterwards — otherwise build fails silently"

3. **Context**: Project-specific facts discovered during execution.
   Example: "The authentication module uses a custom middleware chain — not the standard FastAPI dependency injection"

## Rules
1. Each learning must be ACTIONABLE — future agents can act on it without additional context.
2. Be SPECIFIC: include file paths, tool names, config keys, or version numbers when relevant.
3. Write in third person imperative: "Always X when Y" or "Never Z without W".
4. Skip trivial observations that any competent developer would already know.
5. Each learning: 15-80 words. Output 2-8 learnings total.
6. confidence: 0.8-1.0 (only high-confidence learnings).
7. importance: 0.7-1.0 (only significant learnings).

## Output
JSON array. Each item:
{"memory_type":"semantic","content":"<the learning>","confidence":<float>,"importance":<float>,"reasoning":"<brief evidence>"}

Empty if no meaningful learnings: []"""


_GOAL_LEARNINGS_MAX_CHARS = 60_000


async def extract_goal_learnings(
    messages: Sequence[Mapping[str, object]],
    goal_objective: str,
    llm_func: LLMFunc,
    *,
    max_chars: int = _GOAL_LEARNINGS_MAX_CHARS,
) -> list[ExtractedMemory]:
    """Extract forward-looking actionable learnings from a completed goal's execution trace.

    Unlike general memory extraction which is retrospective (recording what happened),
    goal learnings are prospective: they capture patterns, gotchas, and context that
    will help future similar goals succeed faster.

    Args:
        messages: Full collected_messages from the goal execution (converted to dict format)
        goal_objective: The goal's objective text for context
        llm_func: LLM function for extraction
        max_chars: Maximum characters for the input (truncated via head-tail)

    Returns:
        List of ExtractedMemory objects (memory_type=SEMANTIC) representing goal learnings
    """
    if not messages or not goal_objective.strip():
        return []

    from myrm_agent_harness.toolkits.memory.chunking import EpisodesChunker

    total_chars = sum(len(str(m.get("content") or "")) for m in messages)
    if total_chars <= max_chars:
        batches: list[Sequence[Mapping[str, object]]] = [messages]
    else:
        chunker = EpisodesChunker(
            soft_max_chars=max(4_000, max_chars // 2), overlap_turns=1
        )
        episodes = chunker.split_into_episodes([dict(m) for m in messages])
        batches = [ep.messages for ep in episodes]

    all_learnings: list[ExtractedMemory] = []
    seen_contents: set[str] = set()

    for batch_msgs in batches:
        formatted = "\n".join(
            f"[{str(m.get('role') or 'user').upper()}]: {m.get('content', '')}"
            for m in batch_msgs
        )

        language = detect_language(formatted)
        lang_hint = (
            "\n\n**IMPORTANT**: Write all learnings in Chinese (中文)."
            if language == "zh"
            else ""
        )

        prompt = (
            f"## Goal Objective\n\n{goal_objective}\n\n"
            f"## Execution Trace\n\n{formatted}\n\n"
            f"## Instructions\n\nExtract actionable learnings from the above goal execution.{lang_hint}\n"
            "Return ONLY a valid JSON array, no other text.\n"
        )

        try:
            raw = await llm_func(_GOAL_LEARNINGS_PROMPT, prompt)
            parsed = _parse_response(raw)
            for item in parsed:
                if not item.evidence:
                    item.evidence = [
                        EvidenceReference(
                            source_id=f"goal:{goal_objective[:30]}",
                            quote_snippet=goal_objective[:120],
                        )
                    ]
            for m in parsed:
                if m.confidence >= 0.7 and m.importance >= 0.6:
                    key = m.content.strip()
                    if key not in seen_contents:
                        seen_contents.add(key)
                        all_learnings.append(m)
        except Exception as e:
            logger.warning("Goal learnings batch extraction failed: %s", e)

    if all_learnings:
        logger.info(
            "Extracted %d goal learnings from %d messages (%d batches)",
            len(all_learnings),
            len(messages),
            len(batches),
        )
    return all_learnings
