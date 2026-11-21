"""VenvManager when ``python -m venv`` does not simply succeed: it fails before or after linking the interpreter, cannot start, hangs, or
the venv is discarded or already there. A failed build never removes the directory: another process may be building in it."""

from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.common import venv_manager
from tests.toolkits.code_execution._venv_spawn import VENV_SPAWN, FakeVenvSpawn, let_the_loop_run, make_manager


async def test_a_build_that_fails_after_the_link_falls_back_to_system_python_and_leaves_the_venv_alone(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spawn = FakeVenvSpawn(build_exit=1, hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn), caplog.at_level(logging.ERROR):
        assert await manager.get_python_executable() == str(tmp_path / "venvs" / "bin" / "python")
        spawn.release_build.set()
        await manager.ensure_pip_ready_for("pip install requests")
        assert await manager.get_python_executable() == sys.executable
        assert await manager.rewrite_pip_command("pip install requests") == "pip install requests"

    assert (tmp_path / "venvs" / "bin" / "python").is_symlink()
    assert "ensurepip failed" in caplog.text
    assert len(spawn.creations) == 1


async def test_a_build_that_has_failed_by_the_time_it_is_looked_at_gives_system_python_at_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spawn = FakeVenvSpawn(build_exit=1)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn), caplog.at_level(logging.ERROR):
        interpreter = await manager.get_python_executable()

    assert interpreter == sys.executable
    assert (tmp_path / "venvs").exists()
    assert "ensurepip failed" in caplog.text


async def test_a_failed_build_leaves_what_another_process_has_written_in_the_directory(tmp_path: Path) -> None:
    """Processes that start together run ``python -m venv`` on the same path; each can fail where another succeeds, so none may clean up."""
    spawn = FakeVenvSpawn(build_exit=1, hold_build=True)
    manager = make_manager(tmp_path)
    venv = tmp_path / "venvs"

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        (venv / "lib" / "site-packages").mkdir(parents=True)
        (venv / "lib" / "site-packages" / "written_by_another_process.py").touch()
        spawn.release_build.set()
        await manager.ensure_pip_ready_for("pip install requests")

    assert (venv / "lib" / "site-packages" / "written_by_another_process.py").exists()
    assert (venv / "bin" / "python").is_symlink()


async def test_a_build_that_dies_before_it_links_anything_falls_back_and_leaves_what_it_left(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "venvs" / "lib").mkdir(parents=True)
    spawn = FakeVenvSpawn(dies_before_linking=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn), caplog.at_level(logging.ERROR):
        interpreter = await asyncio.wait_for(manager.get_python_executable(), timeout=1)
        await asyncio.wait_for(manager.ensure_pip_ready_for("pip install requests"), timeout=1)

    assert interpreter == sys.executable
    assert (tmp_path / "venvs" / "lib").exists()
    assert "venv failed" in caplog.text


async def test_a_build_that_cannot_start_falls_back_the_same_way(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spawn = FakeVenvSpawn(spawn_error=OSError("exec format error"))
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn), caplog.at_level(logging.ERROR):
        interpreter = await manager.get_python_executable()
        await asyncio.wait_for(manager.ensure_pip_ready_for("pip install requests"), timeout=1)

    assert interpreter == sys.executable
    assert not (tmp_path / "venvs").exists()
    assert "exec format error" in caplog.text


async def test_the_build_log_is_created_next_to_the_venv_so_an_unusable_system_temp_dir_cannot_stop_the_build(
    tmp_path: Path,
) -> None:
    spawn = FakeVenvSpawn()
    manager = make_manager(tmp_path)

    with (
        patch(VENV_SPAWN, side_effect=spawn),
        patch(f"{venv_manager.__name__}.tempfile.TemporaryFile", wraps=tempfile.TemporaryFile) as create_log,
    ):
        await manager.get_python_executable()

    assert create_log.call_args.kwargs == {"dir": tmp_path}


async def test_a_build_log_that_cannot_be_created_falls_back_without_starting_the_build(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spawn = FakeVenvSpawn()
    manager = make_manager(tmp_path)

    with (
        patch(VENV_SPAWN, side_effect=spawn),
        patch(f"{venv_manager.__name__}.tempfile.TemporaryFile", side_effect=OSError("no space left on device")),
        caplog.at_level(logging.ERROR),
    ):
        interpreter = await manager.get_python_executable()

    assert interpreter == sys.executable
    assert spawn.calls == []
    assert "no space left on device" in caplog.text


async def test_a_failed_build_keeps_a_venv_whose_pip_arrived_meanwhile(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(build_exit=1, hold_build=True)
    manager = make_manager(tmp_path)
    venv = tmp_path / "venvs"

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        (venv / "bin" / "pip").touch()
        spawn.release_build.set()
        await manager.ensure_pip_ready_for("pip install requests")
        interpreter = await manager.get_python_executable()

    assert interpreter == str(venv / "bin" / "python")
    assert (venv / "bin" / "pip").exists()


async def test_a_build_that_never_links_is_stopped_at_the_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(venv_manager, "_BUILD_TIMEOUT_SECONDS", 0.05)
    spawn = FakeVenvSpawn(hold_links=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn), caplog.at_level(logging.ERROR):
        interpreter = await asyncio.wait_for(manager.get_python_executable(), timeout=1)

    assert interpreter == sys.executable
    assert spawn.terminated == 1
    assert "timed out" in caplog.text


async def test_a_build_that_links_but_never_ends_is_stopped_at_the_deadline_and_the_system_python_takes_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(venv_manager, "_BUILD_TIMEOUT_SECONDS", 0.05)
    spawn = FakeVenvSpawn(hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        assert await manager.get_python_executable() == str(tmp_path / "venvs" / "bin" / "python")
        await asyncio.wait_for(manager.ensure_pip_ready_for("pip install requests"), timeout=1)
        interpreter = await manager.get_python_executable()

    assert interpreter == sys.executable
    assert spawn.terminated == 1


async def test_discard_cancels_the_pending_build_and_the_next_use_builds_again(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        await let_the_loop_run()
        assert manager.discard() is True
        await let_the_loop_run()
        assert spawn.abandoned == 1
        waiter = asyncio.create_task(manager.ensure_pip_ready_for("pip list"))
        await let_the_loop_run()
        assert len(spawn.creations) == 2
        spawn.release_build.set()
        await asyncio.wait_for(waiter, timeout=1)
        interpreter = await manager.get_python_executable()

    assert interpreter == str(tmp_path / "venvs" / "bin" / "python")
    assert (tmp_path / "venvs" / "bin" / "pip").exists()


async def test_an_existing_venv_is_used_as_it_is(tmp_path: Path) -> None:
    venv = tmp_path / "venvs"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").touch()
    spawn = FakeVenvSpawn()
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        interpreter = await manager.get_python_executable()
        await asyncio.wait_for(manager.ensure_pip_ready_for("pip install requests"), timeout=1)

    assert interpreter == str(venv / "bin" / "python")
    assert spawn.calls == []
    assert not (venv / "bin" / "pip").exists()


async def test_without_auto_create_there_is_no_venv_and_nothing_to_wait_for(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn()
    manager = make_manager(tmp_path, auto_create=False)

    with patch(VENV_SPAWN, side_effect=spawn):
        interpreter = await manager.get_python_executable()
        await asyncio.wait_for(manager.ensure_pip_ready_for("pip install requests"), timeout=1)

    assert interpreter == sys.executable
    assert spawn.calls == []
