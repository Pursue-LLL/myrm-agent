"""Canvas service — Agent-facing canvas operations."""

from app.services.canvas.operations import (
    get_canvas_selection,
    get_canvas_state,
    insert_canvas_element,
)

__all__ = [
    "get_canvas_state",
    "get_canvas_selection",
    "insert_canvas_element",
]
