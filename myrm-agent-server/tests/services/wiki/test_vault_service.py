"""Tests for shared wiki archiver accessor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.wiki.pipeline.compiler import WikiCompiler

from app.services.wiki.vault import (
    get_wiki_archiver,
    get_wiki_structure,
    init_wiki_vault_at_startup,
    reset_wiki_archiver_cache_for_tests,
)


class TestGetWikiArchiver:
    def setup_method(self) -> None:
        reset_wiki_archiver_cache_for_tests()

    def teardown_method(self) -> None:
        reset_wiki_archiver_cache_for_tests()

    def test_reuses_cached_instance_for_same_llm(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        llm = MagicMock()
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)
            first = get_wiki_archiver(llm)
            second = get_wiki_archiver(llm)
        assert first is second

    def test_recreates_when_llm_changes(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)
            first = get_wiki_archiver(MagicMock())
            second = get_wiki_archiver(MagicMock())
        assert first is not second

    def test_recreates_when_agent_id_changes(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        llm = MagicMock()
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)
            legal = get_wiki_archiver(llm, agent_id="legal")
            life = get_wiki_archiver(llm, agent_id="life")
        assert legal is not life

    def test_recreates_when_manager_changes(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        llm = MagicMock()
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)
            first = get_wiki_archiver(llm, manager=MagicMock())
            second = get_wiki_archiver(llm, manager=MagicMock())
        assert first is not second

    def test_recreates_when_public_dirs_or_labels_change(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        pub1 = tmp_path / "pub1"
        pub2 = tmp_path / "pub2"
        llm = MagicMock()
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)
            first = get_wiki_archiver(llm, public_dirs=[pub1], public_dir_labels={"pub1": "Vault A"})
            second = get_wiki_archiver(llm, public_dirs=[pub1], public_dir_labels={"pub1": "Vault A"})
            third = get_wiki_archiver(llm, public_dirs=[pub1, pub2], public_dir_labels={"pub1": "Vault A", "pub2": "Vault B"})
        assert first is second
        assert first is not third


@pytest.mark.asyncio
async def test_init_wiki_vault_at_startup_runs_migration(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    mock_structure = MagicMock()

    with (
        patch("app.config.settings.settings") as mock_settings,
        patch(
            "app.services.wiki.vault.service.migrate_legacy_wiki_vaults",
            return_value=MagicMock(skipped=False, files_copied=2),
        ) as mock_migrate,
        patch(
            "app.services.wiki.vault.service.WikiStructure",
            return_value=mock_structure,
        ) as mock_ws,
    ):
        mock_settings.database.harness_dir = str(harness)
        await init_wiki_vault_at_startup()

    mock_migrate.assert_called_once()
    mock_ws.assert_called_once()
    mock_structure.ensure_structure.assert_called_once()


class TestGetWikiArchiverRequiresAModel:
    def test_rejects_a_missing_model(self) -> None:
        with pytest.raises(TypeError, match="model"):
            get_wiki_archiver(None)  # type: ignore[arg-type]


class TestGetWikiStructure:
    def setup_method(self) -> None:
        reset_wiki_archiver_cache_for_tests()

    def teardown_method(self) -> None:
        reset_wiki_archiver_cache_for_tests()

    def test_returns_the_agent_vault_without_starting_a_compile_worker(self, tmp_path: Path) -> None:
        with patch("app.services.wiki.vault.resolver.wiki_root", return_value=tmp_path / "wiki"):
            structure = get_wiki_structure("legal")

        assert structure.base_dir == (tmp_path / "wiki" / "agents" / "legal").resolve()
        assert structure.raw_dir.is_dir()
        assert str(structure.base_dir) not in WikiCompiler._active_workers

    def test_names_the_same_vault_as_the_archiver_of_that_agent(self, tmp_path: Path) -> None:
        with patch("app.services.wiki.vault.resolver.wiki_root", return_value=tmp_path / "wiki"):
            structure = get_wiki_structure("legal")
            archiver = get_wiki_archiver(MagicMock(), agent_id="legal")

        assert structure.base_dir == archiver._structure.base_dir

    def test_default_agent_scope_is_the_default_vault(self, tmp_path: Path) -> None:
        with patch("app.services.wiki.vault.resolver.wiki_root", return_value=tmp_path / "wiki"):
            assert get_wiki_structure().base_dir == get_wiki_structure("default").base_dir
