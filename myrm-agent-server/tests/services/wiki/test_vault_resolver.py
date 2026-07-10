"""Tests for wiki vault path resolver and legacy migration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.wiki.vault_resolver import (
    list_legacy_wiki_vault_paths,
    migrate_legacy_wiki_vaults,
    resolve_wiki_vault_path,
)


class TestResolveWikiVaultPath:
    def test_uses_harness_dir(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)
            assert resolve_wiki_vault_path() == (harness / "wiki").resolve()


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

        canonical_raw = harness / "wiki" / "raw" / "note.md"
        assert first.skipped is False
        assert first.files_copied == 1
        assert canonical_raw.exists()
        assert canonical_raw.read_text(encoding="utf-8") == "# Legacy note"
        assert second.skipped is True
        assert (state_wiki / "raw" / "note.md").exists()

    def test_does_not_overwrite_existing_canonical_files(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        canonical = harness / "wiki" / "raw"
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


class TestLegacyPaths:
    def test_includes_state_dir_wiki(self, tmp_path: Path) -> None:
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.state_dir = str(tmp_path / "state")
            paths = list_legacy_wiki_vault_paths()
        assert paths[0] == (tmp_path / "state" / "wiki").resolve()
