"""[INPUT]
- myrm_agent_harness.toolkits.memory.types::EpisodicMemory / EvidenceReference / MemoryType / PreferenceType / ProceduralMemory / ProfileEntry / SemanticMemory (POS: Memory type system foundation. Provides type-safe schema definitions for all)

[OUTPUT]
- ExtractionConfig: ExtractionConfig
- ExtractedMemory: ExtractedMemory
- ExtractionResult: ExtractionResult

[POS]
记忆提取子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    EvidenceReference,
    MemoryType,
    PreferenceType,
    ProceduralMemory,
    ProfileEntry,
    SemanticMemory,
)

logger = logging.getLogger(__name__)


LLMFunc = Callable[[str, str], Awaitable[str]]
ConcreteMemory = ProfileEntry | SemanticMemory | EpisodicMemory | ProceduralMemory

@dataclass
class ExtractionConfig:
    extract_profile: bool = True
    extract_semantic: bool = True
    extract_episodic: bool = True
    extract_procedural: bool = True
    enable_task_digest: bool = False
    min_confidence: float = 0.8
    min_importance: float = 0.6
    max_extractions_per_turn: int = 5
    extraction_model: str = "gpt-4o-mini"
    max_input_chars: int = 80_000
    """Maximum characters for the conversation prompt sent to extraction LLM.
    Conversations exceeding this are truncated using head-tail preservation."""
    wiki_boundary_enabled: bool = False
    """When True, extraction prompt skips document-like semantic/episodic facts (wiki owns those)."""
    domain_preset: str = "none"
    """Domain extraction preset injecting priority attribute hints into the extraction prompt.
    Valid values: 'none', 'persona', 'work_assistant', 'research', or 'auto'."""


class ExtractedMemory(BaseModel):
    memory_type: MemoryType
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0, default=0.5)
    expected_valid_days: int | None = Field(
        default=None,
        description="Estimated validity window in days. None = stable/unknown.",
    )
    profile_key: str | None = None
    profile_value: str | None = None
    trigger: str | None = None
    action: str | None = None
    tool_name: str | None = Field(
        default=None,
        description="Tool name this procedural rule is scoped to (e.g. 'bash_code_execute_tool')",
    )
    tool_rule_priority: str | None = Field(
        default=None,
        description="Priority for tool-scoped rules: 'critical', 'high', or 'normal'",
    )
    source_message: str | None = None
    reasoning: str | None = None
    application: str | None = None
    preference_type: PreferenceType | None = None
    preference_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    source_error: str | None = Field(
        default=None,
        description="Description of the mistake being corrected (for correction memories)",
    )
    evidence: list[EvidenceReference] = Field(
        default_factory=list,
        description="Structured provenance evidence anchoring this fact to raw interaction context",
    )


class ExtractionResult(BaseModel):
    memories: list[ExtractedMemory] = Field(default_factory=list)
    raw_response: str | None = None
    model_used: str = ""
    extraction_time_ms: float = 0.0
    correction_signal_detected: bool = False
    correction_count: int = 0
    truncated: bool = False
    dropped_message_count: int = 0
