"""``import_memories`` hands the writer only the memory types it can store.

Claims are compiled, retrieval-only knowledge (``ClaimMemory`` says so) and the writer rejects them:
an exported claim must never reach ``store_batch``, and must not cost the other types in the same
file their import.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from myrm_agent_harness.toolkits.memory._manager.import_export import MemoryManagerImportExportMixin
from myrm_agent_harness.toolkits.memory.types import AnyMemory, ClaimMemory, SemanticMemory


class _Importer(MemoryManagerImportExportMixin):
    """The import mixin with a recording ``store_batch`` in place of the real writer."""

    def __init__(self) -> None:
        self._deduplicator = None
        self._relational = None
        self.batches: list[list[AnyMemory]] = []

    async def store_batch(
        self,
        memories: Sequence[AnyMemory],
        *,
        _bypass_approval: bool = False,
        _force_pending: bool = False,
    ) -> list[AnyMemory]:
        self.batches.append(list(memories))
        return list(memories)


def _exported(memory: SemanticMemory | ClaimMemory) -> dict[str, object]:
    return memory.model_dump(mode="json", exclude={"embedding"})


@pytest.mark.asyncio
async def test_storable_types_reach_the_writer_and_claims_do_not() -> None:
    importer = _Importer()
    semantic = SemanticMemory(content="prefers dark mode")
    claim = ClaimMemory(content="c", claim_key="k", title="t", claim_text="the claim")

    counts = await importer.import_memories({"semantic": [_exported(semantic)], "claim": [_exported(claim)]})

    assert counts == {"semantic": 1}
    assert len(importer.batches) == 1
    assert [type(memory) for memory in importer.batches[0]] == [SemanticMemory]
