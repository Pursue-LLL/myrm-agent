"""Unit tests for Obsidian canvas text extraction."""

import json
from pathlib import Path

from myrm_agent_harness.toolkits.wiki.portability import extract_canvas_text_nodes


def test_extract_canvas_text_nodes(tmp_path: Path):
    canvas_file = tmp_path / "architecture.canvas"
    canvas_payload = {
        "nodes": [
            {
                "id": "node-1",
                "type": "text",
                "text": "Microservice Gateway Architecture",
            },
            {
                "id": "node-2",
                "type": "file",
                "file": "specs/auth.md",
                "label": "Authentication Service Spec",
            },
            {
                "id": "node-3",
                "type": "link",
                "url": "https://example.com/api",
                "label": "API Docs",
            },
            {
                "id": "node-4",
                "type": "group",
                "label": "Core Cluster",
            },
        ],
        "edges": [],
    }
    canvas_file.write_text(json.dumps(canvas_payload), encoding="utf-8")

    nodes = extract_canvas_text_nodes(canvas_file)
    assert len(nodes) == 4

    types = {n.node_type for n in nodes}
    assert types == {"text", "file", "link", "group"}

    text_node = next(n for n in nodes if n.node_type == "text")
    assert text_node.content == "Microservice Gateway Architecture"

    file_node = next(n for n in nodes if n.node_type == "file")
    assert file_node.content == "specs/auth.md"
    assert file_node.label == "Authentication Service Spec"


def test_extract_canvas_edge_cases(tmp_path: Path):
    # Non-existent file
    assert extract_canvas_text_nodes(tmp_path / "missing.canvas") == []

    # Corrupted JSON
    corrupted = tmp_path / "corrupted.canvas"
    corrupted.write_text("{bad-json}", encoding="utf-8")
    assert extract_canvas_text_nodes(corrupted) == []

    # Non-dict payload
    non_dict = tmp_path / "array.canvas"
    non_dict.write_text("[1, 2, 3]", encoding="utf-8")
    assert extract_canvas_text_nodes(non_dict) == []

    # Invalid nodes container
    invalid_nodes = tmp_path / "bad_nodes.canvas"
    invalid_nodes.write_text(json.dumps({"nodes": "not-a-list"}), encoding="utf-8")
    assert extract_canvas_text_nodes(invalid_nodes) == []

    # Non-dict node entries inside list
    mixed_nodes = tmp_path / "mixed.canvas"
    mixed_nodes.write_text(json.dumps({"nodes": ["string-node", 123, None]}), encoding="utf-8")
    assert extract_canvas_text_nodes(mixed_nodes) == []

    # null fields are empty, never the text "None"
    null_fields = tmp_path / "null_fields.canvas"
    null_fields.write_text(
        json.dumps({"nodes": [{"type": "text", "text": None}, {"type": "file", "file": None, "label": None}]}),
        encoding="utf-8",
    )
    assert extract_canvas_text_nodes(null_fields) == []
