"""Kanban board settings hot-swap: update_board must refresh the live dispatcher.

Regression for runtime config changes: editing ``max_concurrent_tasks`` (or other
board settings) via the GUI/API previously left the running dispatcher on its
startup snapshot, so the frontend's concurrency badge disagreed with real
scheduling. ``update_board`` now calls ``dispatcher.refresh_board`` whenever
settings change, while name/description-only edits must not disturb it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.kanban.types import BoardSettings, KanbanBoard

from app.services.kanban.board_ops import update_board


class _FakeDispatcher:
    def __init__(self) -> None:
        self.refreshed: list[KanbanBoard] = []

    def refresh_board(self, board: KanbanBoard) -> None:
        self.refreshed.append(board)


def _make_board(max_concurrent: int = 1) -> KanbanBoard:
    return KanbanBoard(
        board_id="b1",
        name="Board",
        settings=BoardSettings(max_concurrent_tasks=max_concurrent),
    )


@pytest.mark.asyncio
async def test_update_board_settings_refreshes_live_dispatcher() -> None:
    store = AsyncMock()
    store.get_board.return_value = _make_board(max_concurrent=1)
    saved = _make_board(max_concurrent=2)
    store.save_board.return_value = saved

    dispatchers = {"b1": _FakeDispatcher()}
    result = await update_board(
        store,
        "b1",
        settings=BoardSettings(max_concurrent_tasks=2),
        dispatchers=dispatchers,
    )

    assert result is saved
    assert dispatchers["b1"].refreshed == [saved]
    store.save_board.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_board_name_only_does_not_refresh_dispatcher() -> None:
    store = AsyncMock()
    board = _make_board()
    store.get_board.return_value = board
    store.save_board.return_value = board

    dispatchers = {"b1": _FakeDispatcher()}
    await update_board(store, "b1", name="Renamed", dispatchers=dispatchers)

    assert dispatchers["b1"].refreshed == []


@pytest.mark.asyncio
async def test_update_board_settings_without_dispatcher_is_safe() -> None:
    store = AsyncMock()
    store.get_board.return_value = _make_board(max_concurrent=1)
    saved = _make_board(max_concurrent=2)
    store.save_board.return_value = saved

    result = await update_board(
        store,
        "b1",
        settings=BoardSettings(max_concurrent_tasks=2),
        dispatchers=None,
    )

    assert result is saved
