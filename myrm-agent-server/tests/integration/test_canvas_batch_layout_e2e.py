"""Integration test: canvas_batch_layout full pipeline.

Tests the entire flow without mocks:
  canvas_batch_layout tool → layout algorithm → batch insert → snapshot write → SSE hint

This is a server-side E2E test — no HTTP, no browser, but exercises all real
modules in sequence exactly as they run in production.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.services.canvas._events import (
    consume_hint,
    notify_batch_layout_done,
    pending_hints,
    sse_events,
)
from app.services.canvas.canvas_agent_tools import create_canvas_tools
from app.services.canvas.operations import batch_insert_canvas_elements, get_canvas_state


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect canvas data and clean SSE state."""
    monkeypatch.setattr("app.services.canvas._paths.CANVAS_DATA_DIR", tmp_path)
    sse_events.clear()
    pending_hints.clear()
    yield  # type: ignore[misc]
    sse_events.clear()
    pending_hints.clear()


CANVAS_ID = "11111111-2222-3333-4444-555555555555"


class TestBatchLayoutE2E:
    """Full pipeline: tool invocation → layout → insert → SSE hint → snapshot on disk."""

    @pytest.mark.asyncio
    async def test_grid_layout_full_pipeline(self, tmp_path: Path) -> None:
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [
                {"id": "concept1", "text": "Machine Learning"},
                {"id": "concept2", "text": "Deep Learning"},
                {"id": "concept3", "text": "Neural Networks"},
            ],
            "layout": "grid",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["layout"] == "grid"
        assert result["nodes_inserted"] == 3
        assert result["arrows_inserted"] == 0

        snapshot_path = tmp_path / CANVAS_ID / "snapshot.json"
        assert snapshot_path.exists()
        snapshot = json.loads(snapshot_path.read_text())
        shapes = [v for v in snapshot["store"].values() if v.get("type") == "note"]
        assert len(shapes) == 3

        hint = consume_hint(CANVAS_ID)
        assert hint == "batch-layout-done"

    @pytest.mark.asyncio
    async def test_tree_layout_with_edges(self, tmp_path: Path) -> None:
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [
                {"id": "root", "text": "AI"},
                {"id": "ml", "text": "ML"},
                {"id": "dl", "text": "DL"},
                {"id": "nlp", "text": "NLP"},
            ],
            "edges": [
                {"from_id": "root", "to_id": "ml"},
                {"from_id": "root", "to_id": "dl"},
                {"from_id": "root", "to_id": "nlp"},
            ],
            "layout": "tree",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["layout"] == "tree"
        assert result["nodes_inserted"] == 4
        assert result["arrows_inserted"] == 3

        snapshot_path = tmp_path / CANVAS_ID / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        arrows = [v for v in snapshot["store"].values() if v.get("type") == "arrow"]
        assert len(arrows) == 3
        for arrow in arrows:
            assert "x" in arrow["props"]["start"]
            assert "x" in arrow["props"]["end"]

    @pytest.mark.asyncio
    async def test_force_layout_network(self, tmp_path: Path) -> None:
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [
                {"id": "a", "text": "Python"},
                {"id": "b", "text": "JavaScript"},
                {"id": "c", "text": "Rust"},
                {"id": "d", "text": "Go"},
                {"id": "e", "text": "TypeScript"},
            ],
            "edges": [
                {"from_id": "a", "to_id": "b"},
                {"from_id": "b", "to_id": "e"},
                {"from_id": "a", "to_id": "c"},
                {"from_id": "c", "to_id": "d"},
            ],
            "layout": "force",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["layout"] == "force"
        assert result["nodes_inserted"] == 5
        assert result["arrows_inserted"] == 4

    @pytest.mark.asyncio
    async def test_empty_nodes_returns_error(self) -> None:
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({"nodes": []})
        result = json.loads(result_json)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_coexists_with_insert_element(self, tmp_path: Path) -> None:
        """batch_layout doesn't interfere with existing single-insert tool."""
        tools = create_canvas_tools(CANVAS_ID)
        insert_tool = next(t for t in tools if t.name == "canvas_insert_element")
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        await insert_tool.ainvoke({"shape_type": "note", "x": 0, "y": 0, "props": {"text": "Pre-existing"}})

        await batch_tool.ainvoke({
            "nodes": [{"id": "new", "text": "New node"}],
            "layout": "grid",
        })

        snapshot_path = tmp_path / CANVAS_ID / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        shapes = [v for v in snapshot["store"].values() if v.get("typeName") == "shape"]
        assert len(shapes) == 2


class TestEdgeCasesE2E:
    """Edge cases: malformed input, boundary conditions, concurrency."""

    @pytest.mark.asyncio
    async def test_invalid_layout_strategy_falls_back_to_grid(self, tmp_path: Path) -> None:
        """Invalid layout name should fallback to grid, not crash."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [{"id": "a", "text": "Node A"}, {"id": "b", "text": "Node B"}],
            "layout": "invalid_strategy_xyz",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["layout"] == "grid"
        assert result["nodes_inserted"] == 2

    @pytest.mark.asyncio
    async def test_edges_with_nonexistent_node_ids_skipped(self, tmp_path: Path) -> None:
        """Arrows referencing nodes not in the batch are gracefully skipped."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [{"id": "a", "text": "Existing"}],
            "edges": [
                {"from_id": "a", "to_id": "nonexistent"},
                {"from_id": "ghost", "to_id": "a"},
            ],
            "layout": "grid",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["nodes_inserted"] == 1
        assert result["arrows_inserted"] == 0

    @pytest.mark.asyncio
    async def test_node_without_id_gets_auto_id(self, tmp_path: Path) -> None:
        """Nodes without explicit 'id' field get auto-generated IDs (n0, n1, ...)."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [
                {"text": "No ID node 1"},
                {"text": "No ID node 2"},
            ],
            "layout": "grid",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["nodes_inserted"] == 2

    @pytest.mark.asyncio
    async def test_duplicate_node_ids_handled(self, tmp_path: Path) -> None:
        """Duplicate logical IDs: last one wins in id_map, but all shapes inserted."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [
                {"id": "dup", "text": "First"},
                {"id": "dup", "text": "Second"},
            ],
            "layout": "grid",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["nodes_inserted"] == 2

    @pytest.mark.asyncio
    async def test_edge_with_malformed_dict_skipped(self, tmp_path: Path) -> None:
        """Edge dicts missing from_id/to_id keys are gracefully filtered."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
            "edges": [
                {"from_id": "a"},
                {"to_id": "b"},
                {},
                {"from_id": "a", "to_id": "b"},
            ],
            "layout": "grid",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["arrows_inserted"] == 1

    @pytest.mark.asyncio
    async def test_large_batch_50_nodes(self, tmp_path: Path) -> None:
        """50 nodes with star topology: verifies performance and correctness at scale."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        nodes = [{"id": f"n{i}", "text": f"Concept {i}"} for i in range(50)]
        edges = [{"from_id": "n0", "to_id": f"n{i}"} for i in range(1, 50)]

        result_json = await batch_tool.ainvoke({
            "nodes": nodes,
            "edges": edges,
            "layout": "force",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["nodes_inserted"] == 50
        assert result["arrows_inserted"] == 49

    @pytest.mark.asyncio
    async def test_unicode_text_preserved(self, tmp_path: Path) -> None:
        """CJK, emoji, special characters are correctly persisted."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [
                {"id": "cn", "text": "人工智能研究"},
                {"id": "jp", "text": "機械学習ノート"},
                {"id": "emoji", "text": "🧠 Brain Map 🗺️"},
            ],
            "layout": "grid",
        })
        result = json.loads(result_json)
        assert result["status"] == "ok"

        snapshot_path = tmp_path / CANVAS_ID / "snapshot.json"
        content = snapshot_path.read_text(encoding="utf-8")
        assert "人工智能研究" in content
        assert "機械学習ノート" in content
        assert "🧠 Brain Map 🗺️" in content

    @pytest.mark.asyncio
    async def test_self_loop_edge_handled(self, tmp_path: Path) -> None:
        """Self-referencing edge (a → a) doesn't crash, produces arrow with zero delta."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [{"id": "self", "text": "Recursive"}],
            "edges": [{"from_id": "self", "to_id": "self"}],
            "layout": "grid",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["arrows_inserted"] == 1

        snapshot_path = tmp_path / CANVAS_ID / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        arrows = [v for v in snapshot["store"].values() if v.get("type") == "arrow"]
        assert len(arrows) == 1
        assert arrows[0]["props"]["end"]["x"] == 0
        assert arrows[0]["props"]["end"]["y"] == 0


class TestSSEIntegrationE2E:
    """SSE event system integration with the batch layout pipeline."""

    @pytest.mark.asyncio
    async def test_sse_event_triggered_by_batch_layout(self) -> None:
        """SSE asyncio.Event is set when batch_layout completes."""
        event = asyncio.Event()
        sse_events.setdefault(CANVAS_ID, set()).add(event)

        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        await batch_tool.ainvoke({
            "nodes": [{"id": "x", "text": "test"}],
            "layout": "grid",
        })

        assert event.is_set()

    @pytest.mark.asyncio
    async def test_multiple_batch_layout_calls_produce_multiple_hints(self) -> None:
        """Each batch_layout call adds one hint to the queue."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        await batch_tool.ainvoke({"nodes": [{"id": "a", "text": "A"}], "layout": "grid"})
        await batch_tool.ainvoke({"nodes": [{"id": "b", "text": "B"}], "layout": "grid"})
        await batch_tool.ainvoke({"nodes": [{"id": "c", "text": "C"}], "layout": "grid"})

        assert consume_hint(CANVAS_ID) == "batch-layout-done"
        assert consume_hint(CANVAS_ID) == "batch-layout-done"
        assert consume_hint(CANVAS_ID) == "batch-layout-done"
        assert consume_hint(CANVAS_ID) is None

    @pytest.mark.asyncio
    async def test_consume_hint_returns_none_for_unknown_canvas(self) -> None:
        """consume_hint on a canvas that never had batch_layout returns None."""
        assert consume_hint("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee") is None

    @pytest.mark.asyncio
    async def test_hint_queue_bounded_at_16(self) -> None:
        """Pending hints queue never exceeds _MAX_PENDING_HINTS (16)."""
        for _ in range(20):
            notify_batch_layout_done(CANVAS_ID)

        queue = pending_hints.get(CANVAS_ID)
        assert queue is not None
        assert len(queue) == 16


class TestSnapshotPersistenceE2E:
    """Snapshot file integrity and state accumulation."""

    @pytest.mark.asyncio
    async def test_sequential_batch_layouts_accumulate_shapes(self, tmp_path: Path) -> None:
        """Multiple batch_layout calls accumulate in the same snapshot."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        await batch_tool.ainvoke({
            "nodes": [{"id": "a", "text": "First batch"}],
            "layout": "grid",
        })
        await batch_tool.ainvoke({
            "nodes": [{"id": "b", "text": "Second batch"}],
            "layout": "grid",
        })

        snapshot_path = tmp_path / CANVAS_ID / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        shapes = [v for v in snapshot["store"].values() if v.get("type") == "note"]
        assert len(shapes) == 2

    @pytest.mark.asyncio
    async def test_snapshot_valid_json_structure(self, tmp_path: Path) -> None:
        """Snapshot always contains a valid {"store": {...}} structure."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        await batch_tool.ainvoke({
            "nodes": [{"id": "v", "text": "Validate"}],
            "layout": "tree",
        })

        snapshot_path = tmp_path / CANVAS_ID / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        assert "store" in snapshot
        assert isinstance(snapshot["store"], dict)

        for shape_id, shape_data in snapshot["store"].items():
            assert "id" in shape_data
            assert "type" in shape_data
            assert "x" in shape_data
            assert "y" in shape_data
            assert "typeName" in shape_data
            assert shape_data["typeName"] == "shape"

    @pytest.mark.asyncio
    async def test_arrow_endpoints_are_coordinate_based(self, tmp_path: Path) -> None:
        """Verify arrows use pure coordinate endpoints, not bindings."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        await batch_tool.ainvoke({
            "nodes": [{"id": "src", "text": "Source"}, {"id": "dst", "text": "Destination"}],
            "edges": [{"from_id": "src", "to_id": "dst"}],
            "layout": "grid",
        })

        snapshot_path = tmp_path / CANVAS_ID / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text())
        arrows = [v for v in snapshot["store"].values() if v.get("type") == "arrow"]
        assert len(arrows) == 1

        arrow = arrows[0]
        start = arrow["props"]["start"]
        end = arrow["props"]["end"]

        assert isinstance(start["x"], (int, float))
        assert isinstance(start["y"], (int, float))
        assert isinstance(end["x"], (int, float))
        assert isinstance(end["y"], (int, float))
        assert start == {"x": 0, "y": 0}
        assert "type" not in start
        assert "boundShapeId" not in start

    @pytest.mark.asyncio
    async def test_get_canvas_state_reads_batch_layout_result(self, tmp_path: Path) -> None:
        """get_canvas_state correctly reads what batch_layout wrote."""
        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")
        get_state_tool = next(t for t in tools if t.name == "canvas_get_state")

        await batch_tool.ainvoke({
            "nodes": [
                {"id": "r1", "text": "Research Topic 1"},
                {"id": "r2", "text": "Research Topic 2"},
            ],
            "edges": [{"from_id": "r1", "to_id": "r2"}],
            "layout": "tree",
        })

        state_json = await get_state_tool.ainvoke({})
        state = json.loads(state_json)

        assert state["status"] == "ok"
        assert state["shape_count"] == 3  # 2 notes + 1 arrow

    @pytest.mark.asyncio
    async def test_corrupted_snapshot_recovered(self, tmp_path: Path) -> None:
        """If existing snapshot is corrupted JSON, batch_layout starts fresh."""
        cdir = tmp_path / CANVAS_ID
        cdir.mkdir(parents=True)
        (cdir / "snapshot.json").write_text("{invalid json!!!", encoding="utf-8")

        tools = create_canvas_tools(CANVAS_ID)
        batch_tool = next(t for t in tools if t.name == "canvas_batch_layout")

        result_json = await batch_tool.ainvoke({
            "nodes": [{"id": "recover", "text": "Recovered"}],
            "layout": "grid",
        })
        result = json.loads(result_json)

        assert result["status"] == "ok"
        assert result["nodes_inserted"] == 1


class TestObsidianCanvasAdapterE2E:
    """Integration: .canvas file extraction into wiki-ready Markdown."""

    def test_full_canvas_file_extraction(self, tmp_path: Path) -> None:
        """Complete .canvas JSON → Markdown extraction with all node types."""
        from app.services.wiki.obsidian_adapter import adapt_obsidian_file

        vault = tmp_path / "vault"
        vault.mkdir()
        raw_dest = tmp_path / "raw"
        raw_dest.mkdir()
        assets = tmp_path / "assets"
        assets.mkdir()

        canvas_data = {
            "nodes": [
                {"id": "1", "type": "text", "text": "# Main Idea\n\nThis is the core concept."},
                {"id": "2", "type": "text", "text": "Supporting evidence here."},
                {"id": "3", "type": "file", "file": "notes/research.md", "label": "Research Notes"},
                {"id": "4", "type": "link", "url": "https://example.com", "label": "Reference"},
                {"id": "5", "type": "group", "label": "Category A"},
                {"id": "6", "type": "file", "file": "data/chart.png"},
            ],
            "edges": [
                {"id": "e1", "fromNode": "1", "toNode": "2"},
            ],
        }
        canvas_file = vault / "mindmap.canvas"
        canvas_file.write_text(json.dumps(canvas_data), encoding="utf-8")

        dest_path, metadata, images = adapt_obsidian_file(canvas_file, vault, raw_dest, assets)

        assert dest_path is not None
        assert dest_path.suffix == ".md"
        assert dest_path.name == "mindmap.md"
        assert metadata.get("source_type") == "canvas"
        assert images == 0

        content = dest_path.read_text(encoding="utf-8")
        assert "# Main Idea" in content
        assert "Supporting evidence here." in content
        assert "- File: Research Notes" in content
        assert "- Link: Reference" in content
        assert "## Category A" in content
        assert "- File: data/chart.png" in content

    def test_canvas_file_empty_nodes(self, tmp_path: Path) -> None:
        """Canvas with no nodes returns None (nothing to extract)."""
        from app.services.wiki.obsidian_adapter import adapt_obsidian_file

        vault = tmp_path / "vault"
        vault.mkdir()
        raw_dest = tmp_path / "raw"
        raw_dest.mkdir()
        assets = tmp_path / "assets"
        assets.mkdir()

        canvas_file = vault / "empty.canvas"
        canvas_file.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")

        dest_path, metadata, images = adapt_obsidian_file(canvas_file, vault, raw_dest, assets)
        assert dest_path is None

    def test_canvas_file_invalid_json(self, tmp_path: Path) -> None:
        """Corrupted .canvas file returns None without crashing."""
        from app.services.wiki.obsidian_adapter import adapt_obsidian_file

        vault = tmp_path / "vault"
        vault.mkdir()
        raw_dest = tmp_path / "raw"
        raw_dest.mkdir()
        assets = tmp_path / "assets"
        assets.mkdir()

        canvas_file = vault / "broken.canvas"
        canvas_file.write_text("{not valid json", encoding="utf-8")

        dest_path, metadata, images = adapt_obsidian_file(canvas_file, vault, raw_dest, assets)
        assert dest_path is None
        assert metadata == {}

    def test_canvas_nested_in_subdirectory(self, tmp_path: Path) -> None:
        """Canvas in nested vault directory produces correct relative output path."""
        from app.services.wiki.obsidian_adapter import adapt_obsidian_file

        vault = tmp_path / "vault"
        (vault / "projects" / "ai").mkdir(parents=True)
        raw_dest = tmp_path / "raw"
        raw_dest.mkdir()
        assets = tmp_path / "assets"
        assets.mkdir()

        canvas_data = {"nodes": [{"id": "1", "type": "text", "text": "Deep nested content"}]}
        canvas_file = vault / "projects" / "ai" / "diagram.canvas"
        canvas_file.write_text(json.dumps(canvas_data), encoding="utf-8")

        dest_path, _, _ = adapt_obsidian_file(canvas_file, vault, raw_dest, assets)

        assert dest_path is not None
        assert dest_path == raw_dest / "projects" / "ai" / "diagram.md"
        assert "Deep nested content" in dest_path.read_text()

    def test_canvas_text_nodes_only_empty_text_skipped(self, tmp_path: Path) -> None:
        """Text nodes with empty/whitespace text are filtered out."""
        from app.services.wiki.obsidian_adapter import adapt_obsidian_file

        vault = tmp_path / "vault"
        vault.mkdir()
        raw_dest = tmp_path / "raw"
        raw_dest.mkdir()
        assets = tmp_path / "assets"
        assets.mkdir()

        canvas_data = {
            "nodes": [
                {"id": "1", "type": "text", "text": "   "},
                {"id": "2", "type": "text", "text": ""},
                {"id": "3", "type": "text", "text": "Valid content"},
            ]
        }
        canvas_file = vault / "sparse.canvas"
        canvas_file.write_text(json.dumps(canvas_data), encoding="utf-8")

        dest_path, _, _ = adapt_obsidian_file(canvas_file, vault, raw_dest, assets)

        assert dest_path is not None
        content = dest_path.read_text()
        assert "Valid content" in content
        assert content.strip() == "Valid content"
