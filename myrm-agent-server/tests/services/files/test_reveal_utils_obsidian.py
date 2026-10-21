"""Tests for obsidian direct launch availability flag."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.files.reveal_utils import is_obsidian_app_installed, is_obsidian_direct_launch_available


def test_obsidian_direct_launch_requires_local_mode_and_app() -> None:
    with (
        patch("app.config.deploy_mode.is_local_mode", return_value=True),
        patch("app.services.files.reveal_utils.is_obsidian_app_installed", return_value=True),
    ):
        assert is_obsidian_direct_launch_available() is True


def test_obsidian_direct_launch_false_when_app_missing() -> None:
    with (
        patch("app.config.deploy_mode.is_local_mode", return_value=True),
        patch("app.services.files.reveal_utils.is_obsidian_app_installed", return_value=False),
    ):
        assert is_obsidian_direct_launch_available() is False


def test_obsidian_direct_launch_true_on_windows_local_when_installed() -> None:
    with (
        patch("app.config.deploy_mode.is_local_mode", return_value=True),
        patch("app.services.files.reveal_utils.is_obsidian_app_installed", return_value=True),
    ):
        assert is_obsidian_direct_launch_available() is True


def test_obsidian_direct_launch_false_in_cloud_mode() -> None:
    with (
        patch("app.config.deploy_mode.is_local_mode", return_value=False),
        patch("app.services.files.reveal_utils.is_obsidian_app_installed", return_value=True),
    ):
        assert is_obsidian_direct_launch_available() is False


def test_obsidian_app_installed_checks_standard_macos_paths(tmp_path) -> None:
    app_path = tmp_path / "Obsidian.app"
    app_path.mkdir()
    with (
        patch("app.services.files.reveal_utils.platform.system", return_value="Darwin"),
        patch(
            "app.services.files.reveal_utils._OBSIDIAN_MACOS_APP_CANDIDATES",
            (app_path,),
        ),
    ):
        assert is_obsidian_app_installed() is True


def test_obsidian_app_installed_checks_windows_executable(tmp_path) -> None:
    exe_path = tmp_path / "Obsidian.exe"
    exe_path.write_text("", encoding="utf-8")
    with (
        patch("app.services.files.reveal_utils.platform.system", return_value="Windows"),
        patch(
            "app.services.files.reveal_utils._obsidian_windows_executable_candidates",
            return_value=(exe_path,),
        ),
    ):
        assert is_obsidian_app_installed() is True


def test_obsidian_app_installed_checks_linux_path() -> None:
    fake_bin = Path("/usr/bin/obsidian")
    with (
        patch("app.services.files.reveal_utils.platform.system", return_value="Linux"),
        patch("app.services.files.reveal_utils.shutil.which", return_value=str(fake_bin)),
    ):
        assert is_obsidian_app_installed() is True
