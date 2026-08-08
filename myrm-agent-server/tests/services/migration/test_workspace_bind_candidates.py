"""Tests for migration workspace bind candidate discovery."""

from __future__ import annotations

from pathlib import Path

from app.services.migration.workspace_bind_candidates import (
    discover_workspace_bind_candidates,
)


def test_discover_openclaw_workspace_bind_candidates(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note-a.md").write_text("# A", encoding="utf-8")
    (workspace / ".obsidian").mkdir()

    loaded = {
        "_source": "openclaw",
        "_discovery_root": str(tmp_path),
    }

    candidates = discover_workspace_bind_candidates(loaded)
    paths = {item.path for item in candidates}

    assert str(workspace.resolve()) in paths
    primary = next(item for item in candidates if item.path == str(workspace.resolve()))
    assert primary.has_obsidian_config is True
    assert primary.markdown_file_count >= 1
    assert primary.label == "OpenClaw workspace"


def test_discover_workspace_bind_candidates_non_openclaw_returns_empty(
    tmp_path: Path,
) -> None:
    loaded = {
        "_source": "hermes",
        "_discovery_root": str(tmp_path),
    }
    assert discover_workspace_bind_candidates(loaded) == []


def test_discover_workspace_bind_candidates_codex_empty_without_hints(
    tmp_path: Path,
) -> None:
    loaded = {
        "_source": "codex",
        "_discovery_root": str(tmp_path),
    }
    assert discover_workspace_bind_candidates(loaded) == []
