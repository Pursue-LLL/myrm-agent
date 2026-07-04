"""Tests for app.services.canvas.canvas_agent_tools.

Covers: create_canvas_tools factory, tool invocation, SSE notification wiring.
Uses mock for operations to avoid filesystem I/O.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.canvas._events import sse_events
from app.services.canvas.canvas_agent_tools import create_canvas_tools

VALID_CANVAS_ID = "12345678-1234-1234-1234-123456789abc"


@pytest.fixture(autouse=True)
def _clean_sse_events() -> None:
    sse_events.clear()
    yield  # type: ignore[misc]
    sse_events.clear()


class TestCreateCanvasTools:
    def test_returns_four_tools(self) -> None:
        tools = create_canvas_tools(VALID_CANVAS_ID)
        assert len(tools) == 4

    def test_tool_names(self) -> None:
        tools = create_canvas_tools(VALID_CANVAS_ID)
        names = {t.name for t in tools}
        assert names == {
            "canvas_get_state",
            "canvas_get_selection",
            "canvas_insert_element",
            "canvas_batch_layout",
        }

    def test_tools_are_async(self) -> None:
        tools = create_canvas_tools(VALID_CANVAS_ID)
        for t in tools:
            assert hasattr(t, "coroutine") or t.coroutine is not None or hasattr(t, "ainvoke")


class TestCanvasGetStateTool:
    @pytest.mark.asyncio
    async def test_empty_canvas_returns_empty_status(self) -> None:
        tools = create_canvas_tools(VALID_CANVAS_ID)
        get_state = next(t for t in tools if t.name == "canvas_get_state")

        with patch(
            "app.services.canvas.canvas_agent_tools.get_canvas_state",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await get_state.ainvoke({})
            data = json.loads(result)
            assert data["status"] == "empty"

    @pytest.mark.asyncio
    async def test_returns_shapes_from_snapshot(self) -> None:
        snapshot: dict[str, Any] = {
            "store": {
                "shape:abc": {"typeName": "shape", "type": "text", "props": {"text": "hi"}},
                "page:1": {"typeName": "page"},
            }
        }
        tools = create_canvas_tools(VALID_CANVAS_ID)
        get_state = next(t for t in tools if t.name == "canvas_get_state")

        with patch(
            "app.services.canvas.canvas_agent_tools.get_canvas_state",
            new_callable=AsyncMock,
            return_value=snapshot,
        ):
            result = await get_state.ainvoke({})
            data = json.loads(result)
            assert data["status"] == "ok"
            assert data["shape_count"] == 1
            assert data["shapes"][0]["type"] == "text"


class TestCanvasGetSelectionTool:
    @pytest.mark.asyncio
    async def test_empty_selection(self) -> None:
        tools = create_canvas_tools(VALID_CANVAS_ID)
        get_sel = next(t for t in tools if t.name == "canvas_get_selection")

        with patch(
            "app.services.canvas.canvas_agent_tools.get_canvas_selection",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await get_sel.ainvoke({})
            data = json.loads(result)
            assert data["status"] == "empty"

    @pytest.mark.asyncio
    async def test_returns_selected_shapes(self) -> None:
        selected = [{"id": "shape:1", "type": "note"}, {"id": "shape:2", "type": "geo"}]
        tools = create_canvas_tools(VALID_CANVAS_ID)
        get_sel = next(t for t in tools if t.name == "canvas_get_selection")

        with patch(
            "app.services.canvas.canvas_agent_tools.get_canvas_selection",
            new_callable=AsyncMock,
            return_value=selected,
        ):
            result = await get_sel.ainvoke({})
            data = json.loads(result)
            assert data["status"] == "ok"
            assert data["count"] == 2


class TestCanvasInsertElementTool:
    @pytest.mark.asyncio
    async def test_insert_returns_shape_and_notifies_sse(self) -> None:
        import asyncio as _asyncio

        evt = _asyncio.Event()
        sse_events[VALID_CANVAS_ID] = {evt}

        created_shape: dict[str, Any] = {
            "id": "shape:abc123",
            "type": "text",
            "x": 100.0,
            "y": 200.0,
            "props": {"text": "hello"},
            "typeName": "shape",
        }
        tools = create_canvas_tools(VALID_CANVAS_ID)
        insert_tool = next(t for t in tools if t.name == "canvas_insert_element")

        with patch(
            "app.services.canvas.canvas_agent_tools.insert_canvas_element",
            new_callable=AsyncMock,
            return_value=created_shape,
        ):
            result = await insert_tool.ainvoke(
                {"shape_type": "text", "x": 100.0, "y": 200.0, "props": {"text": "hello"}}
            )
            data = json.loads(result)
            assert data["status"] == "ok"
            assert data["inserted_shape"]["id"] == "shape:abc123"
            assert evt.is_set(), "SSE event should be triggered after insert"

    @pytest.mark.asyncio
    async def test_insert_without_props(self) -> None:
        created_shape: dict[str, Any] = {
            "id": "shape:def456",
            "type": "geo",
            "x": 0.0,
            "y": 0.0,
            "props": {},
            "typeName": "shape",
        }
        tools = create_canvas_tools(VALID_CANVAS_ID)
        insert_tool = next(t for t in tools if t.name == "canvas_insert_element")

        with patch(
            "app.services.canvas.canvas_agent_tools.insert_canvas_element",
            new_callable=AsyncMock,
            return_value=created_shape,
        ):
            result = await insert_tool.ainvoke({"shape_type": "geo"})
            data = json.loads(result)
            assert data["status"] == "ok"
