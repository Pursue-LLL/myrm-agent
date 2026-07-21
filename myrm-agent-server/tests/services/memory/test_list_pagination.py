"""Tests for list_memories_paginated true pagination and get_memory_tags batch scrolling."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.memory.crud import MemoryItem, MemoryListPaginatedResponse
from app.services.memory.operations.crud.list_write import (
    TagStatsResponse,
    get_memory_tags,
    list_memories_paginated,
)


def _make_semantic(content: str, importance: float = 0.5, created_at: datetime | None = None, tags: list[str] | None = None):
    from myrm_agent_harness.toolkits.memory.types import SemanticMemory

    ts = created_at or datetime.now(UTC)
    return SemanticMemory(content=content, importance=importance, created_at=ts, updated_at=ts, tags=tags or [])


def _mock_manager():
    m = AsyncMock()
    m.list_memories = AsyncMock(return_value=[])
    m.count_memories = AsyncMock(return_value=0)
    m.search = AsyncMock(return_value=[])
    m.has_vector = True
    return m


class TestListMemoriesPaginatedSingleType:
    @pytest.mark.asyncio
    async def test_passes_correct_limit_and_offset(self):
        manager = _mock_manager()
        manager.count_memories.return_value = 50
        manager.list_memories.return_value = []

        result = await list_memories_paginated(
            type="semantic", search=None, tag=None, sort_by="created_at",
            sort_order="desc", page=3, page_size=10, manager=manager,
        )

        manager.list_memories.assert_called_once()
        call_kwargs = manager.list_memories.call_args[1]
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 20
        assert result.pagination.page == 3
        assert result.pagination.total == 50
        assert result.pagination.total_pages == 5

    @pytest.mark.asyncio
    async def test_passes_sort_and_tag(self):
        manager = _mock_manager()
        manager.count_memories.return_value = 0

        await list_memories_paginated(
            type="semantic", search=None, tag="python", sort_by="importance",
            sort_order="asc", page=1, page_size=20, manager=manager,
        )

        call_kwargs = manager.list_memories.call_args[1]
        assert call_kwargs["sort_by"] == "importance"
        assert call_kwargs["sort_order"] == "asc"
        assert call_kwargs["tag_filter"] == "python"


class TestListMemoriesPaginatedMultiType:
    @pytest.mark.asyncio
    async def test_multi_type_fetches_offset_plus_page_size(self):
        manager = _mock_manager()
        manager.count_memories.return_value = 10
        manager.list_memories.return_value = []

        await list_memories_paginated(
            type=None, search=None, tag=None, sort_by="created_at",
            sort_order="desc", page=2, page_size=5, manager=manager,
        )

        for call in manager.list_memories.call_args_list:
            assert call[1]["offset"] == 0
            assert call[1]["limit"] == 10  # offset((2-1)*5=5) + page_size(5)


class TestListMemoriesPaginatedSearch:
    @pytest.mark.asyncio
    async def test_delegates_to_search_when_search_provided(self):
        manager = _mock_manager()
        manager.search.return_value = []

        result = await list_memories_paginated(
            type=None, search="hello world", tag=None, sort_by="created_at",
            sort_order="desc", page=1, page_size=20, manager=manager,
        )

        manager.search.assert_called_once()
        manager.list_memories.assert_not_called()


class TestGetMemoryTagsBatchScrolling:
    @pytest.mark.asyncio
    async def test_batch_scrolls_all_memories(self):
        manager = _mock_manager()

        batch1 = [_make_semantic(f"mem{i}", tags=["python"]) for i in range(200)]
        batch2 = [_make_semantic(f"mem{i}", tags=["ai"]) for i in range(50)]

        call_count = 0

        async def _list_side_effect(mem_type, *, limit, offset, **kwargs):
            nonlocal call_count
            call_count += 1
            if mem_type.value == "semantic":
                if offset == 0:
                    return batch1
                elif offset == 200:
                    return batch2
            return []

        manager.list_memories = AsyncMock(side_effect=_list_side_effect)

        result = await get_memory_tags(limit=10, manager=manager)
        assert isinstance(result, TagStatsResponse)
        assert call_count >= 3

    @pytest.mark.asyncio
    async def test_handles_empty_tags(self):
        manager = _mock_manager()
        manager.list_memories.return_value = []
        result = await get_memory_tags(limit=10, manager=manager)
        assert result.total_tagged == 0
        assert result.tags == []
