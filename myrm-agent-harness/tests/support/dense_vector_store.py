"""In-memory dense vector store that keeps the contract memory writes and walks depend on.

[INPUT]
- myrm_agent_harness.toolkits.vector.base::VectorDocument, FilterDict (POS: stored point and the scroll filter shape)

[OUTPUT]
- DenseVectorStore: ``upsert`` / ``get`` / ``scroll`` over named collections

[POS]
Harness pytest-only store double. A plain ``AsyncMock`` accepts every write and ends every
walk, so it cannot show a batch the real store refuses whole or a walk that stops at the first
page. This double refuses a vectorless document before writing anything (as
``QdrantVectorStore.upsert`` does) and pages ``scroll`` by an opaque cursor that is ``None``
only after the last page.
"""

from __future__ import annotations

from collections.abc import Sequence

from myrm_agent_harness.toolkits.vector.base import FilterDict, VectorDocument


class DenseVectorStore:
    """Collections of points held in insertion order; reads hand out copies, as a remote store does."""

    def __init__(self) -> None:
        self.points: dict[tuple[str, str], VectorDocument] = {}
        self.scroll_calls: list[tuple[str, int, str | None]] = []

    def put(self, collection: str, doc: VectorDocument) -> VectorDocument:
        """Seed a point directly, bypassing the write contract of ``upsert``."""
        self.points[(collection, doc.id)] = doc
        return doc

    def stored(self, collection: str, doc_id: str) -> VectorDocument | None:
        return self.points.get((collection, doc_id))

    async def upsert(self, collection: str, documents: Sequence[VectorDocument]) -> list[str]:
        for doc in documents:
            if doc.vector is None:
                raise ValueError(f"Document {doc.id} is missing vector")
        for doc in documents:
            self.points[(collection, doc.id)] = doc.model_copy(deep=True)
        return [doc.id for doc in documents]

    async def get(self, collection: str, ids: list[str]) -> list[VectorDocument]:
        return [self.points[(collection, i)].model_copy(deep=True) for i in ids if (collection, i) in self.points]

    async def scroll(
        self,
        collection: str,
        limit: int = 100,
        offset: str | None = None,
        filters: FilterDict | None = None,
        order_by: tuple[str, str] | None = None,
    ) -> tuple[list[VectorDocument], str | None]:
        if order_by is not None:
            raise NotImplementedError("sorted scrolling is not modelled by this double")
        self.scroll_calls.append((collection, limit, offset))
        matching = [doc for (name, _), doc in self.points.items() if name == collection and _matches(doc, filters)]
        start = int(offset) if offset else 0
        end = start + limit
        page = [doc.model_copy(deep=True) for doc in matching[start:end]]
        return page, (str(end) if end < len(matching) else None)


def _matches(doc: VectorDocument, filters: FilterDict | None) -> bool:
    for key, expected in (filters or {}).items():
        actual = doc.metadata.get(key)
        if isinstance(expected, dict):
            if set(expected) != {"not"}:
                raise NotImplementedError(f"filter operator on {key!r} is not modelled by this double")
            if actual == expected["not"]:
                return False
        elif isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True
