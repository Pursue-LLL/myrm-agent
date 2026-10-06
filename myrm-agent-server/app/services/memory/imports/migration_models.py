"""Universal memory migration models and contracts.

[INPUT]
External memory schemas and target memory bucket definitions.

[OUTPUT]
Strongly-typed CanonicalMigratedItem and MigrationParityReport contracts.

[POS]
Universal memory migration domain models ensuring zero-loss schema normalization.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MigrationSourceType(StrEnum):
    MEM0 = "mem0"
    LETTA_MEMGPT = "letta"
    LANGCHAIN = "langchain"
    ZEP = "zep"
    CLAUDE_CODE = "claude_code"
    OPENCLAW = "openclaw"
    HINDSIGHT = "hindsight"
    UNKNOWN = "unknown"


class MemoryTargetBucket(StrEnum):
    SEMANTIC = "semantic"
    CONVERSATION = "conversation"
    PROCEDURAL = "procedural"


class MigrationFidelityLevel(StrEnum):
    LOSSLESS_VERBATIM = "lossless_verbatim"
    STRUCTURED_SEMANTIC = "structured_semantic"
    PROCEDURAL_RULE = "procedural_rule"


class CanonicalMigratedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    source_type: MigrationSourceType
    source_id: str
    target_bucket: MemoryTargetBucket
    fidelity_level: MigrationFidelityLevel
    content: str
    importance: float = 0.5
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class MigrationParityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: MigrationSourceType
    total_source_items: int
    mapped_semantic_count: int
    mapped_conversation_count: int
    mapped_procedural_count: int
    dropped_or_invalid_count: int
    fidelity_ratio: float
    warnings: list[str] = Field(default_factory=list)
    audit_digest: str
