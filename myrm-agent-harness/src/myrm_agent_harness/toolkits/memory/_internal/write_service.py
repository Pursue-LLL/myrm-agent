"""Write-side orchestration for memory persistence.


[INPUT]
- memory._internal.storage::{store_*} (POS: internal vector storage operations)
- memory._internal.dedup_funcs::{SemanticDedupFunc, EpisodicDedupFunc} (POS: batch deduplication callable types)
- memory._internal.memory_scanner::scan_and_clean_memory (POS: content safety scanner)
- memory._internal.write_builders::MemoryBuildersMixin (POS: constructors of the convenience writes)
- memory._internal.write_fence::{write_grant, within_write_grant} (POS: write-scope fence predicate shared with consolidation)
- memory.agent_surface.transient_fact_boundary::filter_transient_business_memories (POS: L3 write gate for transient business facts)
- memory.strategies.chat_fence::{DELETED_CHAT_REJECTION, derives_from_deleted_chat, keep_live} (POS: refusal of writes derived from a deleted chat)

[OUTPUT]
- MemoryWriter: Write-side orchestrator (scan, transient business fact L3 write gate, deleted-chat fence, approval routing, explicit/inferred write gates, batch dedup, persistence)

[POS]
Write-side orchestration for memory persistence. Handles memory scanning, transient business fact filtering at the L3 write gate,
the refusal of memories derived from a chat that was just deleted (once before approval routing and, for a batch, again after
deduplication, which can merge a stored memory into the write), approval routing, explicit bypass vs inferred force-pending gates,
batch deduplication, and persistence.
Not part of the public API.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from myrm_agent_harness.toolkits.memory._internal.dedup_funcs import EpisodicDedupFunc, SemanticDedupFunc
from myrm_agent_harness.toolkits.memory._internal.memory_scanner import (
    MemoryTaintedError,
    scan_and_clean_memory,
)
from myrm_agent_harness.toolkits.memory._internal.storage import MemoryError, MemoryRejectedError
from myrm_agent_harness.toolkits.memory._internal.write_builders import MemoryBuildersMixin
from myrm_agent_harness.toolkits.memory._internal.write_fence import within_write_grant, write_grant
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.strategies.chat_fence import (
    DELETED_CHAT_REJECTION,
    derives_from_deleted_chat,
    keep_live,
)
from myrm_agent_harness.toolkits.memory.strategies.exact_fact import ExactFactClassifier
from myrm_agent_harness.toolkits.memory.types import (
    AnyMemory,
    ConversationMemory,
    EpisodicMemory,
    MemoryScope,
    ProceduralMemory,
    RuleSource,
    SemanticMemory,
    ToolRulePriority,
)

logger = logging.getLogger(__name__)

ApprovalSubmitFunc = Callable[[AnyMemory], Awaitable[str]]
BindScopeFunc = Callable[[AnyMemory], AnyMemory]


@dataclass(slots=True)
class PartitionedMemories:
    semantic: list[SemanticMemory]
    episodic: list[EpisodicMemory]
    procedural: list[ProceduralMemory]
    conversation: list[ConversationMemory]


class MemoryWriter(MemoryBuildersMixin):
    """Owns write-side validation, batching, and convenience constructors."""

    __slots__ = (
        "_approval_required",
        "_bind_scope",
        "_config",
        "_deduplicate_episodic_batch",
        "_deduplicate_semantic_batch",
        "_namespaces",
        "_scope",
        "_store_conversations_batch",
        "_store_episodic",
        "_store_episodics_batch",
        "_store_procedural",
        "_store_procedurals_batch",
        "_store_semantic",
        "_store_semantics_batch",
        "_submit_pending",
        "_user_id",
    )

    def __init__(
        self,
        *,
        config: MemoryConfig,
        user_id: str,
        scope: MemoryScope,
        namespaces: list[str],
        approval_required: bool,
        bind_scope_func: BindScopeFunc,
        submit_pending_func: ApprovalSubmitFunc,
        store_semantic_func: Callable[[SemanticMemory], Awaitable[SemanticMemory]],
        store_episodic_func: Callable[[EpisodicMemory], Awaitable[EpisodicMemory]],
        store_procedural_func: Callable[[ProceduralMemory], Awaitable[ProceduralMemory]],
        store_semantics_batch_func: Callable[[list[SemanticMemory]], Awaitable[list[SemanticMemory]]],
        store_episodics_batch_func: Callable[[list[EpisodicMemory]], Awaitable[list[EpisodicMemory]]],
        store_procedurals_batch_func: Callable[[list[ProceduralMemory]], Awaitable[list[ProceduralMemory]]],
        store_conversations_batch_func: Callable[[list[ConversationMemory]], Awaitable[list[ConversationMemory]]],
        deduplicate_semantic_batch_func: SemanticDedupFunc,
        deduplicate_episodic_batch_func: EpisodicDedupFunc,
    ) -> None:
        self._config = config
        self._user_id = user_id
        self._scope = scope
        self._namespaces = list(namespaces)
        self._approval_required = approval_required
        self._bind_scope = bind_scope_func
        self._submit_pending = submit_pending_func
        self._store_semantic = store_semantic_func
        self._store_episodic = store_episodic_func
        self._store_procedural = store_procedural_func
        self._store_semantics_batch = store_semantics_batch_func
        self._store_episodics_batch = store_episodics_batch_func
        self._store_procedurals_batch = store_procedurals_batch_func
        self._store_conversations_batch = store_conversations_batch_func
        self._deduplicate_semantic_batch = deduplicate_semantic_batch_func
        self._deduplicate_episodic_batch = deduplicate_episodic_batch_func

    def _routes_to_pending(self, *, bypass_approval: bool, force_pending: bool) -> bool:
        if bypass_approval:
            return False
        if force_pending:
            return True
        return self._approval_required

    def _bind_owner(self, memory: AnyMemory) -> AnyMemory:
        """Stamp the manager owner onto the memory exactly once.

        Ownership has to live on the record itself — not only on the manager — because
        vector payloads are the only persisted copy for semantic/episodic memories.
        Without it, ownership-scoped guards (pin/unpin, delete, consolidation scroll)
        compare against an absent payload key and reject legitimate rows.
        """
        if not memory.user_id:
            memory.user_id = self._user_id
        return memory

    async def store(
        self,
        memory: AnyMemory,
        *,
        bypass_approval: bool = False,
        force_pending: bool = False,
        scope_prevalidated: bool = False,
    ) -> AnyMemory:
        """Persist one memory.

        ``scope_prevalidated`` is for replaying a queued proposal: the write-scope fence
        already ran when the proposal was submitted by the originating writer, and the
        reviewing manager (e.g. the global settings inbox) holds a different grant than
        the proposing agent, so re-checking it here would reject every cross-agent approval.
        """
        self._validate_supported_memory(memory)
        self._attach_current_trace_id(memory)
        bound_memory = self._bind_for_store(memory, scope_prevalidated=scope_prevalidated)
        if not scope_prevalidated:
            self._validate_write_scope(bound_memory)
        if self._config.security_scan_enabled:
            scan_and_clean_memory(bound_memory, block_threshold=self._config.injection_block_threshold)

        if isinstance(bound_memory, ProceduralMemory):
            self._enforce_agent_self_priority_ceiling(bound_memory)

        if force_pending:
            bound_memory.metadata["write_intent"] = "inferred"

        bound_memory = self._require_transient_fact_allowed(bound_memory)
        bound_memory = self._apply_exact_fact_lock(bound_memory)

        if derives_from_deleted_chat(self._user_id, bound_memory):
            raise MemoryRejectedError(DELETED_CHAT_REJECTION)

        if self._routes_to_pending(bypass_approval=bypass_approval, force_pending=force_pending):
            pending_id = await self._submit_pending(bound_memory)
            if not pending_id:
                raise MemoryRejectedError(
                    "Not saved: the same memory is already waiting for the user's approval. Do not save it again."
                )
            bound_memory.metadata["_pending_id"] = pending_id
            return bound_memory

        if isinstance(bound_memory, SemanticMemory):
            return await self._store_semantic(bound_memory)
        if isinstance(bound_memory, EpisodicMemory):
            return await self._store_episodic(bound_memory)
        if isinstance(bound_memory, ProceduralMemory):
            return await self._store_procedural(bound_memory)
        raise ValueError(f"Unknown memory type: {type(bound_memory).__name__}")

    def _apply_exact_fact_lock(self, memory: AnyMemory) -> AnyMemory:
        extracted = ExactFactClassifier.extract_identifiers(memory.content)
        if extracted or getattr(memory, "is_exact_fact", False):
            memory.is_exact_fact = True
            existing = set(getattr(memory, "exact_identifiers", []) or [])
            existing.update(extracted)
            memory.exact_identifiers = sorted(existing)
        return memory

    async def store_batch(
        self,
        memories: Sequence[AnyMemory],
        *,
        bypass_approval: bool = False,
        force_pending: bool = False,
        skip_dedup: bool = False,
    ) -> list[AnyMemory]:
        if not memories:
            return []

        for memory in memories:
            self._validate_supported_memory(memory)
            self._attach_current_trace_id(memory)
        bound_memories = [self._bind_owner(self._bind_scope(memory)) for memory in memories]
        for bound_memory in bound_memories:
            self._validate_write_scope(bound_memory)
        safe_memories = self._scan_batch(bound_memories)
        if not safe_memories:
            return []

        for mem in safe_memories:
            if isinstance(mem, ProceduralMemory):
                self._enforce_agent_self_priority_ceiling(mem)
            if force_pending:
                mem.metadata["write_intent"] = "inferred"

        safe_memories = self._filter_transient_business_batch(safe_memories)
        if not safe_memories:
            return []
        safe_memories = keep_live(self._user_id, [self._apply_exact_fact_lock(m) for m in safe_memories])
        if not safe_memories:
            return []

        if self._routes_to_pending(bypass_approval=bypass_approval, force_pending=force_pending):
            results: list[AnyMemory] = []
            for memory in safe_memories:
                pending_id = await self._submit_pending(memory)
                if pending_id:
                    memory.metadata["_pending_id"] = pending_id
                    results.append(memory)
            return results

        partitioned = self._partition_memories(safe_memories)
        if not skip_dedup:
            # Deduplication can merge a stored memory into the write, and the chat that memory derives from may have
            # been deleted while it ran.
            if partitioned.semantic:
                partitioned.semantic = keep_live(
                    self._user_id, await self._deduplicate_semantic_batch(partitioned.semantic)
                )
            if partitioned.episodic:
                partitioned.episodic = keep_live(
                    self._user_id, await self._deduplicate_episodic_batch(partitioned.episodic)
                )

        stores: list[Awaitable[Sequence[AnyMemory]]] = []
        if partitioned.semantic:
            stores.append(self._store_semantics_batch(partitioned.semantic))
        if partitioned.episodic:
            stores.append(self._store_episodics_batch(partitioned.episodic))
        if partitioned.procedural:
            stores.append(self._store_procedurals_batch(partitioned.procedural))
        if partitioned.conversation:
            stores.append(self._store_conversations_batch(partitioned.conversation))

        batches = await asyncio.gather(*stores)
        return [memory for batch in batches for memory in batch]

    def _filter_transient_business_batch(self, memories: Sequence[AnyMemory]) -> list[AnyMemory]:
        from myrm_agent_harness.toolkits.memory.agent_surface.transient_fact_boundary import (
            filter_transient_business_memories,
        )
        from myrm_agent_harness.toolkits.memory.profile_notes import filter_intake_garbage

        clean_mems, g_dropped = filter_intake_garbage(memories)
        if g_dropped:
            logger.info("Intake garbage filter dropped %d transient memories", g_dropped)

        filtered, dropped = filter_transient_business_memories(clean_mems)
        if dropped:
            logger.info("Transient business fact gate dropped %d memories", dropped)
        return filtered

    def _require_transient_fact_allowed(self, memory: AnyMemory) -> AnyMemory:
        from myrm_agent_harness.toolkits.memory.agent_surface.transient_fact_boundary import (
            transient_fact_save_rejection_message,
        )
        from myrm_agent_harness.toolkits.memory.profile_notes import check_memory_not_garbage

        check_memory_not_garbage(memory)
        filtered = self._filter_transient_business_batch([memory])
        if not filtered:
            raise MemoryRejectedError(transient_fact_save_rejection_message())
        return filtered[0]

    def _scan_batch(self, memories: Sequence[AnyMemory]) -> list[AnyMemory]:
        if not self._config.security_scan_enabled:
            return list(memories)

        safe_memories: list[AnyMemory] = []
        threshold = self._config.injection_block_threshold
        for memory in memories:
            try:
                scan_and_clean_memory(memory, block_threshold=threshold)
                safe_memories.append(memory)
            except MemoryTaintedError:
                continue  # rejected: counted and logged by the scanner; siblings are unaffected
        return safe_memories

    def _partition_memories(self, memories: Sequence[AnyMemory]) -> PartitionedMemories:
        semantic: list[SemanticMemory] = []
        episodic: list[EpisodicMemory] = []
        procedural: list[ProceduralMemory] = []
        conversation: list[ConversationMemory] = []

        for memory in memories:
            if isinstance(memory, SemanticMemory):
                semantic.append(memory)
            elif isinstance(memory, EpisodicMemory):
                episodic.append(memory)
            elif isinstance(memory, ProceduralMemory):
                procedural.append(memory)
            elif isinstance(memory, ConversationMemory):
                conversation.append(memory)
            else:
                raise ValueError(f"Unknown memory type: {type(memory).__name__}")

        return PartitionedMemories(
            semantic=semantic,
            episodic=episodic,
            procedural=procedural,
            conversation=conversation,
        )

    def _validate_supported_memory(self, memory: AnyMemory) -> None:
        if not isinstance(
            memory,
            (SemanticMemory, EpisodicMemory, ProceduralMemory, ConversationMemory),
        ):
            raise ValueError(f"Unknown memory type: {type(memory).__name__}")

    def _validate_write_scope(self, memory: AnyMemory) -> None:
        """Refuse writes whose namespaces fall outside this writer's grant.

        A memory may only target the writer's own write scope plus
        shared-capable read namespaces (``global`` or ``shared:*``). Any other
        read-only namespace (e.g. another agent's private space) must not be
        written into; fail loud instead of silently persisting.
        """
        grant = write_grant(self._scope, self._namespaces)
        if not within_write_grant(memory.scope.namespaces, grant):
            raise MemoryError(
                f"Memory write scope {sorted(set(memory.scope.namespaces))} exceeds allowed scope {sorted(grant)}"
            )

    @staticmethod
    def _attach_current_trace_id(memory: AnyMemory) -> None:
        """Inject active execution trace ID into memory if not already set."""
        if hasattr(memory, "trace_id") and not getattr(memory, "trace_id", None):
            try:
                from myrm_agent_harness.observability.tracing import resolve_current_trace_id

                tid = resolve_current_trace_id()
                if tid:
                    memory.trace_id = tid
            except Exception:
                pass

    @staticmethod
    def _enforce_agent_self_priority_ceiling(memory: ProceduralMemory) -> None:
        """Prevent AGENT_SELF rules from claiming CRITICAL priority."""
        if memory.source == RuleSource.AGENT_SELF and memory.tool_rule_priority == ToolRulePriority.CRITICAL:
            memory.tool_rule_priority = ToolRulePriority.HIGH
            logger.warning(
                "Downgraded AGENT_SELF rule from CRITICAL to HIGH: %s",
                memory.content[:60],
            )

    def _bind_for_store(self, memory: AnyMemory, *, scope_prevalidated: bool) -> AnyMemory:
        """Bind the memory to this writer, except that a replayed proposal keeps the scope it was queued with.

        The reviewing manager is bound to another agent, so binding the proposal again would move a rule out of the
        agent that proposed it. A proposal queued without any scope still takes the reviewer's.
        """
        keeps_queued_scope = scope_prevalidated and bool(memory.scope.namespaces)
        return self._bind_owner(memory if keeps_queued_scope else self._bind_scope(memory))
