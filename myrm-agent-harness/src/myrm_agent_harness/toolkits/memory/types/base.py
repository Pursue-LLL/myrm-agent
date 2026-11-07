"""[INPUT]
- enums::MemoryTier / DigestKind / EvaporationState / ClaimGraphState / ClaimConflictState / MemoryStatus (POS: 记忆枚举)
- domain_types::MemoryDomain / infer_domain_and_category (POS: 领域分区推断)
- pydantic::BaseModel / Field / field_validator / model_validator (POS: 校验与序列化)

[OUTPUT]
- BaseMemory / MemoryScope / MemoryLifecycle / EvidenceReference: 记忆基础模型
- ARCHIVE_RETENTION_DAYS / archive_retention_stamps: 归档保留窗口
- MemoryMutationRef / MemoryMutationResult / ProfileAttributeSnapshot: 变更与快照 DTO

[POS]
`memory/types_pkg/` 的基础模型层；所有具体记忆类型都继承 `BaseMemory`。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Self
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from myrm_agent_harness.toolkits.memory.domain_types import (
    MemoryDomain,
    infer_domain_and_category,
)

from .enums import (
    ClaimConflictState,
    ClaimGraphState,
    DigestKind,
    EvaporationState,
    MemoryStatus,
    MemoryTier,
)


class EvidenceReference(BaseModel):
    """Structured evidence anchor linking extracted facts to raw interaction context."""

    source_id: str = Field(..., description="Unique ID of source conversation, document or turn")
    message_id: str | None = Field(default=None, description="Granular message ID if available")
    channel_id: str | None = Field(default=None, description="Channel identifier (e.g. slack, telegram, web)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Interaction timestamp")
    quote_snippet: str | None = Field(default=None, description="Exact verbatim snippet serving as factual evidence")
    author_id: str | None = Field(default=None, description="Sender ID of the evidentiary message")


ARCHIVE_RETENTION_DAYS = 7


def archive_retention_stamps(now: datetime) -> dict[str, str]:
    """Build the metadata pair every archival write path must stamp.

    ``archived_at`` drives the trash listing order, and ``archive_expires_at``
    is the retention deadline the purge scanner reads to reclaim the entry.
    Deriving both from one instant keeps them consistent and guarantees the
    entry is reclaimable, so no archival path can leak an immortal record.
    """
    return {
        "archived_at": now.isoformat(),
        "archive_expires_at": (now + timedelta(days=ARCHIVE_RETENTION_DAYS)).isoformat(),
    }


class MemoryMutationRef(BaseModel):
    """A single typed memory mutation outcome reference."""

    memory_type: str
    memory_id: str
    backend: str
    reason: str = ""


class MemoryMutationResult(BaseModel):
    """Exact outcome of a typed memory mutation request."""

    deleted_refs: list[MemoryMutationRef] = Field(default_factory=list)
    missing_refs: list[MemoryMutationRef] = Field(default_factory=list)
    forbidden_refs: list[MemoryMutationRef] = Field(default_factory=list)
    failed_refs: list[MemoryMutationRef] = Field(default_factory=list)

    def deleted_counts_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for ref in self.deleted_refs:
            counts[ref.memory_type] = counts.get(ref.memory_type, 0) + 1
        return counts


class ProfileAttributeSnapshot(BaseModel):
    """Content-local profile attribute value and revision."""

    key: str
    value: str | None = None
    exists: bool = False
    revision: str = ""
    updated_at: datetime | None = None


class MemoryScope(BaseModel):
    """Deterministic ownership and session identity for a memory record.

    ``primary_namespace`` is the authoritative single namespace used by the
    vector layer for precise scope filtering (exact IN matching against the
    single-value payload field), so one agent can never match another agent's
    private memories through a shared broadcast namespace. ``namespaces`` is an
    ordered broad-to-narrow scope list kept for display and scope
    reconstruction only; it must not be used for permission filtering.
    """

    primary_namespace: str = ""
    namespaces: list[str] = Field(default_factory=list)
    client_id: str | None = None
    agent_id: str | None = None
    channel_id: str | None = None
    conversation_id: str | None = None
    task_id: str | None = None


class MemoryLifecycle(BaseModel):
    """Typed lifecycle state for compiled / staged memories.

    This model replaces ad-hoc metadata strings for tiered memory flows such as
    task digests and claim graph compilation.
    """

    tier: MemoryTier
    digest_kind: DigestKind | None = None
    evaporation_state: EvaporationState | None = None
    evaporated_at: datetime | None = None
    claim_graph_state: ClaimGraphState | None = None
    claim_graph_node_id: str | None = None
    claim_graph_updated_at: datetime | None = None
    claim_graph_conflict: ClaimConflictState | None = None

    @field_validator("evaporated_at", "claim_graph_updated_at", mode="before")
    @classmethod
    def _ensure_utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

    @classmethod
    def new_task_digest(cls) -> MemoryLifecycle:
        return cls(
            tier=MemoryTier.L2,
            digest_kind=DigestKind.TASK,
            evaporation_state=EvaporationState.PENDING,
            claim_graph_state=ClaimGraphState.PENDING,
            claim_graph_conflict=ClaimConflictState.NONE,
        )


class BaseMemory(BaseModel):
    """Common fields shared by all memory types.

    Sharing is represented by ``scope.namespaces`` rather than business-specific
    fields. Product layers can bind their own concepts to framework-safe
    namespace strings, e.g. ``shared:customer-a``.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = Field(
        default="",
        description="Owner identifier persisted to the vector payload for ownership-scoped guards",
    )
    content: str = Field(..., description="Memory text content")
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stored_at: datetime | None = Field(
        default=None,
        description=(
            "Instant the store persisted this memory, from a clock that never repeats within a process. "
            "Unlike created_at, which a late approval, an import or a correction carries from its own "
            "source, it orders arrival. The store sets it on every write and a vector document carries it "
            "back on every read; a procedural rule's row records its insert time as created_at instead."
        ),
    )
    access_count: int = Field(default=0)
    last_accessed_at: datetime | None = None
    user_rating: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="User feedback rating [0,1]. 0.5 = neutral (no feedback yet). Updated via EMA.",
    )
    pinned: bool = Field(default=False, description="User-pinned: immune to forgetting")
    is_user_locked: bool = Field(
        default=False,
        description="Protected against automated background distillation and overwrite",
    )
    expected_valid_days: int | None = Field(
        default=None,
        description="LLM-estimated validity window in days. None = use global half-life fallback.",
    )
    status: MemoryStatus = Field(default=MemoryStatus.ACTIVE, description="Unified lifecycle status")
    trace_id: str | None = Field(default=None, description="Execution trace ID that produced this memory commit")
    scope: MemoryScope = Field(default_factory=MemoryScope)
    lifecycle: MemoryLifecycle | None = None
    evidence: list[EvidenceReference] = Field(
        default_factory=list, description="Structured provenance evidence anchoring this fact"
    )
    is_exact_fact: bool = Field(
        default=False,
        description="Exact fact hard lock: zero-loss verbatim persistence and deterministic recall",
    )
    exact_identifiers: list[str] = Field(
        default_factory=list,
        description="Extracted high-entropy exact symbols (UUID, SHA, SemVer, config keys)",
    )
    summary_l0: str = Field(
        default="",
        description="L0 minimal semantic anchor (<=120 chars) for fast gating and token-efficient indexing",
    )
    overview_l1: str = Field(
        default="",
        description="L1 structured factual overview (<=400 chars) for default recall injection",
    )
    domain: MemoryDomain = Field(
        default=MemoryDomain.USER,
        description="Persona/experience domain partition (user, assistant, task)",
    )
    domain_category: str = Field(
        default="",
        description="Fine-grained category under the domain (profile, preferences, identity, soul, etc.)",
    )

    @model_validator(mode="after")
    def _fill_progressive_defaults(self) -> Self:
        if not self.summary_l0 and self.content:
            clean = self.content.strip()
            self.summary_l0 = clean[:120].strip()
        if not self.domain_category:
            mem_type = str(getattr(self, "memory_type", "semantic"))
            ev_type = str(getattr(self, "event_type", ""))
            pref_type = getattr(self, "preference_type", None)
            tags = getattr(self, "tags", None)
            inferred_domain, inferred_cat = infer_domain_and_category(
                mem_type,
                content=self.content,
                event_type=ev_type,
                preference_type=pref_type,
                tags=tags,
            )
            if self.domain == MemoryDomain.USER and inferred_domain != MemoryDomain.USER:
                self.domain = inferred_domain
            self.domain_category = inferred_cat.value
        return self

    @property
    def is_user_protected(self) -> bool:
        """Whether the user's protection applies, whichever flag carries it.

        ``pinned`` is the persisted lock for vector memories; ``is_user_locked``
        is the persisted lock for procedural rules; ``is_exact_fact`` protects
        exact identifiers against lossy compression. Automated writers check this
        single predicate so neither flag can be silently bypassed.
        """
        return self.pinned or self.is_user_locked or self.is_exact_fact

    @field_validator("created_at", "updated_at", "last_accessed_at", "stored_at", mode="before")
    @classmethod
    def _ensure_utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v
