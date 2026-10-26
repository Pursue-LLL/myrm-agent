"""Service-level coverage for the memory CRUD endpoints in ``crud/list_write.py``.

The WebUI reaches these service functions through the memory router; the unit lane covers
them here so a keyword-mode (embeddings-less) deployment keeps every management path
tested without the e2e lane. A real manager over an embedded Qdrant runs the storage
path; only the operation ledger write is patched out (it needs a request-scoped session).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory

from app.schemas.memory.crud import CreateMemoryRequest, RateMemoryRequest, UpdateMemoryStatusRequest
from app.services.memory.operations.crud.list_write import (
    UndoConsolidationRequest,
    create_memory,
    get_memory_context,
    get_memory_stats,
    get_memory_tags,
    list_memories_paginated,
    rate_memory,
    search_memories,
    undo_consolidation,
    update_memory_status,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def keyword_manager(tmp_path: Path):
    """A real embeddings-less manager: semantic/episodic memories live in the sparse mirror."""
    manager = await create_local_memory_manager(tmp_path / "memory", None)
    try:
        yield manager
    finally:
        await manager.close()


@pytest.fixture(autouse=True)
def _skip_ledger():
    """The ledger write needs a request-scoped DB session this service-level test has not."""
    with patch(
        "app.services.memory.operations.crud.list_write._record_memory_event",
        new=AsyncMock(),
    ):
        yield


async def _store_knowledge(manager, content: str, *, tags: list[str] | None = None) -> SemanticMemory:
    return await manager.store(SemanticMemory(id=str(uuid4()), user_id="sandbox_user", content=content, tags=tags or []))


async def test_search_memories_returns_scored_results(keyword_manager) -> None:
    memory = await _store_knowledge(keyword_manager, "搜索校验：TypeScript strict 模式")

    response = await search_memories(query="TypeScript", memory_types=None, limit=10, session_id=None, manager=keyword_manager)

    assert [item.id for item in response.results] == [memory.id]
    assert response.scores == [pytest.approx(response.scores[0])]
    assert response.total == 1


async def test_get_memory_stats_counts_every_type(keyword_manager) -> None:
    await _store_knowledge(keyword_manager, "统计校验：TypeScript")

    stats = await get_memory_stats(manager=keyword_manager)

    assert stats.by_type[MemoryType.SEMANTIC.value] == 1
    assert stats.total_memories >= 1
    assert set(stats.by_type) >= {MemoryType.SEMANTIC.value, MemoryType.EPISODIC.value}


async def test_get_memory_context_returns_a_mapping(keyword_manager) -> None:
    context = await get_memory_context(include_profile=True, include_rules=True, manager=keyword_manager)

    assert isinstance(context, dict)


async def test_get_memory_tags_aggregates_tags(keyword_manager) -> None:
    await _store_knowledge(keyword_manager, "标签校验：TypeScript", tags=["编辑器", "偏好"])

    response = await get_memory_tags(limit=20, manager=keyword_manager)

    assert {item.tag for item in response.tags} >= {"编辑器", "偏好"}
    assert response.total_tagged == 1


async def test_create_memory_profile_branch(keyword_manager) -> None:
    item = await create_memory(
        CreateMemoryRequest(memory_type="profile", content="reply_style: concise", key="reply_style", value="concise"),
        manager=keyword_manager,
    )

    assert "reply_style" in item.content


async def test_create_memory_procedural_branch(keyword_manager) -> None:
    item = await create_memory(
        CreateMemoryRequest(
            memory_type="procedural",
            content="提交前运行 lint",
            trigger="提交代码前",
            action="运行 lint",
        ),
        manager=keyword_manager,
    )

    assert item.content


async def test_update_memory_status_archives_and_rejects_unknown(keyword_manager) -> None:
    memory = await _store_knowledge(keyword_manager, "状态校验：TypeScript")

    archived = await update_memory_status(memory.id, UpdateMemoryStatusRequest(status="archived"), manager=keyword_manager)
    assert archived.id == memory.id

    with pytest.raises(HTTPException) as excinfo:
        await update_memory_status(memory.id, UpdateMemoryStatusRequest(status="bogus"), manager=keyword_manager)
    assert excinfo.value.status_code == 400


async def test_undo_consolidation_reports_nothing_to_restore(keyword_manager) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await undo_consolidation(UndoConsolidationRequest(subsumed_ids=["missing-id"]), manager=keyword_manager)

    assert excinfo.value.status_code == 400


async def test_list_memories_paginated_tolerates_a_listing_failure(keyword_manager) -> None:
    await _store_knowledge(keyword_manager, "容错校验：TypeScript")
    with patch.object(keyword_manager, "list_memories", new=AsyncMock(side_effect=RuntimeError("backend down"))):
        response = await list_memories_paginated(
            type=None,
            search=None,
            tag=None,
            sort_by="created_at",
            sort_order="desc",
            page=1,
            page_size=20,
            manager=keyword_manager,
        )

    assert response.items == []
    assert response.pagination.total == 1


async def test_search_memories_paginated_filters_by_tag(keyword_manager) -> None:
    await _store_knowledge(keyword_manager, "标签搜索校验：TypeScript strict", tags=["编辑器"])
    await _store_knowledge(keyword_manager, "标签搜索校验：TypeScript strict", tags=["其他"])

    response = await list_memories_paginated(
        type=None,
        search="TypeScript",
        tag="编辑器",
        sort_by="created_at",
        sort_order="desc",
        page=1,
        page_size=20,
        manager=keyword_manager,
    )

    assert [item.tags for item in response.items] == [["编辑器"]]


async def _search_page(manager, *, page: int, page_size: int):
    return await list_memories_paginated(
        type=None,
        search="typescript",
        tag=None,
        sort_by="created_at",
        sort_order="desc",
        page=page,
        page_size=page_size,
        manager=manager,
    )


async def test_search_pagination_pages_through_one_ranked_window(keyword_manager) -> None:
    """Each page is a slice of the same ranking and has_next follows the window, not the page."""
    for index in range(45):
        await _store_knowledge(keyword_manager, f"typescript pagination note topic{index} detail{index}")

    pages = [await _search_page(keyword_manager, page=page, page_size=20) for page in (1, 2, 3)]
    whole = await _search_page(keyword_manager, page=1, page_size=100)

    assert [len(page.items) for page in pages] == [20, 20, 5]
    assert [page.pagination.has_next for page in pages] == [True, True, False]
    assert {page.pagination.total for page in pages} == {45}
    assert [item.id for page in pages for item in page.items] == [item.id for item in whole.items]


async def test_search_pagination_stops_at_the_window(keyword_manager) -> None:
    for index in range(60):
        await _store_knowledge(keyword_manager, f"typescript window note topic{index} detail{index}")

    last = await _search_page(keyword_manager, page=3, page_size=20)

    assert last.pagination.total == 50
    assert len(last.items) == 10
    assert last.pagination.has_next is False


async def test_search_pagination_does_not_reinforce_what_it_shows(keyword_manager) -> None:
    """Browsing the Memory page is not recall: it must not bump access counts."""
    await _store_knowledge(keyword_manager, "typescript browsing note")

    with patch("myrm_agent_harness.toolkits.memory._internal.maintenance.bump_access_counts", new=AsyncMock()) as bump:
        response = await _search_page(keyword_manager, page=1, page_size=20)
        await asyncio.sleep(0)

    assert len(response.items) == 1
    bump.assert_not_called()


async def test_rate_memory_updates_and_reports_missing(keyword_manager) -> None:
    memory = await _store_knowledge(keyword_manager, "评分校验：TypeScript")

    response = await rate_memory(memory.id, RateMemoryRequest(score=5), manager=keyword_manager)
    assert response.success is True
    assert response.memory_id == memory.id

    with pytest.raises(HTTPException) as excinfo:
        await rate_memory("missing-id", RateMemoryRequest(score=5), manager=keyword_manager)
    assert excinfo.value.status_code == 404


async def test_create_memory_rejects_disabled_types(keyword_manager) -> None:
    """The manual-create gates follow the manager's enabled types, not dense capability."""
    enabled = frozenset({MemoryType.PROFILE})
    with patch.object(keyword_manager, "get_enabled_types", return_value=enabled):
        with pytest.raises(HTTPException) as semantic:
            await create_memory(CreateMemoryRequest(memory_type="semantic", content="TypeScript"), manager=keyword_manager)
        with pytest.raises(HTTPException) as episodic:
            await create_memory(CreateMemoryRequest(memory_type="episodic", content="TypeScript"), manager=keyword_manager)

    assert semantic.value.status_code == 400
    assert episodic.value.status_code == 400


async def test_create_memory_reports_backend_failures(keyword_manager) -> None:
    from myrm_agent_harness.toolkits.memory import MemoryError as HarnessMemoryError

    with patch.object(keyword_manager, "add_knowledge", new=AsyncMock(side_effect=HarnessMemoryError("no vector backend"))):
        with pytest.raises(HTTPException) as semantic:
            await create_memory(CreateMemoryRequest(memory_type="semantic", content="TypeScript"), manager=keyword_manager)
    with patch.object(keyword_manager, "add_event", new=AsyncMock(side_effect=HarnessMemoryError("no vector backend"))):
        with pytest.raises(HTTPException) as episodic:
            await create_memory(CreateMemoryRequest(memory_type="episodic", content="TypeScript"), manager=keyword_manager)

    assert semantic.value.status_code == 400
    assert episodic.value.status_code == 400


async def test_create_memory_procedural_requires_trigger_and_relational(keyword_manager) -> None:
    with pytest.raises(HTTPException) as missing_trigger:
        await create_memory(
            CreateMemoryRequest(memory_type="procedural", content="提交前运行 lint", action="运行 lint"),
            manager=keyword_manager,
        )

    with patch.object(type(keyword_manager), "has_relational", property(lambda self: False)):
        with pytest.raises(HTTPException) as no_relational:
            await create_memory(
                CreateMemoryRequest(
                    memory_type="procedural",
                    content="提交前运行 lint",
                    trigger="提交代码前",
                    action="运行 lint",
                ),
                manager=keyword_manager,
            )

    assert missing_trigger.value.status_code == 400
    assert no_relational.value.status_code == 400


async def test_create_memory_rejects_unknown_type(keyword_manager) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await create_memory(CreateMemoryRequest(memory_type="unknown", content="TypeScript"), manager=keyword_manager)

    assert excinfo.value.status_code == 400


async def test_search_memories_filters_types_and_applies_session_weights(keyword_manager) -> None:
    memory = await _store_knowledge(keyword_manager, "搜索校验：TypeScript strict")

    response = await search_memories(
        query="TypeScript",
        memory_types="semantic,episodic",
        limit=10,
        session_id="session-1",
        manager=keyword_manager,
    )

    assert [item.id for item in response.results] == [memory.id]


async def test_get_memory_stats_tolerates_a_counting_failure(keyword_manager) -> None:
    await _store_knowledge(keyword_manager, "统计容错校验：TypeScript")
    original = keyword_manager.count_memories

    async def flaky_count(mem_type, **kwargs):
        if mem_type == MemoryType.EPISODIC:
            raise RuntimeError("backend down")
        return await original(mem_type, **kwargs)

    with patch.object(keyword_manager, "count_memories", new=AsyncMock(side_effect=flaky_count)):
        stats = await get_memory_stats(manager=keyword_manager)

    assert stats.by_type[MemoryType.EPISODIC.value] == 0
    assert stats.by_type[MemoryType.SEMANTIC.value] == 1


async def test_get_memory_context_falls_back_for_non_mapping_context(keyword_manager) -> None:
    with patch.object(keyword_manager, "get_context", new=AsyncMock(return_value="raw-context")):
        context = await get_memory_context(include_profile=True, include_rules=True, manager=keyword_manager)

    assert context == {"value": "raw-context"}


async def test_undo_consolidation_restores_a_subsumed_memory(keyword_manager) -> None:
    memory = await keyword_manager.store(
        SemanticMemory(
            id=str(uuid4()),
            user_id="sandbox_user",
            content="被吸收校验：TypeScript",
            metadata={"subsumed": True},
        )
    )

    response = await undo_consolidation(UndoConsolidationRequest(subsumed_ids=[memory.id]), manager=keyword_manager)

    assert "1" in response["message"]


async def test_update_memory_status_reports_missing_memory(keyword_manager) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await update_memory_status("missing-id", UpdateMemoryStatusRequest(status="archived"), manager=keyword_manager)

    assert excinfo.value.status_code == 404


async def test_get_memory_tags_tolerates_a_read_failure(keyword_manager) -> None:
    with patch.object(keyword_manager, "list_memories", new=AsyncMock(side_effect=RuntimeError("backend down"))):
        response = await get_memory_tags(limit=20, manager=keyword_manager)

    assert response.tags == []
    assert response.total_tagged == 0
