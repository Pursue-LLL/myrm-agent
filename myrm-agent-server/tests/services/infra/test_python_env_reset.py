"""Deferred Python-environment reset: the request is consumed at startup and clears the environment once."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.code_execution.config import (
    ExecutionConfig,
    get_execution_config,
    set_execution_config,
)
from myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager import VenvManager

from app.services.infra.python_env_reset import (
    _MARKER_TTL_SECONDS,
    _marker_path,
    apply_pending_python_env_reset,
    cancel_python_env_reset,
    request_python_env_reset,
)
from app.services.instance_archive.policy import PathCategory, classify_path

pytestmark = pytest.mark.allow_blocking_io


@pytest.fixture
def state_dir(tmp_path: Path) -> Iterator[Path]:
    with patch("app.services.infra.python_env_reset.get_settings") as get_settings:
        get_settings.return_value.database.state_dir = str(tmp_path)
        yield tmp_path


@pytest.fixture
def shared_venv(tmp_path: Path) -> Iterator[Path]:
    """The execution config the harness hook resolves, pointed at a venv path under tmp."""
    venv_path = tmp_path / "venvs"
    previous = get_execution_config()
    config = ExecutionConfig()
    config.local.shared_venv_path = str(venv_path)
    set_execution_config(config)
    yield venv_path
    set_execution_config(previous)


def test_marker_never_travels_with_an_instance_backup(state_dir: Path) -> None:
    relative = _marker_path().relative_to(state_dir)

    assert classify_path(relative.parts).category is PathCategory.RUNTIME


def test_request_then_cancel_leaves_no_trace(state_dir: Path) -> None:
    assert request_python_env_reset() is True
    assert _marker_path().exists()

    cancel_python_env_reset()
    cancel_python_env_reset()  # withdrawing twice is harmless

    assert not _marker_path().exists()


def test_a_valid_request_already_pending_is_not_placed_again(state_dir: Path) -> None:
    """Only the call that placed a request may withdraw it, so a repeated call must not claim one."""
    assert request_python_env_reset() is True
    placed_at = _marker_path().stat().st_mtime

    assert request_python_env_reset() is False
    assert _marker_path().stat().st_mtime == placed_at


def test_a_stale_request_is_replaced_by_a_new_one(state_dir: Path) -> None:
    request_python_env_reset()
    stale = time.time() - _MARKER_TTL_SECONDS - 60
    os.utime(_marker_path(), (stale, stale))

    assert request_python_env_reset() is True
    assert time.time() - _marker_path().stat().st_mtime < _MARKER_TTL_SECONDS


@pytest.mark.asyncio
async def test_next_start_rebuilds_a_working_empty_environment(state_dir: Path, shared_venv: Path) -> None:
    """Outcome: after a requested reset the agent gets a fresh interpreter without what was installed before."""
    shared_venv.mkdir(parents=True)
    (shared_venv / "polluted.txt").write_text("leftover from a broken install")
    request_python_env_reset()

    assert apply_pending_python_env_reset() is True

    assert not _marker_path().exists()
    assert not shared_venv.exists()
    after = VenvManager(get_execution_config())
    interpreter = await after.get_python_executable()
    assert not (shared_venv / "polluted.txt").exists()
    result = subprocess.run([interpreter, "-c", "print(40 + 2)"], capture_output=True, text=True, check=False)
    assert result.stdout.strip() == "42"


def test_a_start_without_a_request_keeps_the_environment(state_dir: Path, shared_venv: Path) -> None:
    (shared_venv / "lib").mkdir(parents=True)

    assert apply_pending_python_env_reset() is False
    assert (shared_venv / "lib").exists()


def test_a_stale_request_is_dropped_without_touching_the_environment(state_dir: Path, shared_venv: Path) -> None:
    """A request from a reset that never completed must not wipe packages on some later restart."""
    (shared_venv / "lib").mkdir(parents=True)
    request_python_env_reset()
    stale = time.time() - _MARKER_TTL_SECONDS - 60
    os.utime(_marker_path(), (stale, stale))

    assert apply_pending_python_env_reset() is False
    assert (shared_venv / "lib").exists()
    assert not _marker_path().exists()


def test_a_failed_removal_is_not_retried_on_later_starts(state_dir: Path) -> None:
    request_python_env_reset()

    with (
        patch("app.services.infra.python_env_reset.discard_shared_venv", side_effect=OSError("read-only")),
        pytest.raises(OSError, match="read-only"),
    ):
        apply_pending_python_env_reset()

    assert not _marker_path().exists()
