"""MemoryManager mixin module (internal). Do not import directly."""

from __future__ import annotations

import asyncio
from typing import Literal, cast

from myrm_agent_harness.toolkits.memory._internal.rule_text import RuleFields, edited_rule_fields
from myrm_agent_harness.toolkits.memory._internal.unit_interval import require_unit_interval
from myrm_agent_harness.toolkits.memory._manager.host import MemoryManagerHost
from myrm_agent_harness.toolkits.memory._manager.shared import (
    UTC,
    AnyMemory,
    ConversationMemory,
    EmbeddingProtocol,
    EpisodicMemory,
    MemoryError,
    MemoryNotFoundError,
    MemoryProtectedError,
    MemoryRejectedError,
    MemoryStatus,
    ProceduralMemory,
    SemanticMemory,
    archive_retention_stamps,
    datetime,
    get_from_vector,
    logger,
    scan_and_clean_memory,
    update_vector_memory,
)
from myrm_agent_harness.toolkits.memory.strategies.exact_fact import ExactFactClassifier
from myrm_agent_harness.toolkits.memory.strategies.sparse_mutation import (
    apply_sparse_mutation,
)

ExactFactIndexAction = Literal["record", "delete"]


def _restamp_exact_fact(
    memory: SemanticMemory, *, is_exact_fact: bool | None, content_changed: bool
) -> ExactFactIndexAction | None:
    """Re-derive a knowledge memory's exact-fact flag and identifiers from its final content.

    Runs after the security scan so the identifiers and the index follow the stored (redacted) text;
    returns the index change the memory needs, if any. An explicit ``is_exact_fact`` wins. Without
    one only a content change re-stamps, and it stamps the way a new write does: text that carries an
    identifier makes the memory an exact fact, and a memory that already was one keeps the stamp. Only
    knowledge memories carry the stamp: it is persisted with them and the exact-identifier stream
    serves only them.
    """
    if is_exact_fact is None and not content_changed:
        return None
    identifiers = ExactFactClassifier.extract_identifiers(memory.content)
    if is_exact_fact is not None:
        memory.is_exact_fact = is_exact_fact
    elif memory.is_exact_fact or identifiers:
        memory.is_exact_fact = True
    else:
        return None
    memory.exact_identifiers = identifiers if memory.is_exact_fact else []
    return "record" if memory.is_exact_fact else "delete"


class MemoryManagerMutationsMixin(MemoryManagerHost):
    async def _sync_exact_fact_index(self, memory: AnyMemory, action: ExactFactIndexAction | None) -> None:
        """Mirror a stored memory's exact-fact state into the side index; failures only warn."""
        if self._relational is None or action is None:
            return
        try:
            if action == "record":
                await self._relational.record_exact_fact(
                    memory_id=memory.id,
                    user_id=memory.user_id,
                    content=memory.content,
                    identifiers=memory.exact_identifiers,
                    primary_namespace=memory.scope.primary_namespace if memory.scope else "",
                    namespaces=memory.scope.namespaces if memory.scope else None,
                )
            else:
                await self._relational.delete_exact_fact(memory.id)
        except Exception as err:
            logger.warning("Failed to sync exact fact index: %s", err)

    # ── Get / Update single memory ──

    async def get_memory(self, memory_id: str) -> AnyMemory | None:
        return await self._find_memory(memory_id, self._namespaces)

    async def _memory_exists_in_any_scope(self, memory_id: str) -> bool:
        """Whether the memory exists in any namespace, including ones this manager cannot read."""
        return await self._find_memory(memory_id, None) is not None

    async def _find_memory(self, memory_id: str, namespaces: list[str] | None) -> AnyMemory | None:
        """Look a memory up across stores; ``namespaces=None`` skips the namespace filter."""
        tasks: list[asyncio.Task[AnyMemory | None]] = []
        if self._vector is not None:
            tasks.append(
                asyncio.create_task(
                    get_from_vector(
                        memory_id,
                        self._vector,
                        self._config,
                        namespaces=namespaces,
                    )
                )
            )
        if self._relational is not None:
            tasks.append(asyncio.create_task(self._relational.get_rule(memory_id, namespaces=namespaces)))
        for r in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(r, BaseException):
                logger.warning("Get memory error: %s", r)
            elif r is not None:
                return r
        return None

    async def correct_memory(
        self, memory_id: str, corrected_content: str, *, allow_protected: bool = True
    ) -> SemanticMemory:
        """Correct a factually wrong memory: store a linked correction, then demote the old one.

        The correction passes the same write pipeline as any other memory (security scan,
        transient-fact gate, exact-fact lock) and the old memory is demoted only once it was
        accepted, so a rejected correction changes nothing. ``allow_protected=False``
        (automated and agent-facing paths) refuses to demote a memory the user protected.
        Returns the newly created correction memory.
        """
        existing = await self.get_memory(memory_id)
        if existing is None:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")
        if not isinstance(existing, SemanticMemory):
            raise MemoryError(f"Correction only supports SemanticMemory, got {type(existing).__name__}")
        if not allow_protected and existing.is_user_protected:
            raise MemoryProtectedError(
                f"Memory {memory_id} is protected by the user; automated corrections are not allowed"
            )
        if self._vector is None:
            raise MemoryError("Vector backend required")

        mutation_res = apply_sparse_mutation(existing.content, corrected_content)
        final_content = (
            mutation_res.mutated_text
            if (mutation_res.is_mutated and mutation_res.retained_count > 0)
            else corrected_content
        )

        correction_meta = dict(existing.metadata or {})
        if mutation_res.is_mutated and mutation_res.retained_count > 0:
            correction_meta["last_sparse_mutation"] = mutation_res.summary
            correction_meta["sparse_retained_count"] = mutation_res.retained_count
            correction_meta["sparse_overwritten_count"] = mutation_res.overwritten_count

        pref_strength = min(existing.preference_strength + 0.1, 1.0) if existing.preference_strength > 0 else 0.0
        correction = SemanticMemory(
            content=final_content,
            importance=min(existing.importance + 0.2, 1.0),
            confidence=0.95,
            tags=existing.tags,
            source_chat_id=existing.source_chat_id,
            source_chat_ids=list(existing.source_chat_ids),
            preference_type=existing.preference_type,
            preference_strength=pref_strength,
            correction_of=memory_id,
            metadata=correction_meta,
        )
        stored = cast(SemanticMemory, await self.store(correction, _bypass_approval=True))

        demoted = existing.model_copy(deep=True)
        demoted.importance = max(existing.importance * 0.3, 0.05)
        demoted.confidence = 0.1
        # The superseded fact must stop outranking its correction in the exact-identifier stream.
        demoted.is_exact_fact = False
        demoted.exact_identifiers = []
        demoted.metadata = {**demoted.metadata, "corrected": True}
        demoted.updated_at = datetime.now(UTC)
        await update_vector_memory(demoted, False, self._vector, self._config, self._embedding, self._cache)
        await self._sync_exact_fact_index(demoted, "delete")
        return stored

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
    ) -> AnyMemory:
        """Update a memory in place.

        ``allow_protected=False`` (automated and agent-facing paths) refuses to
        touch a memory the user protected, so the guard lives in one place
        instead of being re-implemented at every call site. The WebUI keeps the
        default ``True`` because the user is entitled to edit their own data.

        ``importance`` and ``confidence`` must lie in 0.0-1.0 and content that reads as a
        transient business fact is refused; both raise ``MemoryRejectedError`` before
        anything is written.

        Replacing the ``content`` of a rule stored as its display line rewrites its ``trigger`` and
        ``action`` as well, because the prompt is built from those (see ``rule_text``); any other rule
        keeps them. An empty rule text is refused the same way.

        Replacing the ``content`` of a knowledge memory stamps it as an exact fact when the new text
        carries an identifier, as a new write does, so the memory is then protected from automated edits.
        """
        require_unit_interval("importance", importance, action="updated")
        require_unit_interval("confidence", confidence, action="updated")
        existing = await self.get_memory(memory_id)
        if existing is None:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")

        content_changed = content is not None
        if not allow_protected and existing.is_user_protected:
            raise MemoryProtectedError(f"Memory {memory_id} is protected by the user; automated writes are not allowed")

        updated = existing.model_copy(deep=True)

        if content is not None:
            updated.metadata = {
                **updated.metadata,
                "previous_content": existing.content,
            }
            stored_content = content
            if isinstance(updated, ProceduralMemory):
                held = RuleFields(updated.trigger, updated.action, updated.content)
                updated.trigger, updated.action, stored_content = edited_rule_fields(held, content)
            updated.content = stored_content
            if isinstance(updated, (SemanticMemory, EpisodicMemory)):
                from myrm_agent_harness.toolkits.memory.agent_surface.transient_fact_boundary import (
                    looks_like_transient_business_fact,
                    transient_fact_save_rejection_message,
                )

                if looks_like_transient_business_fact(content):
                    raise MemoryRejectedError(transient_fact_save_rejection_message())
        if importance is not None and isinstance(updated, (SemanticMemory, EpisodicMemory, ConversationMemory)):
            updated.importance = importance
        if confidence is not None and isinstance(updated, SemanticMemory):
            updated.confidence = confidence
        if tags is not None and isinstance(updated, SemanticMemory):
            updated.tags = tags
        if status is not None:
            updated.status = status
            if status == MemoryStatus.ARCHIVED:
                # Re-archiving keeps the original deadline so repeated deletes cannot push
                # back the purge of data the user asked to forget. An archive that carries
                # no retention stamp is still stamped, otherwise the purge scanner could
                # never reclaim it.
                already_reclaimable = existing.status == MemoryStatus.ARCHIVED and bool(
                    existing.metadata.get("archive_expires_at") or existing.metadata.get("archived_at")
                )
                if not already_reclaimable:
                    now = datetime.now(UTC)
                    updated.metadata = {
                        **updated.metadata,
                        **archive_retention_stamps(now),
                        "archive_reason": "user_deleted",
                    }
                    await self._cascade_clean_derived_graph_nodes(memory_id)
                    if self._cache is not None and updated.content:
                        await self._cache.evict(updated.content)
            elif existing.status == MemoryStatus.ARCHIVED and status == MemoryStatus.ACTIVE:
                updated.metadata.pop("archived_at", None)
                updated.metadata.pop("archive_expires_at", None)
                updated.metadata.pop("archive_reason", None)
            if isinstance(updated, ProceduralMemory):
                updated.is_active = status == MemoryStatus.ACTIVE
        elif is_active is not None and isinstance(updated, ProceduralMemory):
            updated.is_active = is_active
            updated.status = MemoryStatus.ACTIVE if is_active else MemoryStatus.DISABLED
        if metadata is not None:
            # Callers pass the complete metadata they computed from the current one
            # (dropping keys is how the consolidation undo and the subsumption
            # undo clear their markers), so this replaces it instead of merging.
            updated.metadata = dict(metadata)
        if isinstance(updated, ProceduralMemory):
            if reasoning is not None:
                updated.reasoning = reasoning
            if application is not None:
                updated.application = application
            if is_user_locked is not None:
                updated.is_user_locked = is_user_locked

        updated.updated_at = datetime.now(UTC)

        if content_changed and self._config.security_scan_enabled:
            scan_and_clean_memory(updated, block_threshold=self._config.injection_block_threshold)

        index_action = (
            _restamp_exact_fact(updated, is_exact_fact=is_exact_fact, content_changed=content_changed)
            if isinstance(updated, SemanticMemory)
            else None
        )

        if isinstance(updated, (SemanticMemory, EpisodicMemory)):
            if self._vector is None:
                raise MemoryError("Vector backend required")
            e: EmbeddingProtocol | None = None
            if content_changed:
                e = self._embedding
            result = await update_vector_memory(
                self._bind_scope(updated),
                content_changed,
                self._vector,
                self._config,
                e,
                self._cache,
            )
            await self._sync_exact_fact_index(result, index_action)
            if content_changed:
                self._record_ephemeral_delta_for_memory(result)
            return result
        if isinstance(updated, ProceduralMemory):
            return await self._rel().update_rule(memory_id, updated)
        raise ValueError(f"Cannot update memory type: {type(updated).__name__}")
