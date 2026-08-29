"""Unit tests for frontend_dev_pause gate."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from e2e_core import frontend_dev_pause as pause


@pytest.fixture
def isolated_pause_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "pause-dir"
    state.mkdir()
    # Pause path is independent of MYRM_DEV_STATE_DIR (isolate must not bypass).
    monkeypatch.setenv("MYRM_FRONTEND_DEV_PAUSE_DIR", str(state))
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path / "isolate-state"))
    monkeypatch.delenv("MYRM_FRONTEND_DEV_FORCE", raising=False)
    return state


def test_not_paused_by_default(isolated_pause_dir: Path) -> None:
    assert pause.is_frontend_dev_paused() is False
    assert pause.main(["check"]) == 1


def test_write_and_check_paused(isolated_pause_dir: Path) -> None:
    pause.write_frontend_dev_pause(600.0, reason="cleanup")
    assert pause.is_frontend_dev_paused() is True
    assert pause.main(["check"]) == 0
    assert pause.pause_remaining_sec() > 590.0
    assert (isolated_pause_dir / "frontend-dev-paused-until").is_file()


def test_isolate_state_dir_cannot_bypass_shared_pause(
    isolated_pause_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pause.write_frontend_dev_pause(600.0)
    # Even if isolate points MYRM_DEV_STATE_DIR elsewhere, pause still hits.
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path / "other-isolate"))
    assert pause.is_frontend_dev_paused() is True


def test_force_env_does_not_bypass_pause(isolated_pause_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pause.write_frontend_dev_pause(600.0)
    monkeypatch.setenv("MYRM_FRONTEND_DEV_FORCE", "1")
    assert pause.is_frontend_dev_paused() is True
    assert pause.force_allowed() is False


def test_expired_pause_auto_clears(isolated_pause_dir: Path) -> None:
    path = pause.pause_file_path()
    path.write_text(f"{time.time() - 1:.3f}\ncleanup\n", encoding="utf-8")
    assert pause.is_frontend_dev_paused() is False
    assert not path.is_file()


def test_clear_removes_stamp(isolated_pause_dir: Path) -> None:
    pause.write_frontend_dev_pause(600.0)
    assert pause.clear_frontend_dev_pause() is True
    assert pause.is_frontend_dev_paused() is False


def test_default_pause_sec_is_eight_hours() -> None:
    assert pause._DEFAULT_PAUSE_SEC == 28800.0
