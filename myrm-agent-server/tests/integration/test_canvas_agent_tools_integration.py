"""Integration tests for canvas agent tools — full chain, no mock.

Covers: create_canvas_tools → operations → filesystem → SSE notification.
Uses real tmp_path I/O, no mock on key paths.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.services.canvas._events import notify_canvas_change, sse_events
from app.services.canvas.canvas_agent_tools import create_canvas_tools

VALID_CANVAS_ID = "12345678-1234-1234-1234-123456789abc"


@pytest.fixture(autouse=True)
def _isolate_canvas_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.canvas._paths.CANVAS_DATA_DIR", tmp_path)


@pytest.fixture(autouse=True)
def _clean_sse() -> None:
    sse_events.clear()
    yield  # type: ignore[misc]
    sse_events.clear()


class TestCanvasAgentToolsIntegration:
    """Full-chain integration: tools → operations → filesystem → SSE."""

    @pytest.mark.asyncio
    async def test_insert_then_get_state(self) -> None:
        """Insert via tool, then verify get_state returns the shape."""
        tools = create_canvas_tools(VALID_CANVAS_ID)
        insert_tool = next(t for t in tools if t.name == "canvas_insert_element")
        get_state_tool = next(t for t in tools if t.name == "canvas_get_state")

        result = await insert_tool.ainvoke(
            {"shape_type": "text", "x": 50.0, "y": 100.0, "props": {"text": "integration test"}}
        )
        insert_data = json.loads(result)
        assert insert_data["status"] == "ok"
        shape_id = insert_data["inserted_shape"]["id"]

        state_result = await get_state_tool.ainvoke({})
        state_data = json.loads(state_result)
        assert state_data["status"] == "ok"
        assert state_data["shape_count"] == 1
        found = [s for s in state_data["shapes"] if s["id"] == shape_id]
        assert len(found) == 1
        assert found[0]["props"]["text"] == "integration test"

    @pytest.mark.asyncio
    async def test_insert_triggers_sse_event(self) -> None:
        """Verify insert_element triggers SSE notification for the canvas."""
        evt = asyncio.Event()
        sse_events[VALID_CANVAS_ID] = {evt}

        tools = create_canvas_tools(VALID_CANVAS_ID)
        insert_tool = next(t for t in tools if t.name == "canvas_insert_element")

        await insert_tool.ainvoke({"shape_type": "note", "x": 0, "y": 0, "props": {"text": "sse test"}})
        assert evt.is_set(), "SSE event must be triggered after insert"

    @pytest.mark.asyncio
    async def test_get_state_empty_canvas(self) -> None:
        """get_state on a fresh canvas returns empty status."""
        tools = create_canvas_tools(VALID_CANVAS_ID)
        get_state = next(t for t in tools if t.name == "canvas_get_state")

        result = await get_state.ainvoke({})
        data = json.loads(result)
        assert data["status"] == "empty"

    @pytest.mark.asyncio
    async def test_get_selection_empty(self) -> None:
        """get_selection with no selection file returns empty."""
        tools = create_canvas_tools(VALID_CANVAS_ID)
        get_sel = next(t for t in tools if t.name == "canvas_get_selection")

        result = await get_sel.ainvoke({})
        data = json.loads(result)
        assert data["status"] == "empty"

    @pytest.mark.asyncio
    async def test_get_selection_with_data(self, tmp_path: Path) -> None:
        """Write selection.json manually, verify get_selection reads it."""
        canvas_dir = tmp_path / VALID_CANVAS_ID
        canvas_dir.mkdir(parents=True, exist_ok=True)
        selection_data = {"selectedShapes": [{"id": "shape:sel1", "type": "text"}]}
        (canvas_dir / "selection.json").write_text(json.dumps(selection_data), "utf-8")

        tools = create_canvas_tools(VALID_CANVAS_ID)
        get_sel = next(t for t in tools if t.name == "canvas_get_selection")

        result = await get_sel.ainvoke({})
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["count"] == 1
        assert data["selected_shapes"][0]["id"] == "shape:sel1"

    @pytest.mark.asyncio
    async def test_multiple_inserts_accumulate(self) -> None:
        """Multiple inserts accumulate in the same canvas snapshot."""
        tools = create_canvas_tools(VALID_CANVAS_ID)
        insert_tool = next(t for t in tools if t.name == "canvas_insert_element")
        get_state_tool = next(t for t in tools if t.name == "canvas_get_state")

        for i in range(3):
            await insert_tool.ainvoke(
                {"shape_type": "note", "x": float(i * 100), "y": 0.0, "props": {"text": f"note-{i}"}}
            )

        state_result = await get_state_tool.ainvoke({})
        state_data = json.loads(state_result)
        assert state_data["shape_count"] == 3

    @pytest.mark.asyncio
    async def test_insert_does_not_notify_other_canvas(self) -> None:
        """SSE notification is scoped — inserting into canvas A does not trigger canvas B."""
        other_canvas = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        evt_other = asyncio.Event()
        sse_events[other_canvas] = {evt_other}

        tools = create_canvas_tools(VALID_CANVAS_ID)
        insert_tool = next(t for t in tools if t.name == "canvas_insert_element")

        await insert_tool.ainvoke({"shape_type": "text", "x": 0, "y": 0})
        assert not evt_other.is_set(), "Other canvas SSE should not be triggered"
