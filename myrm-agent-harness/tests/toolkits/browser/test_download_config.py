"""Unit tests for DownloadConfig — the settings a download manager applies."""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.browser.session.download.config import _DEFAULT_ALLOWED_EXTENSIONS, DownloadConfig


class TestDownloadConfig:
    def test_default_config(self) -> None:
        cfg = DownloadConfig()
        assert cfg.max_file_size_mb == 100
        assert cfg.download_timeout_s == 60.0
        assert cfg.max_concurrent_downloads == 3
        assert cfg.allowed_extensions is _DEFAULT_ALLOWED_EXTENSIONS
        assert cfg.max_files == 200
        assert cfg.max_total_mb == 1024
        assert cfg.admit_page_started is None

    def test_custom_config(self, tmp_path: Path) -> None:
        cfg = DownloadConfig(
            downloads_dir=tmp_path,
            max_file_size_mb=50,
            allowed_extensions=frozenset({"pdf", "csv"}),
        )
        assert cfg.downloads_dir == tmp_path
        assert cfg.max_file_size_mb == 50
        assert cfg.allowed_extensions == frozenset({"pdf", "csv"})

    def test_config_frozen(self) -> None:
        cfg = DownloadConfig()
        with pytest.raises(AttributeError):
            cfg.max_file_size_mb = 999  # type: ignore[misc]
