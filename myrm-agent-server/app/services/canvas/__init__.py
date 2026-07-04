"""Canvas service — Agent-facing canvas operations and tools."""

from app.services.canvas.operations import (
    batch_insert_canvas_elements,
    get_canvas_selection,
    get_canvas_state,
    insert_canvas_element,
    save_canvas_snapshot,
)

__all__ = [
    "batch_insert_canvas_elements",
    "get_canvas_state",
    "get_canvas_selection",
    "insert_canvas_element",
    "save_canvas_snapshot",
]
