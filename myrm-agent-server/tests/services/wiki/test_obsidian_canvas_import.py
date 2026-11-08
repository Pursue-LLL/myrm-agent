"""Tests for turning Obsidian JSON Canvas (.canvas) files into Markdown raw documents."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.wiki.obsidian import ObsidianRawPrepared, parse_frontmatter, prepare_obsidian_file


def _prepare(vault: Path, relative_path: str, payload: object) -> ObsidianRawPrepared | None:
    canvas = vault / relative_path
    canvas.parent.mkdir(parents=True, exist_ok=True)
    canvas.write_text(json.dumps(payload), encoding="utf-8")
    return prepare_obsidian_file(canvas, vault, vault / "assets")


def _body(prepared: ObsidianRawPrepared) -> str:
    return parse_frontmatter(prepared.content)[1].strip()


def test_node_kinds_become_markdown_sections(tmp_path: Path) -> None:
    prepared = _prepare(
        tmp_path,
        "boards/architecture.canvas",
        {
            "nodes": [
                {"id": "1", "type": "text", "text": "Microservice Gateway Architecture"},
                {"id": "2", "type": "file", "file": "specs/auth.md", "label": "Authentication Service Spec"},
                {"id": "3", "type": "link", "url": "https://example.com/api", "label": "API Docs"},
                {"id": "4", "type": "group", "label": "Core Cluster"},
            ],
            "edges": [],
        },
    )

    assert prepared is not None
    assert prepared.relative_path == "boards/architecture.md"
    assert prepared.images_copied == 0
    assert _body(prepared) == (
        "Microservice Gateway Architecture\n\n- File: Authentication Service Spec\n\n- Link: API Docs\n\n## Core Cluster"
    )
    assert prepared.metadata["source_type"] == "canvas"
    assert prepared.metadata["provenance"] == "obsidian_canvas_import"
    assert prepared.metadata["sources"] == ["boards/architecture.md"]


def test_file_and_link_nodes_without_a_label_show_the_path_and_url(tmp_path: Path) -> None:
    prepared = _prepare(
        tmp_path,
        "board.canvas",
        {"nodes": [{"type": "file", "file": "specs/auth.md"}, {"type": "link", "url": "https://example.com/api"}]},
    )

    assert prepared is not None
    assert _body(prepared) == "- File: specs/auth.md\n\n- Link: https://example.com/api"


@pytest.mark.parametrize(
    "payload",
    [
        {"nodes": []},
        {"nodes": [{"type": "group"}, {"type": "text", "text": "   "}, {"type": "image", "file": "a.png"}]},
        [1, 2, 3],
        {"nodes": "not-a-list"},
        {"nodes": ["string-node", 123, None]},
        {"nodes": [{"type": "text", "text": None}, {"type": "file", "file": None, "label": None}]},
    ],
    ids=["no-nodes", "no-text", "array-payload", "nodes-not-a-list", "non-object-nodes", "null-fields"],
)
def test_canvas_without_text_is_skipped(tmp_path: Path, payload: object) -> None:
    assert _prepare(tmp_path, "board.canvas", payload) is None


def test_unreadable_canvas_is_skipped(tmp_path: Path) -> None:
    corrupted = tmp_path / "corrupted.canvas"
    corrupted.write_text("{bad-json}", encoding="utf-8")

    assert prepare_obsidian_file(corrupted, tmp_path, tmp_path / "assets") is None
    assert prepare_obsidian_file(tmp_path / "missing.canvas", tmp_path, tmp_path / "assets") is None


def test_malformed_nodes_do_not_hide_the_valid_ones(tmp_path: Path) -> None:
    prepared = _prepare(tmp_path, "board.canvas", {"nodes": ["string-node", None, {"type": "text", "text": "kept"}]})

    assert prepared is not None
    assert _body(prepared) == "kept"
