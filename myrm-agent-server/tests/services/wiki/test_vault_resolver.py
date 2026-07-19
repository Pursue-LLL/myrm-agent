"""Tests for wiki vault path resolver and legacy migration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.wiki.vault_resolver import (
    is_agent_layout_migration_complete,
    is_legacy_migration_complete,
    is_vault_ready,
    list_legacy_wiki_vault_paths,
    migrate_global_wiki_to_agent_layout,
    migrate_legacy_wiki_vaults,
    resolve_agent_wiki_vault_path,
    resolve_shared_wiki_vault_path,
    resolve_wiki_vault_path,
    sanitize_wiki_scope_id,
)


class TestResolveWikiVaultPath:
    def test_uses_agent_scoped_harness_dir(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)
            assert resolve_wiki_vault_path() == (harness / "wiki" / "agents" / "default").resolve()
            assert resolve_wiki_vault_path("planner") == (harness / "wiki" / "agents" / "planner").resolve()

    def test_shared_context_path(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            assert resolve_shared_wiki_vault_path("team-alpha") == (
                harness / "wiki" / "shared" / "team-alpha"
            ).resolve()

    def test_sanitize_scope_id(self) -> None:
        assert sanitize_wiki_scope_id(None) == "default"
        assert sanitize_wiki_scope_id("  legal-bot  ") == "legal-bot"
        assert sanitize_wiki_scope_id("weird/id") == "weird_id"


class TestLegacyMigration:
    def test_copies_legacy_raw_files_once(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        state_wiki = tmp_path / "wiki"
        legacy_raw = state_wiki / "raw"
        legacy_raw.mkdir(parents=True)
        (legacy_raw / "note.md").write_text("# Legacy note", encoding="utf-8")

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)

            first = migrate_legacy_wiki_vaults()
            second = migrate_legacy_wiki_vaults()

        canonical_raw = harness / "wiki" / "agents" / "default" / "raw" / "note.md"
        assert first.skipped is False
        assert first.files_copied == 1
        assert canonical_raw.exists()
        assert canonical_raw.read_text(encoding="utf-8") == "# Legacy note"
        assert second.skipped is True
        assert (state_wiki / "raw" / "note.md").exists()

    def test_does_not_overwrite_existing_canonical_files(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        canonical = harness / "wiki" / "agents" / "default" / "raw"
        canonical.mkdir(parents=True)
        (canonical / "note.md").write_text("canonical", encoding="utf-8")

        legacy = tmp_path / "wiki" / "raw"
        legacy.mkdir(parents=True)
        (legacy / "note.md").write_text("legacy", encoding="utf-8")

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)
            result = migrate_legacy_wiki_vaults()

        assert result.files_copied == 0
        assert (canonical / "note.md").read_text(encoding="utf-8") == "canonical"


    def test_moves_flat_root_layout_to_default_agent(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        flat_raw = harness / "wiki" / "raw"
        flat_raw.mkdir(parents=True)
        (flat_raw / "legacy.md").write_text("# flat", encoding="utf-8")

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)
            result = migrate_global_wiki_to_agent_layout()

            target = harness / "wiki" / "agents" / "default" / "raw" / "legacy.md"
            assert result.skipped is False
            assert result.entries_moved == 1
            assert target.exists()
            assert is_agent_layout_migration_complete() is True


class TestLegacyPaths:
    def test_includes_state_dir_wiki(self, tmp_path: Path) -> None:
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.state_dir = str(tmp_path / "state")
            paths = list_legacy_wiki_vault_paths()
        assert paths[0] == (tmp_path / "state" / "wiki").resolve()


class TestVaultHealthHelpers:
    def test_is_vault_ready_when_raw_exists(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        raw = harness / "wiki" / "agents" / "default" / "raw"
        raw.mkdir(parents=True)

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            assert is_vault_ready() is True
            assert is_vault_ready("planner") is False

    def test_is_vault_ready_false_without_raw(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        (harness / "wiki" / "agents" / "default").mkdir(parents=True)

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            assert is_vault_ready() is False

    def test_is_legacy_migration_complete_with_marker(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        wiki = harness / "wiki"
        wiki.mkdir(parents=True)
        (wiki / ".wiki_legacy_merged").write_text("", encoding="utf-8")

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            assert is_legacy_migration_complete() is True
