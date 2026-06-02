"""Tests for SearXNG auto-bootstrap."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.startup.local_search_bootstrap import try_start_local_search_profile


def test_skips_when_docker_missing() -> None:
    with patch("app.startup.local_search_bootstrap.shutil.which", return_value=None):
        assert try_start_local_search_profile(blocking=True) is False


def test_invokes_compose_when_docker_available(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    with (
        patch("app.startup.local_search_bootstrap.shutil.which", return_value="/usr/bin/docker"),
        patch("app.startup.local_search_bootstrap._COMPOSE_FILE", compose),
        patch("app.startup.local_search_bootstrap._SERVER_ROOT", tmp_path),
        patch("app.startup.local_search_bootstrap.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        assert try_start_local_search_profile(blocking=True) is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "compose" in args
        assert "search" in args
