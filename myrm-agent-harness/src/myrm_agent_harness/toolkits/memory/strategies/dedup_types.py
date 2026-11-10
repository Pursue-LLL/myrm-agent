"""Vocabulary shared by the layers of memory deduplication.

[INPUT]
- memory.types::{EpisodicMemory, SemanticMemory} (POS: memory data models)

[OUTPUT]
- DeduplicatableMemory: the memory types deduplication compares and merges
- DeduplicationDecision: DUPLICATE / UPDATE_REPLACE / UPDATE_MERGE / NEW verdicts of the judgment layer

[POS]
Shared types of the deduplication layers (judgment, update application, orchestration), so none of them imports
another layer to name a verdict or the memory types it works on.
"""

from __future__ import annotations

from enum import StrEnum

from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, SemanticMemory

DeduplicatableMemory = SemanticMemory | EpisodicMemory


class DeduplicationDecision(StrEnum):
    """LLM deduplication decision types."""

    DUPLICATE = "DUPLICATE"
    UPDATE_REPLACE = "UPDATE_REPLACE"
    UPDATE_MERGE = "UPDATE_MERGE"
    NEW = "NEW"
