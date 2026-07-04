"""Tests for app.services.canvas._layout.

Covers: compute_layout with all three strategies (grid, tree, force).
"""

from __future__ import annotations

import pytest

from app.services.canvas._layout import (
    LayoutEdge,
    LayoutNode,
    NodePosition,
    compute_layout,
)


class TestGridLayout:
    def test_empty_nodes(self) -> None:
        assert compute_layout([], [], "grid") == []

    def test_single_node(self) -> None:
        nodes = [LayoutNode(id="a")]
        result = compute_layout(nodes, [], "grid")
        assert result == [NodePosition(id="a", x=0, y=0)]

    def test_row_wrap(self) -> None:
        nodes = [LayoutNode(id=f"n{i}", width=280) for i in range(8)]
        result = compute_layout(nodes, [], "grid", canvas_width=1000)
        ys = [p.y for p in result]
        assert ys[0] == 0
        assert max(ys) > 0
        assert ys[3] > ys[0]

    def test_no_overlap(self) -> None:
        nodes = [LayoutNode(id=f"n{i}") for i in range(10)]
        result = compute_layout(nodes, [], "grid")
        positions = [(p.x, p.y) for p in result]
        assert len(set(positions)) == 10


class TestTreeLayout:
    def test_linear_chain(self) -> None:
        nodes = [LayoutNode(id=f"n{i}") for i in range(4)]
        edges = [
            LayoutEdge("n0", "n1"),
            LayoutEdge("n1", "n2"),
            LayoutEdge("n2", "n3"),
        ]
        result = compute_layout(nodes, edges, "tree")
        xs = {p.id: p.x for p in result}
        assert xs["n0"] < xs["n1"] < xs["n2"] < xs["n3"]

    def test_fan_out(self) -> None:
        nodes = [LayoutNode(id=f"n{i}") for i in range(4)]
        edges = [
            LayoutEdge("n0", "n1"),
            LayoutEdge("n0", "n2"),
            LayoutEdge("n0", "n3"),
        ]
        result = compute_layout(nodes, edges, "tree")
        xs = {p.id: p.x for p in result}
        assert xs["n0"] == 0
        assert xs["n1"] == xs["n2"] == xs["n3"]
        ys = {p.id: p.y for p in result}
        assert ys["n1"] != ys["n2"]

    def test_handles_cycle(self) -> None:
        nodes = [LayoutNode(id=f"n{i}") for i in range(3)]
        edges = [
            LayoutEdge("n0", "n1"),
            LayoutEdge("n1", "n2"),
            LayoutEdge("n2", "n0"),
        ]
        result = compute_layout(nodes, edges, "tree")
        assert len(result) == 3

    def test_disconnected_nodes(self) -> None:
        nodes = [LayoutNode(id=f"n{i}") for i in range(5)]
        edges = [LayoutEdge("n0", "n1")]
        result = compute_layout(nodes, edges, "tree")
        assert len(result) == 5


class TestForceLayout:
    def test_two_connected_nodes_converge(self) -> None:
        nodes = [LayoutNode(id="a"), LayoutNode(id="b")]
        edges = [LayoutEdge("a", "b")]
        result = compute_layout(nodes, edges, "force")
        assert len(result) == 2
        dist = ((result[0].x - result[1].x) ** 2 + (result[0].y - result[1].y) ** 2) ** 0.5
        assert dist > 0

    def test_single_node(self) -> None:
        result = compute_layout([LayoutNode(id="x")], [], "force")
        assert result == [NodePosition(id="x", x=0.0, y=0.0)]

    def test_disconnected_nodes_spread(self) -> None:
        nodes = [LayoutNode(id=f"n{i}") for i in range(5)]
        result = compute_layout(nodes, [], "force")
        positions = [(p.x, p.y) for p in result]
        assert len(set(positions)) == 5

    def test_performance_reasonable(self) -> None:
        """50 nodes + 49 edges should complete in <1 second."""
        import time

        nodes = [LayoutNode(id=f"n{i}") for i in range(50)]
        edges = [LayoutEdge(f"n{i}", f"n{i+1}") for i in range(49)]
        start = time.perf_counter()
        result = compute_layout(nodes, edges, "force")
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0
        assert len(result) == 50


class TestComputeLayoutDispatch:
    def test_invalid_strategy_falls_back_to_grid(self) -> None:
        nodes = [LayoutNode(id="a"), LayoutNode(id="b")]
        result_grid = compute_layout(nodes, [], "grid")
        result_invalid = compute_layout(nodes, [], "invalid")  # type: ignore[arg-type]
        assert result_grid == result_invalid
