"""Loader and probe tests for assistant memory lanes (Claude Code / Codex / PLUR)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.services.memory.imports.import_adapters import build_memory_import_dry_run
from app.services.migration.source.source_discovery import discover_external_sources
from app.services.migration.source.source_payload_loader import (
    build_coverage_items,
    load_source_payload,
)
from app.services.migration.source.source_payload_loaders_impl import (
    load_claude,
    load_codex,
    load_plur,
)
from app.services.migration.source.source_payload_split import (
    build_instruction_plan,
    extract_memory_payload,
)
from app.services.migration.source.source_probes import discover_claude, discover_codex, discover_plur

_CLAUDE_MEMORY_FILE = """---
name: no-git-confirm
description: "Don't ask for confirmation on git commands - execute directly"
metadata:
  node_type: memory
  type: feedback
  originSessionId: sess-1
---

Don't ask for confirmation on git commands - execute directly.
"""

_CLAUDE_INDEX_FILE = "- [No Git Confirm](feedback_no_git_confirm.md) — Don't ask for confirmation on git commands\n"

_OFFICIAL_ENGRAM_YAML = """engrams:
  - id: ENG-2026-05-06-001
    statement: "Always use Pydantic v2 BaseModels with strict types"
    type: behavioral
    status: active
    scope: global
    domain: backend
  - id: ENG-2026-05-06-002
    statement: "Old deploy checklist superseded by the pipeline"
    type: procedural
    status: retired
    scope: global
    domain: ops
"""


def _build_claude_home(tmp_path: Path) -> Path:
    root = tmp_path / ".claude"
    root.mkdir()
    (root / "CLAUDE.md").write_text("Be precise.\n", encoding="utf-8")
    (root / "settings.json").write_text("{}", encoding="utf-8")
    memory_dir = root / "projects" / "-Users-me-repo" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text(_CLAUDE_INDEX_FILE, encoding="utf-8")
    (memory_dir / "feedback_no_git_confirm.md").write_text(_CLAUDE_MEMORY_FILE, encoding="utf-8")
    return root


def test_claude_probe_discovers_auto_memory_files(tmp_path: Path) -> None:
    root = _build_claude_home(tmp_path)

    source = discover_claude(explicit_home=tmp_path)

    assert source is not None
    assert source.competitor == "claude"
    kinds = {item.kind for item in source.files}
    assert "claude_md" in kinds
    assert "claude_memory" in kinds
    assert source.memory_count_estimate >= 2
    assert str(root) == source.root


def test_claude_loader_reads_memory_and_keeps_instructions_separate(tmp_path: Path) -> None:
    _build_claude_home(tmp_path)

    loaded = load_claude(tmp_path / ".claude", [])

    assert loaded["claude_md"] == "Be precise."
    memory_items = loaded["semantic"]
    assert isinstance(memory_items, list) and len(memory_items) == 1
    item = memory_items[0]
    assert item["content"] == "Don't ask for confirmation on git commands - execute directly."
    assert item["tags"][:1] == ["claude_code_memory"]
    assert item["metadata"]["external_type"] == "feedback"

    instruction_plan = build_instruction_plan({"claude_md": loaded["claude_md"], "_source": "claude"})
    assert "Be precise." in instruction_plan.agent_persona

    memory_payload = extract_memory_payload({**loaded, "_source": "claude"}, include_episodic=False)
    assert "claude_md" not in memory_payload
    assert memory_payload["semantic"]

    coverage_labels = {row["label"] for row in build_coverage_items({**loaded, "_source": "claude"})}
    assert "instruction_lane" in coverage_labels
    assert "memory_lane" in coverage_labels


def test_claude_memory_index_is_a_fallback_when_no_individual_files(tmp_path: Path) -> None:
    root = tmp_path / ".claude"
    root.mkdir()
    memory_dir = root / "projects" / "p" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "MEMORY.md").write_text(_CLAUDE_INDEX_FILE, encoding="utf-8")

    loaded = load_claude(root, [])

    items = loaded["semantic"]
    assert isinstance(items, list) and len(items) == 1
    assert "No Git Confirm" in str(items[0]["content"])


def test_claude_custom_auto_memory_directory_is_honored(tmp_path: Path) -> None:
    root = tmp_path / ".claude"
    root.mkdir()
    custom_dir = tmp_path / "custom-memory"
    custom_dir.mkdir()
    (custom_dir / "note.md").write_text("Custom memory note.", encoding="utf-8")
    (root / "settings.json").write_text(json.dumps({"autoMemoryDirectory": str(custom_dir)}), encoding="utf-8")

    source = discover_claude(explicit_home=tmp_path)
    loaded = load_claude(root, [])

    assert source is not None
    assert any(item.kind == "claude_memory" for item in source.files)
    assert [item["content"] for item in loaded["semantic"]] == ["Custom memory note."]


def test_claude_dry_run_imports_memory_lane(tmp_path: Path) -> None:
    _build_claude_home(tmp_path)
    payload = {"competitor": "claude", "root": str(tmp_path / ".claude"), "files": []}

    loaded = load_source_payload(payload)
    memory_payload = extract_memory_payload(loaded, include_episodic=False)
    result = build_memory_import_dry_run(memory_payload, "claude")

    assert result.summary.source == "claude"
    assert result.summary.mapped_items == 1
    assert result.normalized_data["semantic"]


def _build_codex_home(tmp_path: Path) -> Path:
    root = tmp_path / ".codex"
    root.mkdir()
    (root / "instructions.md").write_text("Prefer small diffs.", encoding="utf-8")
    memories = root / "memories"
    memories.mkdir()
    (memories / "MEMORY.md").write_text("- Deploys wait for migrations\n", encoding="utf-8")
    (memories / "memory_summary.md").write_text("Consolidated summary text.", encoding="utf-8")
    return root


def test_codex_probe_and_loader_read_memories(tmp_path: Path) -> None:
    root = _build_codex_home(tmp_path)

    source = discover_codex(explicit_home=tmp_path)
    loaded = load_codex(root, [])

    assert source is not None
    assert any(item.kind == "codex_memory" for item in source.files)
    assert source.memory_count_estimate >= 2
    entries = loaded["codex_memory"]
    assert isinstance(entries, list) and len(entries) == 2

    result = build_memory_import_dry_run({**loaded, "_source": "codex"}, "codex")
    assert result.summary.source == "codex"
    contents = [item["content"] for item in result.normalized_data["semantic"]]
    assert any("Deploys wait for migrations" in content for content in contents)
    assert "Consolidated summary text." in contents


def test_plur_probe_loader_and_discovery(tmp_path: Path) -> None:
    store = tmp_path / ".plur"
    store.mkdir()
    (store / "engrams.yaml").write_text(_OFFICIAL_ENGRAM_YAML, encoding="utf-8")

    source = discover_plur(explicit_home=tmp_path)
    assert source is not None
    assert source.memory_count_estimate == 2

    discovery = discover_external_sources(home_dir=str(tmp_path))
    assert any(item.competitor == "plur" for item in discovery.sources)

    loaded = load_plur(store, [])
    engrams = loaded["engrams"]
    assert isinstance(engrams, list) and len(engrams) == 2

    result = build_memory_import_dry_run({**loaded, "_source": "plur"}, "plur")
    assert result.summary.source == "plur"
    assert result.summary.mapped_items == 1
    assert result.summary.unmapped_items == 1
    assert result.normalized_data["procedural"][0]["content"] == "Always use Pydantic v2 BaseModels with strict types"


def test_sandbox_payload_loading_allows_upload_root_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.migration.source.source_payload_loader.is_local_mode",
        lambda: False,
    )
    upload_root = Path(tempfile.mkdtemp(prefix="myrm_migration_"))
    (upload_root / "engrams.yaml").write_text(_OFFICIAL_ENGRAM_YAML, encoding="utf-8")

    try:
        loaded = load_source_payload({"competitor": "plur", "root": str(upload_root), "files": []})
        assert loaded.get("_load_error") is None
        assert loaded.get("engrams")

        with pytest.raises(ValueError):
            load_source_payload({"competitor": "plur", "root": str(tmp_path), "files": []})
    finally:
        for child in sorted(upload_root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
        upload_root.rmdir()


def test_sandbox_payload_loading_ignores_files_outside_the_upload_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client-provided ``files`` must not reach host paths outside the archive."""

    monkeypatch.setattr(
        "app.services.migration.source.source_payload_loader.is_local_mode",
        lambda: False,
    )
    upload_root = Path(tempfile.mkdtemp(prefix="myrm_migration_"))
    outside_home = tmp_path / "real_home"
    outside_home.mkdir()
    (outside_home / ".env").write_text("OPENAI_API_KEY=sk-secret\n", encoding="utf-8")
    (outside_home / "MEMORY.md").write_text("- Outside host memory\n", encoding="utf-8")
    inside_memory = upload_root / "MEMORY.md"
    inside_memory.write_text("- Memory from the uploaded archive\n", encoding="utf-8")

    try:
        loaded = load_source_payload(
            {
                "competitor": "hermes",
                "root": str(upload_root),
                "files": [str(outside_home / ".env"), str(outside_home / "MEMORY.md"), str(inside_memory)],
            },
        )

        assert loaded.get("memory_md") == "- Memory from the uploaded archive\n"
        assert "env_keys" not in loaded
    finally:
        for child in sorted(upload_root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
        upload_root.rmdir()
