"""Tests for batch_insert_canvas_elements in app.services.canvas.operations.

Covers: batch insert shapes, batch insert arrows, edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.canvas import operations


@pytest.fixture(autouse=True)
def _isolate_canvas_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.canvas._paths.CANVAS_DATA_DIR", tmp_path)


VALID_CANVAS_ID = "12345678-1234-1234-1234-123456789abc"


class TestBatchInsertShapes:
    @pytest.mark.asyncio
    async def test_insert_multiple_shapes(self, tmp_path: Path) -> None:
        shapes = [
            {"id": "a", "type": "note", "x": 0, "y": 0, "props": {"text": "A"}},
            {"id": "b", "type": "note", "x": 300, "y": 0, "props": {"text": "B"}},
        ]
        result = await operations.batch_insert_canvas_elements(VALID_CANVAS_ID, shapes)
        assert len(result["inserted_shapes"]) == 2
        assert len(result["inserted_arrows"]) == 0

        snap_path = tmp_path / VALID_CANVAS_ID / "snapshot.json"
        assert snap_path.exists()
        snapshot = json.loads(snap_path.read_text())
        assert len(snapshot["store"]) == 2

    @pytest.mark.asyncio
    async def test_empty_shapes(self) -> None:
        result = await operations.batch_insert_canvas_elements(VALID_CANVAS_ID, [])
        assert result["inserted_shapes"] == []
        assert result["inserted_arrows"] == []

    @pytest.mark.asyncio
    async def test_appends_to_existing_snapshot(self, tmp_path: Path) -> None:
        canvas_dir = tmp_path / VALID_CANVAS_ID
        canvas_dir.mkdir(parents=True)
        existing = {"store": {"shape:existing": {"id": "shape:existing", "type": "note"}}}
        (canvas_dir / "snapshot.json").write_text(json.dumps(existing))

        shapes = [{"id": "new", "type": "note", "x": 0, "y": 0, "props": {}}]
        await operations.batch_insert_canvas_elements(VALID_CANVAS_ID, shapes)

        snapshot = json.loads((canvas_dir / "snapshot.json").read_text())
        assert "shape:existing" in snapshot["store"]
        assert len(snapshot["store"]) == 2


class TestBatchInsertArrows:
    @pytest.mark.asyncio
    async def test_arrows_use_coordinate_endpoints(self) -> None:
        shapes = [
            {"id": "a", "type": "note", "x": 0, "y": 0, "props": {"text": "A"}},
            {"id": "b", "type": "note", "x": 320, "y": 0, "props": {"text": "B"}},
        ]
        arrows = [{"from_id": "a", "to_id": "b", "label": "depends"}]
        result = await operations.batch_insert_canvas_elements(
            VALID_CANVAS_ID, shapes, arrows
        )
        assert len(result["inserted_arrows"]) == 1
        arrow = result["inserted_arrows"][0]
        assert arrow["type"] == "arrow"
        assert "x" in arrow["props"]["start"]
        assert "x" in arrow["props"]["end"]
        assert arrow["props"]["text"] == "depends"

    @pytest.mark.asyncio
    async def test_arrow_skips_missing_node(self) -> None:
        shapes = [{"id": "a", "type": "note", "x": 0, "y": 0, "props": {}}]
        arrows = [{"from_id": "a", "to_id": "nonexistent"}]
        result = await operations.batch_insert_canvas_elements(
            VALID_CANVAS_ID, shapes, arrows
        )
        assert len(result["inserted_arrows"]) == 0

    @pytest.mark.asyncio
    async def test_multiple_arrows(self) -> None:
        shapes = [
            {"id": "a", "type": "note", "x": 0, "y": 0, "props": {}},
            {"id": "b", "type": "note", "x": 300, "y": 0, "props": {}},
            {"id": "c", "type": "note", "x": 150, "y": 200, "props": {}},
        ]
        arrows = [
            {"from_id": "a", "to_id": "b"},
            {"from_id": "a", "to_id": "c"},
            {"from_id": "b", "to_id": "c"},
        ]
        result = await operations.batch_insert_canvas_elements(
            VALID_CANVAS_ID, shapes, arrows
        )
        assert len(result["inserted_arrows"]) == 3


class TestBatchInsertEvents:
    @pytest.mark.asyncio
    async def test_hint_queue(self) -> None:
        from app.services.canvas._events import (
            consume_hint,
            notify_batch_layout_done,
        )

        notify_batch_layout_done(VALID_CANVAS_ID)
        hint = consume_hint(VALID_CANVAS_ID)
        assert hint == "batch-layout-done"
        assert consume_hint(VALID_CANVAS_ID) is None

    @pytest.mark.asyncio
    async def test_hint_queue_bounded(self) -> None:
        from app.services.canvas._events import consume_hint, notify_batch_layout_done

        for _ in range(20):
            notify_batch_layout_done(VALID_CANVAS_ID)
        count = 0
        while consume_hint(VALID_CANVAS_ID):
            count += 1
        assert count == 16
