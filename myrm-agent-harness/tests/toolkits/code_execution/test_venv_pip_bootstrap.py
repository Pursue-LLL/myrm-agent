"""VenvManager pip bootstrap: the shared venv is created without pip so Python runs start at once, pip installs in the background,
and every command or snippet that names pip waits for it."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager import VenvManager, mentions_pip
from tests.toolkits.code_execution._venv_spawn import VENV_SPAWN, FakeVenvSpawn

NAMING_PIP = (
    "pip install requests",
    "pip3 install requests",
    "cd /tmp && pip install -r requirements.txt",
    "python -m pip install requests",
    "python3 -m pip list",
    "/data/venvs/bin/pip freeze",
    "uv pip install requests",
    "python -m ensurepip",
    "pip3.13 install requests",
    "import subprocess; subprocess.run(['pip', 'install', 'requests'])",
)
NOT_NAMING_PIP = (
    "ls -la",
    "python script.py",
    "echo pipeline",
    "grep -r pipe .",
    "pipx run black",
    "pipenv install",
    "cat mappings.txt",
)


def _manager(tmp_path: Path, *, auto_create: bool = True) -> VenvManager:
    config = ExecutionConfig()
    config.local.shared_venv_path = str(tmp_path / "venvs")
    config.local.auto_create_venv = auto_create
    return VenvManager(config)


async def _let_the_loop_run() -> None:
    await asyncio.sleep(0.05)


@pytest.mark.parametrize("text", NAMING_PIP)
def test_mentions_pip_recognises_every_way_to_name_it(text: str) -> None:
    assert mentions_pip(text)


@pytest.mark.parametrize("text", NOT_NAMING_PIP)
def test_mentions_pip_ignores_words_that_only_contain_it(text: str) -> None:
    assert not mentions_pip(text)


async def test_the_venv_is_created_without_pip(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn()
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        interpreter = await manager.get_python_executable()
        await manager.ensure_pip_ready_for("pip install requests")

    assert interpreter == str(tmp_path / "venvs" / "bin" / "python")
    (creation,) = spawn.creations
    assert creation.argv == (sys.executable, "-m", "venv", "--without-pip", str(tmp_path / "venvs"))


async def test_the_first_python_run_does_not_wait_for_pip(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_bootstrap=True)
    manager = _manager(tmp_path)
    pip = tmp_path / "venvs" / "bin" / "pip"

    with patch(VENV_SPAWN, side_effect=spawn):
        interpreter = await asyncio.wait_for(manager.get_python_executable(), timeout=1)
        assert interpreter == str(tmp_path / "venvs" / "bin" / "python")
        assert not pip.exists()
        spawn.release.set()
        await manager.ensure_pip_ready_for("pip --version")

    assert pip.exists()


async def test_pip_is_installed_by_ensurepip_in_the_venv_without_the_parent_python_paths(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn()
    manager = _manager(tmp_path)
    venv = tmp_path / "venvs"

    with (
        patch(VENV_SPAWN, side_effect=spawn),
        patch.dict(os.environ, {"PYTHONHOME": "/elsewhere", "PYTHONPATH": "/shadow"}),
    ):
        await manager.get_python_executable()
        await manager.ensure_pip_ready_for("pip install requests")

    (bootstrap,) = spawn.bootstraps
    assert bootstrap.argv == (str(venv / "bin" / "python"), "-m", "ensurepip", "--upgrade", "--default-pip")
    assert bootstrap.cwd == str(venv)
    assert bootstrap.env is not None
    assert bootstrap.env["VIRTUAL_ENV"] == str(venv)
    assert "PYTHONHOME" not in bootstrap.env
    assert "PYTHONPATH" not in bootstrap.env


async def test_the_bootstrap_writes_to_a_file_so_it_outlives_a_parent_that_exits_first(tmp_path: Path) -> None:
    """ensurepip prints while it installs; into a pipe nobody reads any more that kills it and leaves the venv without pip."""
    spawn = FakeVenvSpawn()
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        await manager.ensure_pip_ready_for("pip --version")

    (bootstrap,) = spawn.bootstraps
    assert isinstance(bootstrap.stdout, io.BufferedIOBase)
    assert bootstrap.stderr is bootstrap.stdout


@pytest.mark.parametrize("text", NAMING_PIP)
async def test_text_naming_pip_waits_for_the_bootstrap(tmp_path: Path, text: str) -> None:
    spawn = FakeVenvSpawn(hold_bootstrap=True)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        waiter = asyncio.create_task(manager.ensure_pip_ready_for(text))
        await _let_the_loop_run()
        assert not waiter.done()
        spawn.release.set()
        await asyncio.wait_for(waiter, timeout=1)

    assert (tmp_path / "venvs" / "bin" / "pip").exists()


@pytest.mark.parametrize("text", NOT_NAMING_PIP)
async def test_text_not_naming_pip_does_not_wait(tmp_path: Path, text: str) -> None:
    spawn = FakeVenvSpawn(hold_bootstrap=True)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        await asyncio.wait_for(manager.ensure_pip_ready_for(text), timeout=1)
        assert not (tmp_path / "venvs" / "bin" / "pip").exists()
        spawn.release.set()
        await manager.ensure_pip_ready_for("pip --version")


async def test_a_pip_command_arriving_while_the_venv_is_being_created_waits_for_the_creation_and_then_for_pip(
    tmp_path: Path,
) -> None:
    spawn = FakeVenvSpawn(hold_creation=True, hold_bootstrap=True)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        creation = asyncio.create_task(manager.get_python_executable())
        await _let_the_loop_run()
        waiter = asyncio.create_task(manager.ensure_pip_ready_for("pip --version"))
        await _let_the_loop_run()
        spawn.release_creation.set()
        await asyncio.wait_for(creation, timeout=1)
        await _let_the_loop_run()
        assert not waiter.done()
        spawn.release.set()
        await asyncio.wait_for(waiter, timeout=1)

    assert (tmp_path / "venvs" / "bin" / "pip").exists()


async def test_a_pip_command_with_no_venv_yet_creates_it_and_waits_for_pip(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_bootstrap=True)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        waiter = asyncio.create_task(manager.ensure_pip_ready_for("pip list"))
        await _let_the_loop_run()
        assert not waiter.done()
        spawn.release.set()
        await asyncio.wait_for(waiter, timeout=1)

    assert len(spawn.creations) == 1
    assert (tmp_path / "venvs" / "bin" / "pip").exists()


async def test_text_not_naming_pip_never_creates_the_venv(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn()
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.ensure_pip_ready_for("ls -la")

    assert spawn.calls == []


async def test_a_command_not_starting_with_pip_install_waits_for_a_venv_that_is_being_created(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_creation=True, hold_bootstrap=True)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        creation = asyncio.create_task(manager.get_python_executable())
        await _let_the_loop_run()
        rewrite = asyncio.create_task(manager.rewrite_pip_command("pip --version"))
        await _let_the_loop_run()
        spawn.release_creation.set()
        await asyncio.wait_for(creation, timeout=1)
        await _let_the_loop_run()
        assert not rewrite.done()
        spawn.release.set()
        rewritten = await asyncio.wait_for(rewrite, timeout=1)

    assert rewritten == "pip --version"


async def test_pip_install_is_rewritten_to_the_venv_pip_once_it_exists(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_bootstrap=True)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        rewrite = asyncio.create_task(manager.rewrite_pip_command("pip install requests"))
        await _let_the_loop_run()
        assert not rewrite.done()
        spawn.release.set()
        rewritten = await asyncio.wait_for(rewrite, timeout=1)

    assert rewritten == f"{tmp_path / 'venvs' / 'bin' / 'pip'} install requests"


async def test_a_command_naming_pip_later_in_the_line_waits_and_runs_as_typed(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_bootstrap=True)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        rewrite = asyncio.create_task(manager.rewrite_pip_command("cd /tmp && pip install requests"))
        await _let_the_loop_run()
        assert not rewrite.done()
        spawn.release.set()
        rewritten = await asyncio.wait_for(rewrite, timeout=1)

    assert rewritten == "cd /tmp && pip install requests"


async def test_waiters_share_one_creation_and_one_bootstrap(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_bootstrap=True)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await asyncio.gather(*(manager.get_python_executable() for _ in range(3)))
        waiters = [asyncio.create_task(manager.ensure_pip_ready_for("pip list")) for _ in range(4)]
        await _let_the_loop_run()
        spawn.release.set()
        await asyncio.wait_for(asyncio.gather(*waiters), timeout=1)

    assert len(spawn.creations) == 1
    assert len(spawn.bootstraps) == 1


async def test_a_waiter_that_gives_up_leaves_the_bootstrap_running(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_bootstrap=True)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        waiter = asyncio.create_task(manager.ensure_pip_ready_for("pip list"))
        await _let_the_loop_run()
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        spawn.release.set()
        await asyncio.wait_for(manager.ensure_pip_ready_for("pip list"), timeout=1)
        interpreter = await manager.get_python_executable()

    assert (tmp_path / "venvs" / "bin" / "pip").exists()
    assert interpreter == str(tmp_path / "venvs" / "bin" / "python")


async def test_a_failed_bootstrap_falls_back_to_system_python_and_removes_the_venv(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spawn = FakeVenvSpawn(bootstrap_exit=1)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn), caplog.at_level(logging.ERROR):
        assert await manager.get_python_executable() == str(tmp_path / "venvs" / "bin" / "python")
        await manager.ensure_pip_ready_for("pip install requests")
        assert await manager.get_python_executable() == sys.executable
        assert await manager.rewrite_pip_command("pip install requests") == "pip install requests"

    assert not (tmp_path / "venvs").exists()
    assert "ensurepip failed" in caplog.text
    assert len(spawn.creations) == 1


async def test_a_bootstrap_that_cannot_start_falls_back_the_same_way(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    spawn = FakeVenvSpawn(bootstrap_error=OSError("exec format error"))
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn), caplog.at_level(logging.ERROR):
        await manager.get_python_executable()
        await manager.ensure_pip_ready_for("pip install requests")
        assert await manager.get_python_executable() == sys.executable

    assert not (tmp_path / "venvs").exists()
    assert "exec format error" in caplog.text


async def test_a_failed_bootstrap_keeps_a_venv_whose_pip_arrived_meanwhile(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(bootstrap_exit=1)
    manager = _manager(tmp_path)
    venv = tmp_path / "venvs"

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        (venv / "bin" / "pip").touch()
        await manager.ensure_pip_ready_for("pip install requests")
        interpreter = await manager.get_python_executable()

    assert interpreter == str(venv / "bin" / "python")
    assert (venv / "bin" / "pip").exists()


async def test_a_failed_creation_starts_no_bootstrap(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(create_exit=1)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        interpreter = await manager.get_python_executable()
        await asyncio.wait_for(manager.ensure_pip_ready_for("pip install requests"), timeout=1)

    assert interpreter == sys.executable
    assert spawn.bootstraps == []


async def test_discard_cancels_the_pending_bootstrap_and_the_next_use_builds_again(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_bootstrap=True)
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        await _let_the_loop_run()
        assert manager.discard() is True
        await _let_the_loop_run()
        assert spawn.cancelled_bootstraps == 1
        waiter = asyncio.create_task(manager.ensure_pip_ready_for("pip list"))
        await _let_the_loop_run()
        assert len(spawn.creations) == 2
        spawn.release.set()
        await asyncio.wait_for(waiter, timeout=1)
        interpreter = await manager.get_python_executable()

    assert interpreter == str(tmp_path / "venvs" / "bin" / "python")
    assert len(spawn.creations) == 2
    assert len(spawn.bootstraps) == 2
    assert (tmp_path / "venvs" / "bin" / "pip").exists()


async def test_an_existing_venv_is_used_as_it_is(tmp_path: Path) -> None:
    venv = tmp_path / "venvs"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").touch()
    spawn = FakeVenvSpawn()
    manager = _manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        interpreter = await manager.get_python_executable()
        await asyncio.wait_for(manager.ensure_pip_ready_for("pip install requests"), timeout=1)

    assert interpreter == str(venv / "bin" / "python")
    assert spawn.calls == []
    assert not (venv / "bin" / "pip").exists()


async def test_without_auto_create_there_is_no_venv_and_nothing_to_wait_for(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn()
    manager = _manager(tmp_path, auto_create=False)

    with patch(VENV_SPAWN, side_effect=spawn):
        interpreter = await manager.get_python_executable()
        await asyncio.wait_for(manager.ensure_pip_ready_for("pip install requests"), timeout=1)

    assert interpreter == sys.executable
    assert spawn.calls == []
