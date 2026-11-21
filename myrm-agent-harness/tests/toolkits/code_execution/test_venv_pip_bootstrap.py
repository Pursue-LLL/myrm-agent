"""VenvManager background pip: ``python -m venv`` links the interpreter first and installs pip afterwards, so the manager hands the interpreter out
as soon as it is linked, lets the command finish in the background, and makes every command or snippet that names pip wait for it."""

from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager import mentions_pip
from tests.toolkits.code_execution._venv_spawn import VENV_SPAWN, FakeVenvSpawn, let_the_loop_run, make_manager

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


@pytest.mark.parametrize("text", NAMING_PIP)
def test_mentions_pip_recognises_every_way_to_name_it(text: str) -> None:
    assert mentions_pip(text)


@pytest.mark.parametrize("text", NOT_NAMING_PIP)
def test_mentions_pip_ignores_words_that_only_contain_it(text: str) -> None:
    assert not mentions_pip(text)


async def test_the_venv_is_built_by_the_stdlib_command_with_pip_and_its_output_goes_to_a_file(tmp_path: Path) -> None:
    """The stdlib command runs ensurepip itself, so it finishes on its own when this process exits first; a pipe nobody reads kills it."""
    spawn = FakeVenvSpawn()
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        interpreter = await manager.get_python_executable()
        await manager.ensure_pip_ready_for("pip install requests")

    assert interpreter == str(tmp_path / "venvs" / "bin" / "python")
    (build,) = spawn.creations
    assert build.argv == (sys.executable, "-m", "venv", str(tmp_path / "venvs"))
    assert isinstance(build.stdout, io.BufferedIOBase)
    assert build.stderr is build.stdout


async def test_the_first_python_run_does_not_wait_for_pip(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_build=True)
    manager = make_manager(tmp_path)
    pip = tmp_path / "venvs" / "bin" / "pip"

    with patch(VENV_SPAWN, side_effect=spawn):
        interpreter = await asyncio.wait_for(manager.get_python_executable(), timeout=1)
        assert interpreter == str(tmp_path / "venvs" / "bin" / "python")
        assert not pip.exists()
        spawn.release_build.set()
        await manager.ensure_pip_ready_for("pip --version")

    assert pip.exists()


async def test_the_interpreter_is_handed_out_only_once_python3_is_linked_too(tmp_path: Path) -> None:
    """Agents run ``python3``; the PATH of a shell started now must find it in the venv."""
    spawn = FakeVenvSpawn(hold_aliases=True, hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        creation = asyncio.create_task(manager.get_python_executable())
        await let_the_loop_run()
        assert (tmp_path / "venvs" / "bin" / "python").is_symlink()
        assert not creation.done()
        spawn.release_aliases.set()
        interpreter = await asyncio.wait_for(creation, timeout=1)

    assert interpreter == str(tmp_path / "venvs" / "bin" / "python")


async def test_a_venv_whose_interpreter_is_copied_not_linked_is_handed_out_when_the_build_is_over(
    tmp_path: Path,
) -> None:
    """A copy appears before it is complete, so only the end of the command says it can run."""
    spawn = FakeVenvSpawn(copies=True, hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        creation = asyncio.create_task(manager.get_python_executable())
        await let_the_loop_run()
        assert not creation.done()
        spawn.release_build.set()
        interpreter = await asyncio.wait_for(creation, timeout=1)

    assert interpreter == str(tmp_path / "venvs" / "bin" / "python")
    assert (tmp_path / "venvs" / "bin" / "pip").exists()


@pytest.mark.parametrize("text", NAMING_PIP)
async def test_text_naming_pip_waits_for_the_build(tmp_path: Path, text: str) -> None:
    spawn = FakeVenvSpawn(hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        waiter = asyncio.create_task(manager.ensure_pip_ready_for(text))
        await let_the_loop_run()
        assert not waiter.done()
        spawn.release_build.set()
        await asyncio.wait_for(waiter, timeout=1)

    assert (tmp_path / "venvs" / "bin" / "pip").exists()


@pytest.mark.parametrize("text", NOT_NAMING_PIP)
async def test_text_not_naming_pip_does_not_wait(tmp_path: Path, text: str) -> None:
    spawn = FakeVenvSpawn(hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        await asyncio.wait_for(manager.ensure_pip_ready_for(text), timeout=1)
        assert not (tmp_path / "venvs" / "bin" / "pip").exists()
        spawn.release_build.set()
        await manager.ensure_pip_ready_for("pip --version")


async def test_a_pip_command_arriving_before_the_interpreter_is_linked_waits_for_the_link_and_then_for_pip(
    tmp_path: Path,
) -> None:
    spawn = FakeVenvSpawn(hold_links=True, hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        creation = asyncio.create_task(manager.get_python_executable())
        await let_the_loop_run()
        waiter = asyncio.create_task(manager.ensure_pip_ready_for("pip --version"))
        await let_the_loop_run()
        spawn.release_links.set()
        await asyncio.wait_for(creation, timeout=1)
        await let_the_loop_run()
        assert not waiter.done()
        spawn.release_build.set()
        await asyncio.wait_for(waiter, timeout=1)

    assert (tmp_path / "venvs" / "bin" / "pip").exists()


async def test_a_pip_command_with_no_venv_yet_creates_it_and_waits_for_pip(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        waiter = asyncio.create_task(manager.ensure_pip_ready_for("pip list"))
        await let_the_loop_run()
        assert not waiter.done()
        spawn.release_build.set()
        await asyncio.wait_for(waiter, timeout=1)

    assert len(spawn.creations) == 1
    assert (tmp_path / "venvs" / "bin" / "pip").exists()


async def test_text_not_naming_pip_never_creates_the_venv(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn()
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.ensure_pip_ready_for("ls -la")

    assert spawn.calls == []


async def test_a_command_not_starting_with_pip_install_waits_for_a_venv_that_is_being_built(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_links=True, hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        creation = asyncio.create_task(manager.get_python_executable())
        await let_the_loop_run()
        rewrite = asyncio.create_task(manager.rewrite_pip_command("pip --version"))
        await let_the_loop_run()
        spawn.release_links.set()
        await asyncio.wait_for(creation, timeout=1)
        await let_the_loop_run()
        assert not rewrite.done()
        spawn.release_build.set()
        rewritten = await asyncio.wait_for(rewrite, timeout=1)

    assert rewritten == "pip --version"


async def test_pip_install_is_rewritten_to_the_venv_pip_once_it_exists(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        rewrite = asyncio.create_task(manager.rewrite_pip_command("pip install requests"))
        await let_the_loop_run()
        assert not rewrite.done()
        spawn.release_build.set()
        rewritten = await asyncio.wait_for(rewrite, timeout=1)

    assert rewritten == f"{tmp_path / 'venvs' / 'bin' / 'pip'} install requests"


async def test_a_command_naming_pip_later_in_the_line_waits_and_runs_as_typed(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        rewrite = asyncio.create_task(manager.rewrite_pip_command("cd /tmp && pip install requests"))
        await let_the_loop_run()
        assert not rewrite.done()
        spawn.release_build.set()
        rewritten = await asyncio.wait_for(rewrite, timeout=1)

    assert rewritten == "cd /tmp && pip install requests"


async def test_waiters_share_one_build(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await asyncio.gather(*(manager.get_python_executable() for _ in range(3)))
        waiters = [asyncio.create_task(manager.ensure_pip_ready_for("pip list")) for _ in range(4)]
        await let_the_loop_run()
        spawn.release_build.set()
        await asyncio.wait_for(asyncio.gather(*waiters), timeout=1)

    assert len(spawn.creations) == 1


async def test_a_waiter_that_gives_up_leaves_the_build_running(tmp_path: Path) -> None:
    spawn = FakeVenvSpawn(hold_build=True)
    manager = make_manager(tmp_path)

    with patch(VENV_SPAWN, side_effect=spawn):
        await manager.get_python_executable()
        waiter = asyncio.create_task(manager.ensure_pip_ready_for("pip list"))
        await let_the_loop_run()
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        spawn.release_build.set()
        await asyncio.wait_for(manager.ensure_pip_ready_for("pip list"), timeout=1)
        interpreter = await manager.get_python_executable()

    assert (tmp_path / "venvs" / "bin" / "pip").exists()
    assert interpreter == str(tmp_path / "venvs" / "bin" / "python")
    assert spawn.abandoned == 0
