"""[INPUT]
- base::BaseMemory / EvidenceReference / MemoryScope (POS: 记忆基础模型)
- enums::MemoryStatus / MemoryType / RuleSource / ToolRulePriority (POS: 记忆枚举)

[OUTPUT]
- ProfileEntry / SemanticMemory / EpisodicMemory / ConversationMemory
- ProceduralMemory / ClaimMemory / IntegrationMemory / TaskDigestMemory

[POS]
`memory/types_pkg/` 的具体记忆模型；字段即持久化契约。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .base import BaseMemory, EvidenceReference, MemoryScope
from .enums import MemoryStatus, MemoryType, RuleSource, ToolRulePriority


class ProfileEntry(BaseModel):
    """A single user-profile attribute (key-value pair).

    Attributes:
        language: Primary language of the value content ("zh" or "en")
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    key: str
    value: str | int | float | bool | list[str] | dict[str, str] = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    language: Literal["zh", "en"] = "en"
    scope: MemoryScope = Field(default_factory=MemoryScope)
    evidence: list[EvidenceReference] = Field(
        default_factory=list, description="Structured provenance evidence anchoring this profile fact"
    )

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _ensure_utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

PreferenceType = Literal["explicit", "implicit"]

class SemanticMemory(BaseMemory):
    """Factual knowledge stored with vector embeddings.

    Preference-bearing memories additionally carry ``preference_type``
    and ``preference_strength`` so the RRF retriever can boost them
    automatically without a separate search path.

    Attributes:
        language: Primary language of the content ("zh" or "en")
        merge_count: Number of times this memory has been merged/updated
        merge_history: Compact text log of merge operations
    """

    memory_type: Literal[MemoryType.SEMANTIC] = MemoryType.SEMANTIC
    embedding: list[float] | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_chat_id: str | None = None
    source_message_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    preference_type: PreferenceType | None = None
    preference_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    correction_of: str | None = Field(
        default=None, description="ID of the memory this one corrects, forming a correction chain"
    )
    source_error: str | None = Field(
        default=None, description="Description of the mistake being corrected (complements correction_of)"
    )
    language: Literal["zh", "en"] = "en"
    merge_count: int = Field(default=0, ge=0, description="Number of merges applied to this memory")
    merge_history: str = Field(default="", description="Compact merge log: timestamp|action|summary")

class EpisodicMemory(BaseMemory):
    """Conversation event stored with vector embeddings and optional graph.

    Attributes:
        language: Primary language of the content ("zh" or "en")
        merge_count: Number of times this memory has been merged/updated
        merge_history: Compact text log of merge operations
        subtask_phase: Software engineering / task workflow phase ("analyze", "locate", "edit", "verify")
        is_failure_attempt: Whether this episodic entry represents a failed attempt or dead-end
        failure_reason: Root-cause error message or reason for failure
        negative_lesson: Distilled negative rule / advice to avoid repeating this dead-end
    """

    memory_type: Literal[MemoryType.EPISODIC] = MemoryType.EPISODIC
    embedding: list[float] | None = None
    event_type: str = "conversation"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    related_entities: list[str] = Field(default_factory=list)
    source_chat_id: str | None = None
    source_message_id: str | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    language: Literal["zh", "en"] = "en"
    merge_count: int = Field(default=0, ge=0, description="Number of merges applied to this memory")
    merge_history: str = Field(default="", description="Compact merge log: timestamp|action|summary")
    subtask_phase: Literal["analyze", "locate", "edit", "verify"] | None = Field(
        default=None,
        description="Workflow phase for subtask-level episodic memory",
    )
    is_failure_attempt: bool = Field(
        default=False,
        description="Flag indicating this episodic entry captures a failed attempt or dead-end",
    )
    failure_reason: str | None = Field(
        default=None,
        description="Structured failure cause or error summary",
    )
    negative_lesson: str | None = Field(
        default=None,
        description="Negative guidance / rule to prevent repeating this failed attempt",
    )
    confidence_tier: Literal["strong", "weak", "shadow"] = Field(
        default="strong",
        description="Confidence tier for cross-task reuse: strong drives action, weak/shadow is read-only background",
    )
    relation_category: Literal["same_work_item", "same_problem", "reusable_sop", "shadow_context"] = Field(
        default="same_work_item",
        description="Category describing the cross-task relationship",
    )

class ConversationMemory(BaseMemory):
    """Conversation exchange stored with dual-field verbatim + summary.

    Dual-field storage prevents irreversible information loss:
    - raw_exchange: User question + AI response verbatim (no LLM processing)
    - content: LLM-extracted summary for context compression

    Dual-embedding enables precision + coverage trade-off:
    - raw_embedding: Embedding of raw_exchange (high precision)
    - summary_embedding: Embedding of content (broad coverage)

    Attributes:
        raw_exchange: Verbatim Q+A pair, never modified
        content: LLM extracted summary
        raw_embedding: Vector embedding of raw_exchange
        summary_embedding: Vector embedding of content
        timestamp: When this exchange occurred
        user_turn_only: Whether only user turns are indexed (default True)
        related_entities: Entities mentioned in conversation
        project_id: Project/wing hierarchy (optional)
        topic_id: Topic/room hierarchy (optional)
        language: Primary language ("zh" or "en")
    """

    memory_type: Literal[MemoryType.CONVERSATION] = MemoryType.CONVERSATION
    raw_exchange: str = Field(..., description="User Q + AI A verbatim text")
    raw_embedding: list[float] | None = None
    summary_embedding: list[float] | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    user_turn_only: bool = Field(
        default=True, description="Index only user turns (MemPalace strategy for 96.6% baseline)"
    )
    related_entities: list[str] = Field(default_factory=list)
    source_chat_id: str | None = None
    source_message_id: str | None = None
    project_id: str | None = Field(default=None, description="Project/wing identifier")
    topic_id: str | None = Field(default=None, description="Topic/room identifier")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    language: Literal["zh", "en"] = "en"

    def without_raw(self) -> ConversationMemory:
        """Return copy without raw_exchange (for lazy loading)."""
        return self.model_copy(update={"raw_exchange": "", "raw_embedding": None})

    @property
    def display_content(self) -> str:
        """Return summary content for display (not raw verbatim)."""
        return self.content

class ProceduralMemory(BaseMemory):
    """Behavioral rule: trigger -> action.

    ``is_active`` is kept for SQLite column compatibility but derives from
    ``status``. Prefer using ``status`` for new code.

    Tool-scoped rules use ``tool_name`` to associate with a specific tool
    and ``tool_rule_priority`` to record how durable the rule is:
    - CRITICAL: user-mandated, excluded from TTL archiving
    - HIGH: judged important by the extractor; ceiling for agent-written rules
    - NORMAL: ordinary rule

    Prompt-budget survival is governed by ``is_user_locked``, not by this
    level: endorsed rules are ordered ahead of generic rules so unendorsed
    ones are trimmed first.

    Attributes:
        language: Primary language of the rule content ("zh" or "en")
        tool_name: Tool this rule is scoped to (None = global rule)
        tool_rule_priority: Durability level for tool-scoped rules
    """

    memory_type: Literal[MemoryType.PROCEDURAL] = MemoryType.PROCEDURAL
    content: str = Field(default="", description="Memory text content or rule summary")
    trigger: str
    action: str
    reasoning: str = Field(default="", description="Why this rule exists (Context/Rationale)")
    application: str = Field(default="", description="How to apply this rule (Nuances/Boundaries)")
    priority: int = 0
    is_active: bool = Field(default=True, description="Derived from status on save")
    trigger_keywords: list[str] = Field(default_factory=list)
    source: RuleSource = RuleSource.USER_EXTRACTED
    language: Literal["zh", "en"] = "en"
    tool_name: str | None = Field(default=None, description="Tool this rule is scoped to (None = global)")
    tool_rule_priority: ToolRulePriority = Field(
        default=ToolRulePriority.NORMAL,
        description="Durability level: CRITICAL rules are excluded from TTL archiving",
    )
    error_fingerprint: str | None = Field(
        default=None,
        description="Normalized error signature or regex for fast deterministic matching",
    )
    resolution_steps: list[str] = Field(
        default_factory=list,
        description="Ordered corrective actions or instructions taken to resolve the error",
    )
    facets: list[str] = Field(
        default_factory=lambda: ["global"],
        description="Domain or role scopes (e.g. ['frontend', 'devops'])",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Crystallization confidence factor",
    )
    severity: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Failure severity or impact factor",
    )
    success_count: int = Field(
        default=0,
        ge=0,
        description="Total execution success occurrences",
    )
    fail_count: int = Field(
        default=0,
        ge=0,
        description="Total execution failure occurrences",
    )
    lifecycle_state: str = Field(
        default="active",
        description="Lifecycle state: active, degraded, or retired",
    )

    def model_post_init(self, __context: object) -> None:
        """Sync is_active ↔ status on construction for legacy data."""
        if not self.content and (self.trigger or self.action):
            self.content = f"{self.trigger} -> {self.action}".strip(" ->")
        if not self.is_active and self.status == MemoryStatus.ACTIVE:
            self.status = MemoryStatus.DISABLED
        elif self.is_active and self.status == MemoryStatus.DISABLED:
            self.is_active = False

class ClaimMemory(BaseMemory):
    """Compiled knowledge object produced from the claim graph.

    ClaimMemory is retrieval-only: it represents L3 compiled knowledge and must
    not be treated as a regular semantic fact written through vector storage.
    """

    memory_type: Literal[MemoryType.CLAIM] = MemoryType.CLAIM
    claim_key: str
    title: str
    claim_text: str
    model_summary: str = ""
    last_result: str = ""
    evidence_count: int = Field(default=0, ge=0)
    freshness: str = "stale"
    freshness_days: int = Field(default=0, ge=0)
    contradiction_status: str = "none"
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)

class IntegrationMemory(BaseMemory):
    """External service data cached as local memory for semantic retrieval.

    Integration memories are populated by pulling data from third-party services
    (Gmail, GitHub, Slack, Notion, etc.) and indexing it locally. This enables
    cross-source semantic retrieval without live API calls.
    """

    memory_type: Literal[MemoryType.INTEGRATION] = MemoryType.INTEGRATION
    embedding: list[float] | None = None
    provider: str = Field(..., description="Integration source identifier (e.g. 'gmail', 'github')")
    account_key: str = Field(default="", description="Stable account identifier within the provider")
    account_label: str = Field(default="", description="Human-readable account label")
    source_type: str = Field(default="", description="Object type within the provider (e.g. 'email', 'pr')")
    external_object_id: str | None = Field(default=None, description="Provider-side unique object ID")
    external_object_type: str | None = Field(default=None, description="Provider-side object type label")
    title: str = Field(default="", description="Human-readable title")
    summary: str = Field(default="", description="Compact summary for tree aggregation")
    tags: list[str] = Field(default_factory=list)
    observed_at: datetime | None = Field(default=None, description="When this data was originally observed")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tree_id: str = Field(default="", description="ID of the integration tree this leaf belongs to")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("observed_at", mode="before")
    @classmethod
    def _ensure_observed_utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

class TaskDigestMemory(BaseMemory):
    """Structured artifact summarizing a completed or interrupted long-horizon task session.

    TaskDigestMemory stores the goal, milestones, modified/created artifact paths,
    execution outcome, and key diagnostic metrics for post-session audit and cross-session resume.
    """

    content: str = Field(default="", description="Serialized summary or digest content")
    memory_type: Literal[MemoryType.TASK_DIGEST] = MemoryType.TASK_DIGEST
    task_goal: str = Field(..., description="Original high-level objective of the task session")
    status: Literal["completed", "interrupted", "failed"] = Field(
        default="completed", description="Final execution state of the task"
    )
    completed_steps: list[str] = Field(default_factory=list, description="Ordered summary of completed subtasks")
    artifact_paths: list[str] = Field(default_factory=list, description="Output artifacts or files created/modified")
    artifact_hashes: dict[str, str] = Field(
        default_factory=dict, description="Artifact path -> sha256 fingerprint mappings"
    )
    key_findings: list[str] = Field(default_factory=list, description="Important discoveries or conclusions")
    error_lessons: list[str] = Field(default_factory=list, description="Abstracted error avoidance rules")
    tool_call_count: int = Field(default=0, ge=0, description="Total tool invocations during this task")
    source_session_id: str = Field(default="", description="Session ID where this task was executed")

    def model_post_init(self, __context: object) -> None:
        """Ensure content field has informative human-readable text."""
        if not self.content:
            steps_preview = "; ".join(self.completed_steps[:3]) if self.completed_steps else "none"
            self.content = f"Task Goal: {self.task_goal} | Status: {self.status} | Steps: {steps_preview}"
