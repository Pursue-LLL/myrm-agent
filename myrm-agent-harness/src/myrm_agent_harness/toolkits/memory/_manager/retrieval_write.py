"""MemoryManager mixin module (internal). Do not import directly."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime

from myrm_agent_harness.toolkits.memory._manager.host import MemoryManagerHost
from myrm_agent_harness.toolkits.memory._manager.shared import (
    AnyMemory,
    MemorySearchResult,
    MemoryType,
    load_context,
)

# Fire-and-forget maintenance tasks keep a strong reference here so they are
# not garbage-collected by the event loop before completion.
_pending_tasks: set[asyncio.Task[object]] = set()


class MemoryManagerRetrievalWriteMixin(MemoryManagerHost):
    @staticmethod
    def _record_ephemeral_delta_for_memory(memory: AnyMemory) -> None:
        from myrm_agent_harness.toolkits.memory.ephemeral_delta.notify import (
            record_ephemeral_memory_delta,
        )

        content = getattr(memory, "content", None)
        if not isinstance(content, str) or not content.strip():
            return
        memory_id = getattr(memory, "id", None)
        key = f"memory:{memory_id}" if isinstance(memory_id, str) and memory_id.strip() else "memory:latest"
        record_ephemeral_memory_delta(key=key, value=content)

    async def store(
        self,
        memory: AnyMemory,
        *,
        _bypass_approval: bool = False,
        _force_pending: bool = False,
        _scope_prevalidated: bool = False,
    ) -> AnyMemory:
        result = await self._writer.store(
            memory,
            bypass_approval=_bypass_approval,
            force_pending=_force_pending,
            scope_prevalidated=_scope_prevalidated,
        )
        self._stores_since_consolidation += 1
        trigger = self._config.consolidation.message_count_trigger
        if trigger > 0 and self._stores_since_consolidation >= trigger:
            self._stores_since_consolidation = 0
            self._maybe_consolidate()
        await self._submit_preference_candidate(result)
        return result

    async def store_batch(
        self,
        memories: Sequence[AnyMemory],
        *,
        _bypass_approval: bool = False,
        _force_pending: bool = False,
        _skip_dedup: bool = False,
    ) -> list[AnyMemory]:
        result = await self._writer.store_batch(
            memories,
            bypass_approval=_bypass_approval,
            force_pending=_force_pending,
            skip_dedup=_skip_dedup,
        )
        self._stores_since_consolidation += len(memories)
        trigger = self._config.consolidation.message_count_trigger
        if trigger > 0 and self._stores_since_consolidation >= trigger:
            self._stores_since_consolidation = 0
            self._maybe_consolidate()
        for mem in result:
            await self._submit_preference_candidate(mem)
        return result

    async def search(
        self,
        query: str,
        *,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
        use_rrf: bool = True,
        include_raw: bool = False,
        since: datetime | None = None,
        until: datetime | None = None,
        track_access: bool = True,
        dynamic_signal_weights: dict[str, float] | None = None,
    ) -> list[MemorySearchResult]:
        """Search the enabled memory types.

        ``track_access`` records each hit as used (use count and last-use time), and a memory used
        within the last week is protected from forgetting. Pass ``False`` for a lookup that is not
        a recall: deduplication, diagnostics, existence checks.
        """
        session_chat_id = self._active_session.chat_id if self._active_session else None
        results = await self._search_service.search(
            query,
            memory_types=memory_types or self.get_enabled_types(),
            memory_types_unspecified=memory_types is None,
            limit=limit,
            use_rrf=use_rrf,
            include_raw=include_raw,
            since=since,
            until=until,
            current_chat_id=session_chat_id,
            dynamic_signal_weights=dynamic_signal_weights,
        )
        if track_access and results and self._vector:
            from myrm_agent_harness.toolkits.memory._internal.maintenance import (
                bump_access_counts,
            )

            task = asyncio.create_task(
                bump_access_counts(results, self._vector, self._config, self._relational),
                name="bump_access_counts",
            )
            _pending_tasks.add(task)
            task.add_done_callback(_pending_tasks.discard)
        return results

    async def get_context(
        self,
        *,
        include_profile: bool = True,
        include_rules: bool = True,
        include_agent_instructions: bool = True,
    ) -> dict[str, object]:
        if not self.has_relational:
            return {
                "global_profile": {},
                "peer_profile": {},
                "rules": [],
                "agent_instructions": [],
            }
        assert self._relational is not None
        ctx = await load_context(
            self._relational,
            include_profile=include_profile,
            include_rules=include_rules,
            include_agent_instructions=include_agent_instructions,
            namespaces=self._namespaces,
        )

        return ctx
