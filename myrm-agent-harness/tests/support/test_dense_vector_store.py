"""Unit tests for ``tests.support.dense_vector_store``.

[INPUT]
- tests.support.dense_vector_store::DenseVectorStore (POS: pytest-only dense store double with the real store's write refusal and cursor paging)

[OUTPUT]
- test_upsert_refuses_a_batch_holding_a_vectorless_document: nothing is written when one document lacks a vector
- test_get_returns_copies_of_stored_points: callers cannot mutate the store through a read
- test_scroll_walks_every_point_and_ends_with_no_cursor: the cursor is None only after the last page
- test_scroll_of_an_exact_multiple_of_the_page_size_ends_on_the_last_page: no empty trailing page
- test_scroll_applies_the_filter_shapes_the_memory_toolkit_sends: scalar, list and ``not`` filters

[POS]
The memory tests lean on this double to behave like the real store; these cases pin that.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.vector.base import VectorDocument
from tests.support.dense_vector_store import DenseVectorStore


def _doc(doc_id: str, *, vector: list[float] | None = None, **metadata: str | bool) -> VectorDocument:
    return VectorDocument(id=doc_id, content=doc_id, vector=vector, metadata=dict(metadata))


@pytest.mark.asyncio
async def test_upsert_refuses_a_batch_holding_a_vectorless_document() -> None:
    store = DenseVectorStore()

    with pytest.raises(ValueError, match="Document b is missing vector"):
        await store.upsert("c", [_doc("a", vector=[0.1]), _doc("b")])

    assert store.stored("c", "a") is None


@pytest.mark.asyncio
async def test_get_returns_copies_of_stored_points() -> None:
    store = DenseVectorStore()
    await store.upsert("c", [_doc("a", vector=[0.1], tier="x")])

    (read,) = await store.get("c", ["a", "missing"])
    read.metadata["tier"] = "changed"

    stored = store.stored("c", "a")
    assert stored is not None
    assert stored.metadata["tier"] == "x"


@pytest.mark.asyncio
async def test_scroll_walks_every_point_and_ends_with_no_cursor() -> None:
    store = DenseVectorStore()
    await store.upsert("c", [_doc(f"d{i}", vector=[0.1]) for i in range(5)])

    seen: list[str] = []
    cursor: str | None = None
    while True:
        page, cursor = await store.scroll("c", limit=2, offset=cursor)
        seen.extend(doc.id for doc in page)
        if cursor is None:
            break

    assert seen == [f"d{i}" for i in range(5)]
    assert [limit for _, limit, _ in store.scroll_calls] == [2, 2, 2]


@pytest.mark.asyncio
async def test_scroll_of_an_exact_multiple_of_the_page_size_ends_on_the_last_page() -> None:
    store = DenseVectorStore()
    await store.upsert("c", [_doc(f"d{i}", vector=[0.1]) for i in range(4)])

    _, first_cursor = await store.scroll("c", limit=2)
    page, last_cursor = await store.scroll("c", limit=2, offset=first_cursor)

    assert len(page) == 2
    assert last_cursor is None


@pytest.mark.asyncio
async def test_scroll_applies_the_filter_shapes_the_memory_toolkit_sends() -> None:
    store = DenseVectorStore()
    await store.upsert(
        "c",
        [
            _doc("live", vector=[0.1], archived=False, kind="a", ns="one"),
            _doc("old", vector=[0.1], archived=True, kind="a", ns="one"),
            _doc("other", vector=[0.1], archived=False, kind="b", ns="two"),
            _doc("bare", vector=[0.1]),
        ],
    )

    live, _ = await store.scroll("c", filters={"archived": {"not": True}})
    kind_a, _ = await store.scroll("c", filters={"kind": "a"})
    in_ns, _ = await store.scroll("c", filters={"ns": ["two", "three"]})

    assert [d.id for d in live] == ["live", "other", "bare"]
    assert [d.id for d in kind_a] == ["live", "old"]
    assert [d.id for d in in_ns] == ["other"]
