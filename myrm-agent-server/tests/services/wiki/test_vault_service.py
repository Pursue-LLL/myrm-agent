"""Tests for shared wiki archiver accessor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.wiki.vault_service import get_wiki_archiver, reset_wiki_archiver_cache_for_tests


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
