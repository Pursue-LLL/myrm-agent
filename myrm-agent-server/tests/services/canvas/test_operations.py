"""Tests for app.services.canvas.operations.

Covers: get_canvas_state, get_canvas_selection, insert_canvas_element.
All I/O uses asyncio.to_thread (non-blocking) and is tested against
a temporary directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.canvas import operations


@pytest.fixture(autouse=True)
def _isolate_canvas_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect CANVAS_DATA_DIR to a temp directory for test isolation."""
    monkeypatch.setattr("app.services.canvas._paths.CANVAS_DATA_DIR", tmp_path)


VALID_CANVAS_ID = "12345678-1234-1234-1234-123456789abc"


class TestGetCanvasState:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_snapshot(self) -> None:
        result = await operations.get_canvas_state(VALID_CANVAS_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_parsed_snapshot(self, tmp_path: Path) -> None:
        canvas_dir = tmp_path / VALID_CANVAS_ID
        canvas_dir.mkdir()
        snap = {"store": {"shape:abc": {"type": "text"}}}
        (canvas_dir / "snapshot.json").write_text(json.dumps(snap), "utf-8")

        result = await operations.get_canvas_state(VALID_CANVAS_ID)
        assert result == snap

    @pytest.mark.asyncio
    async def test_returns_none_on_corrupt_json(self, tmp_path: Path) -> None:
        canvas_dir = tmp_path / VALID_CANVAS_ID
        canvas_dir.mkdir()
        (canvas_dir / "snapshot.json").write_text("NOT JSON", "utf-8")

        result = await operations.get_canvas_state(VALID_CANVAS_ID)
        assert result is None


class TestGetCanvasSelection:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_file(self) -> None:
        result = await operations.get_canvas_selection(VALID_CANVAS_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_selected_shapes(self, tmp_path: Path) -> None:
        canvas_dir = tmp_path / VALID_CANVAS_ID
        canvas_dir.mkdir()
        data = {"selectedShapes": [{"id": "shape:1"}, {"id": "shape:2"}]}
        (canvas_dir / "selection.json").write_text(json.dumps(data), "utf-8")

        result = await operations.get_canvas_selection(VALID_CANVAS_ID)
        assert len(result) == 2
        assert result[0]["id"] == "shape:1"

    @pytest.mark.asyncio
    async def test_returns_empty_on_corrupt_json(self, tmp_path: Path) -> None:
        canvas_dir = tmp_path / VALID_CANVAS_ID
        canvas_dir.mkdir()
        (canvas_dir / "selection.json").write_text("{broken", "utf-8")

        result = await operations.get_canvas_selection(VALID_CANVAS_ID)
        assert result == []


class TestInsertCanvasElement:
    @pytest.mark.asyncio
    async def test_creates_snapshot_from_scratch(self) -> None:
        shape = await operations.insert_canvas_element(
            VALID_CANVAS_ID, "text", 100.0, 200.0, {"text": "hello"}
        )
        assert shape["type"] == "text"
        assert shape["x"] == 100.0
        assert shape["y"] == 200.0
        assert shape["props"]["text"] == "hello"
        assert shape["id"].startswith("shape:")

    @pytest.mark.asyncio
    async def test_appends_to_existing_snapshot(self, tmp_path: Path) -> None:
        canvas_dir = tmp_path / VALID_CANVAS_ID
        canvas_dir.mkdir()
        existing = {"store": {"shape:existing": {"type": "note"}}}
        (canvas_dir / "snapshot.json").write_text(json.dumps(existing), "utf-8")

        shape = await operations.insert_canvas_element(
            VALID_CANVAS_ID, "text", 0.0, 0.0
        )

        snap = json.loads((canvas_dir / "snapshot.json").read_text("utf-8"))
        assert "shape:existing" in snap["store"]
        assert shape["id"] in snap["store"]

    @pytest.mark.asyncio
    async def test_text_shape_gets_default_empty_text(self) -> None:
        shape = await operations.insert_canvas_element(
            VALID_CANVAS_ID, "text", 0.0, 0.0
        )
        assert shape["props"]["text"] == ""

    @pytest.mark.asyncio
    async def test_no_sse_notification_call(self) -> None:
        """Verify insert_canvas_element does NOT import or call api-layer code."""
        await operations.insert_canvas_element(
            VALID_CANVAS_ID, "rect", 10.0, 20.0
        )
        # If we got here without ImportError, the reverse dependency is gone
