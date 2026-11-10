"""Layer 3 outcome of deduplication: fold a new memory into the existing one the judgment layer picked.

[INPUT]
- memory.config::MemoryConfig (POS: memory configuration)
- memory.protocols.vector::VectorStoreProtocol (POS: vector store protocol)
- memory.types::SemanticMemory (POS: memory data models)
- strategies.conflict_merger::merge_evidence_references (POS: evidence reference merging)
- strategies.dedup_types::{DeduplicatableMemory, DeduplicationDecision} (POS: the memory types deduplication compares and merges, and the judgment verdicts)

[OUTPUT]
- apply_dedup_update: the existing memory updated in place with the new one, or the new memory to create when the update is refused

[POS]
Applies an UPDATE verdict. The target is refused (the new memory is created instead) when it is user-protected,
sourced from the user, or scoped to a namespace the new memory does not share.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.strategies.dedup_types import DeduplicatableMemory, DeduplicationDecision
from myrm_agent_harness.toolkits.memory.types import SemanticMemory

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.config import MemoryConfig
    from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol

logger = logging.getLogger(__name__)

_HISTORY_SUMMARY_LENGTH = 30


async def apply_dedup_update(
    new_memory: DeduplicatableMemory,
    target_id: str,
    merged_content: str,
    decision: DeduplicationDecision,
    vector: VectorStoreProtocol,
    config: MemoryConfig,
) -> DeduplicatableMemory | None:
    """Apply UPDATE decision by modifying the existing memory.

    Metadata handling:
    - UPDATE_REPLACE: new metadata fully replaces existing metadata
    - UPDATE_MERGE: new metadata merges into existing (new keys override)
    Tags are always union-merged and deduplicated.
    Source fields always update to the latest provenance.
    """
    from myrm_agent_harness.toolkits.memory._internal.storage import (
        doc_to_episodic,
        doc_to_semantic,
    )

    is_semantic = isinstance(new_memory, SemanticMemory)
    collection = config.semantic_collection if is_semantic else config.episodic_collection
    converter = doc_to_semantic if is_semantic else doc_to_episodic

    try:
        docs = await vector.get(collection, [target_id])
        if not docs:
            logger.warning("Target memory %s not found, creating NEW", target_id)
            return new_memory

        existing = converter(docs[0])

        # CRITICAL: User Override Wins - Never allow automated LLM deduplication to overwrite human edits
        if getattr(existing, "is_user_protected", False) or getattr(existing, "source", "") == "user":
            logger.info("Deduplicator: preserved user-locked memory %s, creating NEW instead of overwrite", target_id)
            return new_memory

        existing_ns = set(existing.scope.namespaces)
        new_ns = set(new_memory.scope.namespaces)
        # Empty namespaces mean global scope (no boundary to enforce);
        # only refuse when both sides declare disjoint explicit scopes.
        if existing_ns and new_ns and not existing_ns & new_ns:
            logger.warning("Refusing cross-scope update on %s, creating NEW", target_id)
            return new_memory

        existing.content = merged_content
        existing.updated_at = datetime.now(UTC)
        existing.merge_count += 1
        existing.embedding = None

        # Merge evidence chains if present
        if hasattr(existing, "evidence") and hasattr(new_memory, "evidence"):
            from myrm_agent_harness.toolkits.memory.strategies.conflict_merger import (
                merge_evidence_references,
            )

            existing.evidence = merge_evidence_references(
                getattr(existing, "evidence", None),
                getattr(new_memory, "evidence", None),
            )

        if decision == DeduplicationDecision.UPDATE_REPLACE:
            if new_memory.metadata:
                existing.metadata = dict(new_memory.metadata)
        else:
            if new_memory.metadata:
                existing.metadata = {**existing.metadata, **new_memory.metadata}

        if isinstance(new_memory, SemanticMemory) and isinstance(existing, SemanticMemory) and new_memory.tags:
            existing.tags = list(dict.fromkeys(existing.tags + new_memory.tags))

        if new_memory.source_chat_id:
            existing.source_chat_id = new_memory.source_chat_id
        if new_memory.source_message_id:
            existing.source_message_id = new_memory.source_message_id

        action = "REPLACE" if decision == DeduplicationDecision.UPDATE_REPLACE else "MERGE"
        timestamp = datetime.now(UTC).strftime("%m-%d %H:%M")
        summary = new_memory.content[:_HISTORY_SUMMARY_LENGTH]
        history_entry = f"{timestamp}|{action}|{summary}"
        existing.merge_history = (
            f"{existing.merge_history}\n{history_entry}" if existing.merge_history else history_entry
        )

        if hasattr(existing, "importance"):
            existing.importance = min(existing.importance + 0.05, 1.0)

        return existing

    except Exception as e:
        logger.warning("Apply update failed: %s, creating NEW", e)
        return new_memory
