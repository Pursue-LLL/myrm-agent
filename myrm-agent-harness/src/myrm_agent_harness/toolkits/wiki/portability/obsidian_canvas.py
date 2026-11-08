"""Obsidian JSON Canvas (.canvas) text extraction.

[INPUT]
- pathlib::Path (POS: filesystem path operations)
- json (POS: JSON Canvas spec parsing)

[OUTPUT]
- CanvasTextNode: A textual node extracted from a .canvas file.
- extract_canvas_text_nodes: Extracts clean text nodes and labels from .canvas files.

[POS]
Harness-level pure file-format utilities for Obsidian interoperability.
Decoupled from database, network, and multi-tenant logic.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CanvasTextNode:
    """A textual node extracted from an Obsidian .canvas file."""

    node_id: str
    node_type: str  # "text", "file", "link", "group"
    content: str
    label: str = ""


def extract_canvas_text_nodes(canvas_path: Path | str) -> list[CanvasTextNode]:
    """Parse an Obsidian .canvas JSON file and extract textual node content.

    Complies with JSON Canvas 1.0 spec:
    - nodes[type="text"]: Extracts node.text
    - nodes[type="file"]: Extracts node.file and optional node.label
    - nodes[type="link"]: Extracts node.url and optional node.label
    - nodes[type="group"]: Extracts node.label (section titles)
    """
    path = Path(canvas_path)
    if not path.is_file():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        logger.debug("Failed to read or parse canvas file %s: %s", path, exc)
        return []

    if not isinstance(data, dict):
        return []

    nodes = data.get("nodes", [])
    if not isinstance(nodes, list):
        return []

    extracted: list[CanvasTextNode] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_id = str(node.get("id") or "")
        node_type = str(node.get("type") or "")
        text = str(node.get("text") or "").strip()
        label = str(node.get("label") or "").strip()

        if node_type == "text" and text:
            extracted.append(
                CanvasTextNode(
                    node_id=node_id,
                    node_type="text",
                    content=text,
                    label=label,
                )
            )
        elif node_type == "file":
            file_ref = str(node.get("file") or "").strip()
            if file_ref or label:
                extracted.append(
                    CanvasTextNode(
                        node_id=node_id,
                        node_type="file",
                        content=file_ref,
                        label=label,
                    )
                )
        elif node_type == "link":
            url = str(node.get("url") or "").strip()
            if url or label:
                extracted.append(
                    CanvasTextNode(
                        node_id=node_id,
                        node_type="link",
                        content=url,
                        label=label,
                    )
                )
        elif node_type == "group" and label:
            extracted.append(
                CanvasTextNode(
                    node_id=node_id,
                    node_type="group",
                    content=label,
                    label=label,
                )
            )

    return extracted
