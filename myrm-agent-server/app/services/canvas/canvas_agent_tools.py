"""LangChain agent tools for canvas interaction.

Server business layer — not a harness toolkit primitive.

[INPUT]
- app.services.canvas.operations (POS: Canvas agent-facing operations)
- app.services.canvas._events (POS: SSE event notification hub)

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

from app.services.canvas._events import notify_canvas_change
from app.services.canvas.operations import (
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

    return [canvas_get_state_tool, canvas_get_selection_tool, canvas_insert_element_tool]
