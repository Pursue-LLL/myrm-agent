"""Unit tests for DownloadConfig — the settings a download manager applies."""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.browser.session.download.config import _DEFAULT_ALLOWED_EXTENSIONS, DownloadConfig


class TestDownloadConfig:
    def test_defaults(self, tmp_path: Path) -> None:
        cfg = DownloadConfig(downloads_dir=tmp_path / "downloads", confined_to=tmp_path)
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
            confined_to=tmp_path,
            max_file_size_mb=50,
            allowed_extensions=frozenset({"pdf", "csv"}),
        )
        assert cfg.downloads_dir == tmp_path
        assert cfg.max_file_size_mb == 50
        assert cfg.allowed_extensions == frozenset({"pdf", "csv"})

    def test_config_frozen(self, tmp_path: Path) -> None:
        cfg = DownloadConfig(downloads_dir=tmp_path / "downloads", confined_to=tmp_path)
        with pytest.raises(AttributeError):
            cfg.max_file_size_mb = 999  # type: ignore[misc]

    def test_the_directory_and_the_root_it_is_confined_to_have_no_default(self) -> None:
        with pytest.raises(TypeError):
            DownloadConfig()  # type: ignore[call-arg]


class TestConfinement:
    def test_a_directory_outside_the_root_is_refused(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"

        with pytest.raises(ValueError, match="must lie below confined_to"):
            DownloadConfig(downloads_dir=tmp_path / "elsewhere" / "downloads", confined_to=workspace)

    def test_a_directory_that_steps_out_of_the_root_with_dots_is_refused(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"

        with pytest.raises(ValueError, match="must lie below confined_to"):
            DownloadConfig(downloads_dir=workspace / ".." / "elsewhere", confined_to=workspace)

    def test_a_root_that_is_not_absolute_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must be an absolute path"):
            DownloadConfig(downloads_dir=Path("workspace/downloads"), confined_to=Path("workspace"))

    def test_the_directory_may_be_the_root_itself(self, tmp_path: Path) -> None:
        assert DownloadConfig(downloads_dir=tmp_path, confined_to=tmp_path).downloads_dir == tmp_path
