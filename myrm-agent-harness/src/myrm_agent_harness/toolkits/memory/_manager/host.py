"""Typed declaration of the state and cross-mixin methods every MemoryManager part relies on.

[INPUT]
- langchain_core.language_models.chat_models::BaseChatModel (POS: consolidation LLM type)
- memory._manager.shared (POS: collaborator and memory types re-exported for the manager package)
- memory.session::MemorySession (POS: active session handle)
- memory.strategies.consolidation (POS: consolidation callbacks)

[OUTPUT]
- MemoryManagerHost: annotation-only base shared by MemoryManagerCore and every mixin

[POS]
MemoryManagerCore assigns the shared attributes and the mixins call each other through
``self``. Declaring both once, with no runtime footprint, lets static checkers resolve
``self._vector`` or ``self.store`` inside any mixin and checks each stub against the real
implementation through override checking; ``tests/toolkits/memory/test_manager_host_stubs.py``
keeps the stub signatures aligned with the implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Awaitable, Callable, Sequence

    from langchain_core.language_models.chat_models import BaseChatModel

    from myrm_agent_harness.toolkits.memory._manager.shared import (
        AgentMemoryPolicy,
        AnyMemory,
        ConsolidationConfig,
        ConversationMemory,
        EmbeddingCacheProtocol,
        EmbeddingProtocol,
        EpisodicMemory,
        FilterDict,
        GovernanceService,
        GraphStoreProtocol,
        MaintenanceService,
        MemoryConfig,
        MemoryRetriever,
        MemoryScope,
        MemorySearchService,
        MemoryStatus,
        MemoryType,
        MemoryWriter,
        PreferenceStabilityStrategy,
        ProceduralMemory,
        RecallMode,
        RecurrenceDetector,
        RelationalStoreProtocol,
        SemanticMemory,
        VectorDocument,
        VectorStoreProtocol,
    )
    from myrm_agent_harness.toolkits.memory.session import MemorySession
    from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
        ConflictCallback,
        ConsolidationCompleteCallback,
    )
    from myrm_agent_harness.toolkits.memory.types import PendingResolutionAction


class MemoryManagerHost:
    """Annotation-only base; ``__slots__ = ()`` keeps the composed manager's layout unchanged."""

    __slots__ = ()

    _user_id: str
    _config: MemoryConfig
    _relational: RelationalStoreProtocol | None
    _vector: VectorStoreProtocol | None
    _graph: GraphStoreProtocol | None
    _embedding: EmbeddingProtocol | None
    _cache: EmbeddingCacheProtocol | None
    _namespaces: list[str]
    _scope: MemoryScope
    _recall_mode: RecallMode
    _memory_policy: AgentMemoryPolicy | None
    _retriever: MemoryRetriever
    _writer: MemoryWriter
    _search_service: MemorySearchService
    _governance: GovernanceService
    _maintenance_service: MaintenanceService
    _maintenance_lock: asyncio.Lock
    _consolidation_llm: BaseChatModel | None
    _preference_strategy: PreferenceStabilityStrategy | None
    _recurrence_detector: RecurrenceDetector | None
    _active_session: MemorySession | None
    _on_conflict: ConflictCallback | None
    _on_consolidation_complete: ConsolidationCompleteCallback | None
    _sparse_authoritative: bool
    _approval_required: bool
    _last_cited_memory_ids: list[str]
    _session_count: int
    _stores_since_consolidation: int

    if TYPE_CHECKING:

        def _bind_scope[T: AnyMemory](self, memory: T) -> T: ...

        def _build_text_llm_func(self) -> Callable[[str, str], Awaitable[str]] | None: ...

        async def _cascade_clean_derived_graph_nodes(self, memory_id: str) -> None: ...

        async def _collect_vector_ids(self, collection: str, filters: FilterDict) -> list[tuple[str, bool]]: ...

        def _maybe_consolidate(self) -> None: ...

        async def _memory_exists_in_any_scope(self, memory_id: str) -> bool: ...

        @staticmethod
        def _record_ephemeral_delta_for_memory(memory: AnyMemory) -> None: ...

        def _rel(self) -> RelationalStoreProtocol: ...

        async def _run_consolidation_safe(self, cfg: ConsolidationConfig) -> None: ...

        async def _store_conversations_batch(self, memories: list[ConversationMemory]) -> list[ConversationMemory]: ...

        async def _store_episodic(self, memory: EpisodicMemory) -> EpisodicMemory: ...

        async def _store_episodics_batch(self, memories: list[EpisodicMemory]) -> list[EpisodicMemory]: ...

        async def _store_procedural(self, memory: ProceduralMemory) -> ProceduralMemory: ...

        async def _store_procedurals_batch(self, memories: list[ProceduralMemory]) -> list[ProceduralMemory]: ...

        async def _store_semantic(self, memory: SemanticMemory) -> SemanticMemory: ...

        async def _store_semantics_batch(self, memories: list[SemanticMemory]) -> list[SemanticMemory]: ...

        async def _submit_preference_candidate(self, memory: AnyMemory) -> None: ...

        async def _warmup_embedding_cache(self) -> None: ...

        @property
        def approval_required(self) -> bool: ...

        async def correct_memory(
            self, memory_id: str, corrected_content: str, *, allow_protected: bool = True
        ) -> SemanticMemory: ...

        def get_enabled_types(self) -> list[MemoryType]: ...

        async def get_memory(self, memory_id: str) -> AnyMemory | None: ...

        @property
        def has_relational(self) -> bool: ...

        @property
        def has_vector(self) -> bool: ...

        async def list_memories(
            self,
            memory_type: MemoryType,
            *,
            limit: int = 100,
            offset: int = 0,
            include_archived: bool = False,
            sort_by: str | None = None,
            sort_order: str = "desc",
            tag_filter: str | None = None,
        ) -> list[AnyMemory]: ...

        async def store(
            self,
            memory: AnyMemory,
            *,
            _bypass_approval: bool = False,
            _force_pending: bool = False,
            _scope_prevalidated: bool = False,
        ) -> AnyMemory: ...

        async def store_batch(
            self, memories: Sequence[AnyMemory], *, _bypass_approval: bool = False, _force_pending: bool = False
        ) -> list[AnyMemory]: ...

        async def submit_pending(
            self,
            memory: AnyMemory,
            *,
            resolution_action: PendingResolutionAction = PendingResolutionAction.STORE,
            target_memory_id: str | None = None,
            target_content: str | None = None,
        ) -> str: ...

        async def update_memory(
            self,
            memory_id: str,
            *,
            content: str | None = None,
            importance: float | None = None,
            confidence: float | None = None,
            tags: list[str] | None = None,
            metadata: dict[str, str | int | float | bool] | None = None,
            is_active: bool | None = None,
            status: MemoryStatus | None = None,
            reasoning: str | None = None,
            application: str | None = None,
            is_user_locked: bool | None = None,
            is_exact_fact: bool | None = None,
            allow_protected: bool = True,
        ) -> AnyMemory: ...

        async def delete_memory(self, collection: str, ids: list[str], *, allow_protected: bool = True) -> int: ...

        async def delete_rule(self, rule_id: str, *, allow_protected: bool = True) -> bool: ...

        async def _collect_vector_docs(self, collection: str, filters: FilterDict) -> list[VectorDocument]: ...

        def _owns_vector_doc(self, doc: VectorDocument) -> bool: ...

        async def delete_memories_by_metadata(
            self, metadata_key: str, metadata_value: str, *, memory_types: Sequence[MemoryType] | None = None
        ) -> dict[str, int]: ...
