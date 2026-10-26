"""ReadOnlyMemoryView read delegation: each read reaches the parent with the arguments it was given.

Which members are reads and which are denied writes is pinned by test_read_only_view_surface.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from myrm_agent_harness.toolkits.memory.types import MemoryType


def _make_parent_mock() -> MagicMock:
    parent = MagicMock()
    parent.namespaces = ["ns-1"]
    type(parent).has_relational = PropertyMock(return_value=True)
    type(parent).has_vector = PropertyMock(return_value=True)
    type(parent).has_graph = PropertyMock(return_value=False)
    parent.search = AsyncMock(return_value=[])
    parent.get_context = AsyncMock(return_value={"key": "value"})
    parent.get_learned_context = AsyncMock(return_value={"rules": [{"k": "v"}]})
    parent.get_memory = AsyncMock(return_value=None)
    parent.begin_session = MagicMock(return_value="session-ctx")
    parent.end_session = AsyncMock(return_value=[])
    return parent


class TestReadOnlyMemoryViewReadDelegation:
    """Read operations must delegate to parent."""

    def _make_view(self):
        from myrm_agent_harness.toolkits.memory.ephemeral import ReadOnlyMemoryView

        parent = _make_parent_mock()
        return ReadOnlyMemoryView(parent), parent

    @pytest.mark.asyncio
    async def test_search_delegates(self):
        view, parent = self._make_view()
        await view.search("query")
        parent.search.assert_awaited_once_with(
            "query",
            memory_types=None,
            limit=10,
            use_rrf=True,
            include_raw=False,
            since=None,
            until=None,
            track_access=True,
            dynamic_signal_weights=None,
        )

    @pytest.mark.asyncio
    async def test_get_context_delegates(self):
        view, parent = self._make_view()
        result = await view.get_context()
        parent.get_context.assert_awaited_once()
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_learned_context_delegates(self):
        view, parent = self._make_view()
        result = await view.get_learned_context()
        parent.get_learned_context.assert_awaited_once()
        assert "rules" in result

    @pytest.mark.asyncio
    async def test_get_memory_delegates(self):
        view, parent = self._make_view()
        await view.get_memory("mem-1")
        parent.get_memory.assert_awaited_once_with("mem-1")

    def test_begin_session_delegates(self):
        view, parent = self._make_view()
        result = view.begin_session("chat-1")
        parent.begin_session.assert_called_once_with("chat-1")
        assert result == "session-ctx"

    @pytest.mark.asyncio
    async def test_end_session_returns_empty(self):
        view, _parent = self._make_view()
        result = await view.end_session()
        assert result == []

    @pytest.mark.asyncio
    async def test_close_is_noop(self):
        view, _parent = self._make_view()
        await view.close()

    @pytest.mark.asyncio
    async def test_list_pending_returns_empty(self):
        view, _parent = self._make_view()
        result = await view.list_pending()
        assert result == []

    @pytest.mark.asyncio
    async def test_count_pending_returns_zero(self):
        view, _parent = self._make_view()
        result = await view.count_pending()
        assert result == 0

    @pytest.mark.asyncio
    async def test_list_memories_delegates(self):
        view, parent = self._make_view()
        parent.list_memories = AsyncMock(return_value=[])
        result = await view.list_memories(MemoryType.SEMANTIC)
        parent.list_memories.assert_awaited_once()
        assert result == []

    @pytest.mark.asyncio
    async def test_count_memories_delegates(self):
        view, parent = self._make_view()
        parent.count_memories = AsyncMock(return_value=42)
        result = await view.count_memories(MemoryType.SEMANTIC)
        assert result == 42

    @pytest.mark.asyncio
    async def test_export_all_delegates(self):
        view, parent = self._make_view()
        parent.export_all = AsyncMock(return_value={"semantic": []})
        result = await view.export_all()
        assert "semantic" in result

    def test_get_enabled_types_delegates(self):
        view, parent = self._make_view()
        parent.get_enabled_types = MagicMock(return_value=[MemoryType.SEMANTIC])
        result = view.get_enabled_types()
        assert MemoryType.SEMANTIC in result

    @pytest.mark.asyncio
    async def test_compute_health_score_delegates(self):
        view, parent = self._make_view()
        mock_score = MagicMock()
        parent.compute_health_score = AsyncMock(return_value=mock_score)
        result = await view.compute_health_score()
        assert result is mock_score

    def test_properties(self):
        view, _parent = self._make_view()
        assert view.namespaces == ["ns-1"]
        assert view.has_relational is True
        assert view.has_vector is True
        assert view.has_graph is False

    def test_inherited_properties_no_attribute_error(self):
        """All inherited properties must be accessible without AttributeError."""
        view, _ = self._make_view()
        assert view.active_session is None
        assert view.approval_required is False
        assert view.config is not None
        assert view.last_cited_memory_ids == []
        assert view.scope is not None
