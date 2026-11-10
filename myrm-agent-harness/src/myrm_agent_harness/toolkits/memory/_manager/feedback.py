"""MemoryManager user-feedback mixin: rating and pinning of a stored memory.

[INPUT]
- memory._manager.host::MemoryManagerHost (POS: typed attribute surface the mixins share)
- memory._manager.shared::{AnyMemory, MemoryError, MemoryNotFoundError, doc_to_episodic, doc_to_semantic} (POS: shared imports and error types)

[OUTPUT]
- MemoryManagerFeedbackMixin: rate_memory, pin_memory, unpin_memory

[POS]
The signals a user gives a memory directly: a 1-5 rating folded into the stored rating, and the pin that
shields it from forgetting. Both rewrite one stored payload field in place and nothing else.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory._manager.host import MemoryManagerHost
from myrm_agent_harness.toolkits.memory._manager.shared import (
    AnyMemory,
    MemoryError,
    MemoryNotFoundError,
    doc_to_episodic,
    doc_to_semantic,
)


class MemoryManagerFeedbackMixin(MemoryManagerHost):
    async def rate_memory(self, memory_id: str, score: int, collection: str | None = None) -> bool:
        """Update a memory's user_rating using asymmetric Exponential Moving Average.

        Score is an integer in [1, 5] (user-facing Likert scale).
        Internally normalized to [0, 1] and applied via asymmetric EMA:
            alpha = alpha_negative if normalized < old_rating else alpha_positive
            rating_new = rating_old + alpha * (normalized - rating_old)

        Asymmetric design: negative feedback decays rating faster than positive
        feedback recovers it, requiring more positive validations to restore trust.

        Args:
            memory_id: Target memory ID.
            score: User feedback score (1=bad, 5=excellent).
            collection: Explicit vector collection. If None, searches both.

        Returns:
            True if the memory was found and updated.
        """
        if self._vector is None:
            return False

        clamped = max(1, min(5, score))
        normalized = (clamped - 1) / 4.0
        alpha_positive = self._config.rating_alpha
        alpha_negative = self._config.rating_alpha_negative

        collections = (
            [collection] if collection else [self._config.semantic_collection, self._config.episodic_collection]
        )
        for coll in collections:
            try:
                docs = await self._vector.get(coll, [memory_id])
            except Exception:
                continue
            if not docs:
                continue
            doc = docs[0]
            stored_uid = doc.metadata.get("user_id")
            if stored_uid and stored_uid != self._user_id:
                continue

            stored_rating = doc.metadata.get("user_rating", 0.5)
            old_rating = float(stored_rating) if isinstance(stored_rating, (int, float, str)) else 0.5
            alpha = alpha_negative if normalized < old_rating else alpha_positive
            new_rating = old_rating + alpha * (normalized - old_rating)
            new_rating = max(0.0, min(1.0, round(new_rating, 4)))
            doc.metadata["user_rating"] = new_rating
            await self._vector.upsert(coll, [doc])
            return True
        return False

    async def pin_memory(self, memory_id: str) -> AnyMemory:
        """Mark a memory as user-pinned (immune to forgetting)."""
        return await self._set_pinned(memory_id, pinned=True)

    async def unpin_memory(self, memory_id: str) -> AnyMemory:
        """Remove user-pinned protection from a memory."""
        return await self._set_pinned(memory_id, pinned=False)

    async def _set_pinned(self, memory_id: str, *, pinned: bool) -> AnyMemory:
        if self._vector is None:
            raise MemoryError("Vector backend is required but not provided")

        for coll, converter in (
            (self._config.semantic_collection, doc_to_semantic),
            (self._config.episodic_collection, doc_to_episodic),
        ):
            docs = await self._vector.get(coll, [memory_id])
            if not docs:
                continue
            doc = docs[0]
            # Ownership is persisted in the payload by the write path. Rows written before
            # that field existed carry no `user_id`; for those the namespace scope remains
            # the boundary, so an absent key is tolerated instead of rejecting the row.
            stored_uid = doc.metadata.get("user_id")
            if stored_uid and stored_uid != self._user_id:
                raise MemoryNotFoundError(f"Memory {memory_id} not found")
            if bool(doc.metadata.get("pinned", False)) == pinned:
                return converter(doc)
            doc.metadata["pinned"] = pinned
            await self._vector.upsert(coll, [doc])
            return converter(doc)

        raise MemoryNotFoundError(f"Memory {memory_id} not found")


__all__ = ["MemoryManagerFeedbackMixin"]
