"""Canvas layout algorithms for batch node positioning.

[INPUT]
(none — leaf utility, pure algorithms)

[OUTPUT]
- compute_layout: Dispatch to grid/tree/force strategy
- LayoutNode, LayoutEdge, NodePosition: dataclasses

[POS]
Pure-function layout engine for positioning nodes on a canvas.
Used by canvas_agent_tools.py batch_layout tool to compute (x, y) coordinates
before inserting shapes. Three strategies cover all common knowledge graph shapes:
grid (list/cards), tree (hierarchical DAG), force (associative network).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Literal

LayoutStrategy = Literal["grid", "tree", "force"]


@dataclass(frozen=True, slots=True)
class LayoutNode:
    """A node to be positioned."""

    id: str
    width: float = 280
    height: float = 120


@dataclass(frozen=True, slots=True)
class LayoutEdge:
    """A directed edge between two nodes."""

    from_id: str
    to_id: str


@dataclass(frozen=True, slots=True)
class NodePosition:
    """Computed position for a node."""

    id: str
    x: float
    y: float


def compute_layout(
    nodes: list[LayoutNode],
    edges: list[LayoutEdge],
    strategy: LayoutStrategy = "grid",
    canvas_width: float = 2000.0,
) -> list[NodePosition]:
    """Compute layout positions for nodes using the specified strategy."""
    if not nodes:
        return []
    if strategy == "tree":
        return _layout_tree(nodes, edges)
    if strategy == "force":
        return _layout_force(nodes, edges, canvas_width)
    return _layout_grid(nodes, canvas_width)


def _layout_grid(nodes: list[LayoutNode], canvas_width: float) -> list[NodePosition]:
    """Flow-based grid layout — fills rows left-to-right, wraps on overflow."""
    gap_x = 40.0
    gap_y = 40.0
    positions: list[NodePosition] = []
    x = 0.0
    y = 0.0
    row_height = 0.0

    for node in nodes:
        if x > 0 and x + node.width > canvas_width:
            x = 0.0
            y += row_height + gap_y
            row_height = 0.0
        positions.append(NodePosition(id=node.id, x=x, y=y))
        x += node.width + gap_x
        row_height = max(row_height, node.height)

    return positions


def _layout_tree(
    nodes: list[LayoutNode], edges: list[LayoutEdge]
) -> list[NodePosition]:
    """Layered DAG layout with topological sorting.

    Borrows from systemsculpt's layer assignment + barycenter ordering.
    Handles cycles by breaking back-edges.
    """
    node_map = {n.id: n for n in nodes}
    node_ids = [n.id for n in nodes]
    if not node_ids:
        return []

    successors: dict[str, list[str]] = {nid: [] for nid in node_ids}
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    node_set = set(node_ids)

    for edge in edges:
        if edge.from_id in node_set and edge.to_id in node_set:
            successors[edge.from_id].append(edge.to_id)
            in_degree[edge.to_id] += 1

    # Topological layer assignment (Kahn's algorithm with cycle tolerance)
    layers: dict[str, int] = {}
    roots = [nid for nid in node_ids if in_degree[nid] == 0]
    if not roots:
        roots = [node_ids[0]]
    queue: deque[str] = deque(roots)

    visited: set[str] = set()
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        layer = layers.get(current, 0)
        layers[current] = layer
        for succ in successors[current]:
            if succ not in visited:
                layers[succ] = max(layers.get(succ, 0), layer + 1)
                in_degree[succ] -= 1
                if in_degree[succ] <= 0:
                    queue.append(succ)

    # Assign unvisited nodes (cycle members) to max_layer + 1
    max_layer = max(layers.values()) if layers else 0
    for nid in node_ids:
        if nid not in layers:
            layers[nid] = max_layer + 1

    # Group by layer
    layer_groups: dict[int, list[str]] = {}
    for nid, layer_idx in layers.items():
        layer_groups.setdefault(layer_idx, []).append(nid)

    # Position: left-to-right layers, top-to-bottom within layer
    layer_gap_x = 350.0
    node_gap_y = 40.0
    positions: list[NodePosition] = []

    for layer_idx in sorted(layer_groups.keys()):
        group = layer_groups[layer_idx]
        x = layer_idx * layer_gap_x
        y = 0.0
        for nid in group:
            node = node_map[nid]
            positions.append(NodePosition(id=nid, x=x, y=y))
            y += node.height + node_gap_y

    return positions


def _layout_force(
    nodes: list[LayoutNode],
    edges: list[LayoutEdge],
    canvas_width: float,
) -> list[NodePosition]:
    """Fruchterman-Reingold force-directed layout.

    Suitable for networks without clear hierarchy.
    """
    n = len(nodes)
    if n == 1:
        return [NodePosition(id=nodes[0].id, x=0.0, y=0.0)]

    area = canvas_width * canvas_width
    k = math.sqrt(area / n)
    max_iterations = min(80, n * 4)
    temperature = canvas_width * 0.1

    pos: list[list[float]] = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        radius = canvas_width * 0.3
        pos.append([radius * math.cos(angle), radius * math.sin(angle)])

    id_to_idx = {nodes[i].id: i for i in range(n)}
    valid_edges = [
        (id_to_idx[e.from_id], id_to_idx[e.to_id])
        for e in edges
        if e.from_id in id_to_idx and e.to_id in id_to_idx
    ]

    for step in range(max_iterations):
        disp = [[0.0, 0.0] for _ in range(n)]
        temp = temperature * (1.0 - step / max_iterations)

        # Repulsive forces between all pairs
        for i in range(n):
            for j in range(i + 1, n):
                dx = pos[i][0] - pos[j][0]
                dy = pos[i][1] - pos[j][1]
                dist = max(math.sqrt(dx * dx + dy * dy), 0.01)
                force = (k * k) / dist
                fx = (dx / dist) * force
                fy = (dy / dist) * force
                disp[i][0] += fx
                disp[i][1] += fy
                disp[j][0] -= fx
                disp[j][1] -= fy

        # Attractive forces along edges
        for u, v in valid_edges:
            dx = pos[u][0] - pos[v][0]
            dy = pos[u][1] - pos[v][1]
            dist = max(math.sqrt(dx * dx + dy * dy), 0.01)
            force = (dist * dist) / k
            fx = (dx / dist) * force
            fy = (dy / dist) * force
            disp[u][0] -= fx
            disp[u][1] -= fy
            disp[v][0] += fx
            disp[v][1] += fy

        # Apply displacement with temperature limit
        for i in range(n):
            dx = disp[i][0]
            dy = disp[i][1]
            dist = max(math.sqrt(dx * dx + dy * dy), 0.01)
            scale = min(dist, temp) / dist
            pos[i][0] += dx * scale
            pos[i][1] += dy * scale

    # Normalize to start from (0, 0)
    min_x = min(p[0] for p in pos)
    min_y = min(p[1] for p in pos)

    return [
        NodePosition(
            id=nodes[i].id,
            x=round(pos[i][0] - min_x, 1),
            y=round(pos[i][1] - min_y, 1),
        )
        for i in range(n)
    ]
