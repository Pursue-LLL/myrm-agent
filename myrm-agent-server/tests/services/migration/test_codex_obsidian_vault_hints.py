"""Tests for Obsidian vault hint extraction in Codex migration."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.migration.obsidian_vault_hints import (
    collect_codex_obsidian_vault_hints,
    extract_obsidian_vault_paths_from_settings,
)
from app.services.migration.source.source_payload_loaders_impl import load_codex
from app.services.migration.workspace_bind_candidates import (
    discover_workspace_bind_candidates,
)


def test_extract_obsidian_vault_paths_from_settings_nested_key(tmp_path: Path) -> None:
    vault = tmp_path / "Knowledge"
    vault.mkdir()
    settings = {
        "workspace": {
            "obsidian_vault": str(vault),
        },
    }
    assert extract_obsidian_vault_paths_from_settings(settings) == [str(vault.resolve())]


def test_load_codex_emits_obsidian_vault_hints(tmp_path: Path) -> None:
    codex_root = tmp_path / ".codex"
    codex_root.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    (vault / "note.md").write_text("# Note", encoding="utf-8")

    settings = {"obsidianVault": str(vault)}
    (codex_root / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    (codex_root / "instructions.md").write_text("Follow the vault.", encoding="utf-8")

    loaded = load_codex(
        codex_root,
        [str(codex_root / "settings.json"), str(codex_root / "instructions.md")],
    )
    hints = loaded.get("obsidian_vault_hints")
    assert isinstance(hints, list)
    assert str(vault.resolve()) in [str(Path(item).resolve()) for item in hints]


def test_discover_codex_workspace_bind_candidates(tmp_path: Path) -> None:
    vault = tmp_path / "OpenHuman" / "memory"
    vault.mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    (vault / "daily.md").write_text("# Daily", encoding="utf-8")

    loaded = {
        "_source": "codex",
        "_discovery_root": str(tmp_path),
        "obsidian_vault_hints": [str(vault)],
    }
    candidates = discover_workspace_bind_candidates(loaded)
    assert len(candidates) == 1
    assert candidates[0].has_obsidian_config is True
    assert candidates[0].markdown_file_count >= 1
    assert candidates[0].label == "OpenHuman memory vault"


def test_collect_codex_obsidian_vault_hints_scans_nearby_vaults(tmp_path: Path) -> None:
    codex_root = tmp_path / ".codex"
    codex_root.mkdir()
    sibling_vault = tmp_path / "notes-vault"
    sibling_vault.mkdir()
    (sibling_vault / ".obsidian").mkdir()

    hints = collect_codex_obsidian_vault_hints(None, discovery_root=codex_root)
    assert str(sibling_vault.resolve()) in hints
