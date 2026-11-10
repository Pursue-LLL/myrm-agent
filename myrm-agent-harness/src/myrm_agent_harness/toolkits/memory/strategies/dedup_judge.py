"""Layer 3 of deduplication: judge how a new memory relates to the stored candidates most similar to it.

[INPUT]
- memory.config::MemoryConfig (POS: memory configuration)
- memory.protocols.vector::{VectorSearchResult, VectorStoreProtocol} (POS: vector store protocol)
- memory.types::SemanticMemory (POS: memory data models)
- strategies.dedup_types::{DeduplicatableMemory, DeduplicationDecision} (POS: the memory types deduplication compares and merges, and the judgment verdicts)
- strategies.llm_prompt::DEDUPLICATION_SYSTEM_PROMPT (POS: LLM prompt for Layer 3 semantic deduplication judgment)
- strategies.merger::{DeterministicThreeStateMerger, MergeState} (POS: deterministic memory conflict resolution)
- utils.chat_utils::extract_answer_text (POS: LLM 响应答案提取 — 兼容 reasoning 模型 content 空回退)

[OUTPUT]
- DedupJudge: DUPLICATE / UPDATE_REPLACE / UPDATE_MERGE / NEW verdict for a memory and its candidates
- hard_facet_conflict: the facet a memory and a candidate contradict outright, if any

[POS]
The deterministic three-state merger runs first: CONFIRM and SUPPLEMENT short-circuit with zero LLM cost, a facet or
polarity conflict short-circuits to NEW (both records marked contested so retention leaves them to a human), and only
the semantic-ambiguity band reaches the LLM. LLM failures default to NEW so nothing is lost.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from myrm_agent_harness.toolkits.memory.strategies.dedup_types import DeduplicatableMemory, DeduplicationDecision
from myrm_agent_harness.toolkits.memory.strategies.llm_prompt import (
    DEDUPLICATION_SYSTEM_PROMPT,
)
from myrm_agent_harness.toolkits.memory.strategies.merger import (
    DeterministicThreeStateMerger,
    MergeState,
)
from myrm_agent_harness.toolkits.memory.types import SemanticMemory
from myrm_agent_harness.utils.chat_utils import extract_answer_text

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.config import MemoryConfig
    from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol

logger = logging.getLogger(__name__)

_LLM_CANDIDATES_LIMIT = 3

# Key the forgetting pass reads to hold a contested memory until a human settles it
# (``strategies/forgetting.py`` checks this before applying any retention cut).
_SUPERSEDED_KEY = "superseded"
_CONTESTED_KEY = "conflict_status"
_CONTESTED_VALUE = "conflicted"


def _mark_contested(memory: DeduplicatableMemory) -> None:
    """Flag a memory as contested so retention leaves the decision to a human."""
    metadata = getattr(memory, "metadata", None)
    if isinstance(metadata, dict):
        metadata[_CONTESTED_KEY] = _CONTESTED_VALUE


def hard_facet_conflict(memory: DeduplicatableMemory, candidate: object) -> str | None:
    """The facet this memory and ``candidate`` contradict outright, if any."""
    from myrm_agent_harness.toolkits.memory._internal.storage import (
        doc_to_episodic,
        doc_to_semantic,
    )
    from myrm_agent_harness.toolkits.memory.protocols.vector import VectorSearchResult

    if not isinstance(candidate, VectorSearchResult):
        return None
    converter = doc_to_semantic if isinstance(memory, SemanticMemory) else doc_to_episodic
    facet = DeterministicThreeStateMerger()._detect_facet_conflict(
        converter(candidate.document).content, memory.content
    )
    return facet if facet and facet != "semantic_ambiguity" else None


class DedupJudge:
    """Layer 3: the deterministic three-state merger first, the LLM only where similarity cannot decide."""

    __slots__ = ("_llm", "_time_window_hours")

    def __init__(self, llm: BaseChatModel | None, time_window_hours: int) -> None:
        self._llm = llm
        self._time_window_hours = time_window_hours

    async def judge(
        self,
        new_memory: DeduplicatableMemory,
        candidates: Sequence[object],
        vector: VectorStoreProtocol,
        config: MemoryConfig,
    ) -> tuple[DeduplicationDecision, str | None]:
        """Layer 3: LLM judges the relationship between new memory and candidates.

        Args:
            candidates: List of VectorSearchResult objects from vector.search()

        Returns:
            (decision, merged_content)
        """
        from myrm_agent_harness.toolkits.memory._internal.storage import (
            doc_to_episodic,
            doc_to_semantic,
        )
        from myrm_agent_harness.toolkits.memory.protocols.vector import (
            VectorSearchResult,
        )

        converter = doc_to_semantic if isinstance(new_memory, SemanticMemory) else doc_to_episodic

        search_results = [c for c in candidates[:_LLM_CANDIDATES_LIMIT] if isinstance(c, VectorSearchResult)]
        existing_mems = [converter(result.document) for result in search_results]

        # 0-LLM deterministic three-state evaluation
        merger = DeterministicThreeStateMerger()
        for result, mem in zip(search_results, existing_mems, strict=False):
            merge_dec = merger.evaluate(
                existing=mem,
                candidate_content=new_memory.content,
                candidate_evidence=getattr(new_memory, "evidence", []),
                similarity=result.score,
            )
            if merge_dec.state == MergeState.USER_OVERRIDE_PROTECTED:
                logger.info("Deduplication: blocked overwrite of user-locked memory %s", mem.id)
                return (DeduplicationDecision.NEW, None)
            if merge_dec.state == MergeState.CONFIRM:
                if isinstance(mem, SemanticMemory) and merge_dec.updated_confidence is not None:
                    mem.confidence = merge_dec.updated_confidence
                    if merge_dec.merged_evidence:
                        mem.evidence = merge_dec.merged_evidence
                return (DeduplicationDecision.DUPLICATE, None)
            if merge_dec.state == MergeState.SUPPLEMENT:
                return (DeduplicationDecision.UPDATE_MERGE, merge_dec.merged_content)
            if merge_dec.state == MergeState.CONFLICT:
                if isinstance(mem, SemanticMemory) and merge_dec.updated_confidence is not None:
                    mem.confidence = merge_dec.updated_confidence
                if isinstance(new_memory, SemanticMemory) and merge_dec.candidate_confidence is not None:
                    new_memory.confidence = merge_dec.candidate_confidence
                facet = (merge_dec.conflict_item.facet if merge_dec.conflict_item else None) or ""
                if facet != "semantic_ambiguity":
                    # Deterministic facet/polarity conflict (location, polarity,
                    # single-value exclusivity) — no LLM needed: keep both as NEW.
                    # Marking both sides contested is what makes the forgetting pass
                    # hold them until a human settles the dispute; without it the
                    # decayed record of a rejected option can expire on its own.
                    _mark_contested(mem)
                    _mark_contested(new_memory)
                    # `mem` is rebuilt from the search hit on every call, so marking
                    # it alone is discarded. The stored document has to be written
                    # back or the retention pass never sees the older record as
                    # contested, which is the one record that decays toward expiry.
                    result.document.metadata = {
                        **result.document.metadata,
                        _CONTESTED_KEY: _CONTESTED_VALUE,
                    }
                    if merge_dec.candidate_supersedes:
                        # The candidate named a replacement, so this record is the one
                        # the user withdrew. Recall skips it so the agent stops
                        # repeating it; storage, maintenance and the governance
                        # listing are untouched, so it stays auditable and decays.
                        result.document.metadata[_SUPERSEDED_KEY] = True
                    collection = (
                        config.semantic_collection
                        if isinstance(new_memory, SemanticMemory)
                        else config.episodic_collection
                    )
                    await vector.upsert(collection, [result.document])
                    return (DeduplicationDecision.NEW, None)
                # Generic semantic ambiguity: defer to the Layer-3 LLM judge.
                continue

        if self._llm is None:
            return (DeduplicationDecision.NEW, None)

        context_parts = [
            f"New memory: {new_memory.content}",
            f"Type: {new_memory.memory_type}",
            f"Created: {new_memory.created_at.isoformat()}",
            "\nExisting similar memories:",
        ]
        has_recent = False
        new_ts = new_memory.created_at if new_memory.created_at.tzinfo else new_memory.created_at.replace(tzinfo=UTC)
        for idx, (result, mem) in enumerate(zip(search_results, existing_mems, strict=False)):
            mem_ts = mem.created_at if mem.created_at.tzinfo else mem.created_at.replace(tzinfo=UTC)
            time_diff = (new_ts - mem_ts).total_seconds() / 3600
            within_window = time_diff < self._time_window_hours
            if within_window:
                has_recent = True
            time_marker = f" [RECENT <{self._time_window_hours}h]" if within_window else ""
            context_parts.append(
                f"\n[{idx + 1}] (similarity={result.score:.2f}, "
                f"time_diff={time_diff:.1f}h{time_marker}, access={mem.access_count}x)\n"
                f"Content: {mem.content}\n"
                f"Metadata: {json.dumps(mem.metadata, ensure_ascii=False)}"
            )

        if has_recent:
            context_parts.insert(
                3,
                f"\n Recent memories found (within {self._time_window_hours}h window). "
                "For recent similar memories, prefer UPDATE over NEW unless clearly different events.",
            )

        user_prompt = "\n".join(context_parts)

        try:
            response = await self._llm.ainvoke(
                [
                    SystemMessage(content=DEDUPLICATION_SYSTEM_PROMPT.strip()),
                    HumanMessage(content=user_prompt),
                ]
            )
            # 兼容 Anthropic 块列表 / reasoning 模型 content 空回退
            result_text = extract_answer_text(response).strip()

            if "UPDATE_REPLACE" in result_text:
                merged = self._extract_merged_content(result_text)
                return (DeduplicationDecision.UPDATE_REPLACE, merged)
            if "UPDATE_MERGE" in result_text:
                merged = self._extract_merged_content(result_text)
                return (DeduplicationDecision.UPDATE_MERGE, merged)
            if "DUPLICATE" in result_text:
                return (DeduplicationDecision.DUPLICATE, None)

            return (DeduplicationDecision.NEW, None)

        except Exception as e:
            logger.warning("LLM judgment failed: %s, defaulting to NEW", e)
            return (DeduplicationDecision.NEW, None)

    @staticmethod
    def _extract_merged_content(llm_response: str) -> str | None:
        """Extract merged content from LLM response.

        Parses LLM response for 'MERGED:' marker and extracts the content.
        Returns None if marker not found or content is empty.
        """
        for line in llm_response.split("\n"):
            stripped = line.strip()
            if stripped.startswith("MERGED:"):
                content = stripped[7:].strip()
                return content if content else None
        return None
