"""LangChain agent tools for canvas interaction.

Server business layer — not a harness toolkit primitive.

[INPUT]
- app.services.canvas.operations (POS: Canvas agent-facing operations)
- app.services.canvas._events (POS: SSE event notification hub)
- app.services.canvas._layout (POS: Layout algorithms)

[OUTPUT]
- create_canvas_tools: LangChain tool factory

[POS]
Agent-callable canvas tools for Myrm. Wraps service-layer operations as
LangChain StructuredTools so the GeneralAgent can read/write canvas state.
Follows the same pattern as deploy_agent_tools.py.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import BaseTool, tool

from app.services.canvas._events import notify_batch_layout_done, notify_canvas_change
from app.services.canvas._layout import (
    LayoutEdge,
    LayoutNode,
    LayoutStrategy,
    compute_layout,
)
from app.services.canvas.operations import (
    batch_insert_canvas_elements,
    get_canvas_selection,
    get_canvas_state,
    insert_canvas_element,
)

logger = logging.getLogger(__name__)

ShapePropValue = str | int | float | bool | None | list[object] | dict[str, object]

__all__ = ["create_canvas_tools"]


def create_canvas_tools(canvas_id: str) -> list[BaseTool]:
    """Create canvas interaction tools bound to a specific canvas."""

    @tool("canvas_get_state")
    async def canvas_get_state_tool() -> str:
        """Read the full state of the user's canvas workspace.

        Returns the tldraw snapshot as JSON containing all shapes, their
        positions, text content, connections, and other visual properties.
        Use this when the user asks you to analyse, summarise, or act on
        what is on their canvas.
        """
        state = await get_canvas_state(canvas_id)
        if state is None:
            return json.dumps({"status": "empty", "message": "Canvas is empty"})
        shapes = state.get("store", {})
        shape_list = [
            v for v in shapes.values()
            if isinstance(v, dict) and v.get("typeName") == "shape"
        ]
        return json.dumps(
            {"status": "ok", "shape_count": len(shape_list), "shapes": shape_list},
            ensure_ascii=False,
        )

    @tool("canvas_get_selection")
    async def canvas_get_selection_tool() -> str:
        """Read the shapes currently selected by the user on the canvas.

        Returns only the selected shapes rather than the full canvas,
        which is cheaper and more targeted. Use this when the user says
        "this", "these", or refers to something they highlighted.
        """
        shapes = await get_canvas_selection(canvas_id)
        if not shapes:
            return json.dumps({"status": "empty", "message": "Nothing selected"})
        return json.dumps(
            {"status": "ok", "count": len(shapes), "selected_shapes": shapes},
            ensure_ascii=False,
        )

    @tool("canvas_insert_element")
    async def canvas_insert_element_tool(
        shape_type: str,
        x: float = 0,
        y: float = 0,
        props: dict[str, ShapePropValue] | None = None,
    ) -> str:
        """Insert a new shape element onto the user's canvas.

        Args:
            shape_type: tldraw shape type — "text", "note", "geo", "draw", etc.
            x: Horizontal position in canvas coordinates.
            y: Vertical position in canvas coordinates.
            props: Shape-specific properties. For "text"/"note" include {"text": "..."}.
                   For "geo" include {"geo": "rectangle", "w": 200, "h": 100}.
        """
        shape = await insert_canvas_element(canvas_id, shape_type, x, y, props)
        notify_canvas_change(canvas_id)
        return json.dumps(
            {"status": "ok", "inserted_shape": shape},
            ensure_ascii=False,
        )

    @tool("canvas_batch_layout")
    async def canvas_batch_layout_tool(
        nodes: list[dict[str, str]],
        edges: list[dict[str, str]] | None = None,
        layout: str = "grid",
    ) -> str:
        """Insert multiple nodes with automatic layout and optional connecting arrows.

        Use this instead of calling canvas_insert_element repeatedly when you
        need to place several related concepts, a knowledge graph, architecture
        diagram, or mind map.

        Args:
            nodes: List of nodes to insert. Each dict: {"id": "unique_key", "text": "content"}.
                   'id' is a logical key used to reference nodes in edges.
            edges: Optional list of directed connections. Each dict:
                   {"from_id": "source_key", "to_id": "target_key", "label": "optional text"}.
            layout: Layout strategy — "grid" (flat list), "tree" (hierarchy/DAG),
                    or "force" (associative network). Default "grid".
        """
        if not nodes:
            return json.dumps({"status": "error", "message": "No nodes provided"})

        strategy: LayoutStrategy = (
            layout if layout in ("grid", "tree", "force") else "grid"
        )

        layout_nodes = [
            LayoutNode(id=n.get("id", f"n{i}"), width=280, height=120)
            for i, n in enumerate(nodes)
        ]
        layout_edges = [
            LayoutEdge(from_id=e["from_id"], to_id=e["to_id"])
            for e in (edges or [])
            if "from_id" in e and "to_id" in e
        ]

        positions = compute_layout(layout_nodes, layout_edges, strategy)
        pos_map = {p.id: p for p in positions}

        shapes_to_insert = []
        for i, n in enumerate(nodes):
            nid = n.get("id", f"n{i}")
            text = n.get("text", "")
            pos = pos_map.get(nid)
            shapes_to_insert.append({
                "id": nid,
                "type": "note",
                "x": pos.x if pos else 0,
                "y": pos.y if pos else 0,
                "props": {"text": text},
            })

        arrows_to_insert = [
            {"from_id": e["from_id"], "to_id": e["to_id"], "label": e.get("label", "")}
            for e in (edges or [])
            if "from_id" in e and "to_id" in e
        ]

        result = await batch_insert_canvas_elements(
            canvas_id, shapes_to_insert, arrows_to_insert
        )
        notify_batch_layout_done(canvas_id)

        return json.dumps(
            {
                "status": "ok",
                "layout": strategy,
                "nodes_inserted": len(result["inserted_shapes"]),
                "arrows_inserted": len(result["inserted_arrows"]),
            },
            ensure_ascii=False,
        )

    return [
        canvas_get_state_tool,
        canvas_get_selection_tool,
        canvas_insert_element_tool,
        canvas_batch_layout_tool,
    ]
