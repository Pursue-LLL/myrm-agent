"""The packaged backend runs the agent's browser scripts in the Monty worker that the bundle carries.

Each script of ``browser_execute_script_tool`` runs in a worker executable of the Monty interpreter. The client looks
for it in the environment's scripts directory and on PATH, and a frozen app has neither. The runtime hook names the
bundled copy through ``MONTY_BIN`` before the entry imports the server; the build puts the worker in the folder the
hook reads, and the verifier refuses a bundle without it.
"""

from __future__ import annotations

import os
import runpy
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.support.desktop_release import sidecar_build_module, sidecar_module


@pytest.fixture(scope="module")
def build() -> ModuleType:
    return sidecar_build_module()


@pytest.fixture(scope="module")
def inventory() -> ModuleType:
    return sidecar_module("bundle_inventory")


def _bundle_data_dir(tmp_path: Path, inventory: ModuleType, *, with_worker: bool) -> Path:
    """What `sys._MEIPASS` is in a one-folder bundle: the directory that holds the collected data and binaries."""
    internal = tmp_path / "_internal"
    internal.mkdir()
    if with_worker:
        worker = internal / inventory.MONTY_WORKER_DIR / inventory.monty_worker_name()
        worker.parent.mkdir()
        worker.write_text("", encoding="utf-8")
    return internal


def test_the_hook_names_the_bundled_worker_whatever_the_environment_says(
    build: ModuleType, inventory: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    internal = _bundle_data_dir(tmp_path, inventory, with_worker=True)
    monkeypatch.setattr(sys, "_MEIPASS", str(internal), raising=False)
    monkeypatch.setenv("MONTY_BIN", "/somewhere/else/monty")

    runpy.run_path(str(build.MONTY_RUNTIME_HOOK))

    expected = internal / inventory.MONTY_WORKER_DIR / inventory.monty_worker_name()
    assert os.environ["MONTY_BIN"] == str(expected), "the sandbox that runs model-written code must be the shipped one"


def test_the_hook_leaves_the_environment_alone_when_the_bundle_has_no_worker(
    build: ModuleType, inventory: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    internal = _bundle_data_dir(tmp_path, inventory, with_worker=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(internal), raising=False)
    monkeypatch.setenv("MONTY_BIN", "/somewhere/else/monty")

    runpy.run_path(str(build.MONTY_RUNTIME_HOOK))

    assert os.environ["MONTY_BIN"] == "/somewhere/else/monty"


def test_the_client_starts_the_worker_the_hook_names(
    build: ModuleType, inventory: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The variable the hook sets is the one the client reads, not just one with a similar name."""
    from pydantic_monty._binary import find_monty_binary

    internal = _bundle_data_dir(tmp_path, inventory, with_worker=True)
    monkeypatch.setattr(sys, "_MEIPASS", str(internal), raising=False)
    # Set first, so that the variable the hook assigns is restored when the test ends.
    monkeypatch.setenv("MONTY_BIN", "")

    runpy.run_path(str(build.MONTY_RUNTIME_HOOK))

    assert find_monty_binary() == str(internal / inventory.MONTY_WORKER_DIR / inventory.monty_worker_name())


def test_the_command_ships_the_worker_the_client_and_the_hook_in_order(build: ModuleType, inventory: ModuleType) -> None:
    worker = Path("/venv/bin") / inventory.monty_worker_name()
    sep = ";" if build.SYSTEM == "windows" else ":"

    cmd = build.pyinstaller_command(Path("python"), Path("work"), monty_worker=worker)

    options = set(zip(cmd, cmd[1:], strict=False))
    assert ("--add-binary", f"{worker}{sep}{inventory.MONTY_WORKER_DIR}") in options
    assert ("--collect-submodules", inventory.MONTY_PACKAGE) in options
    hooks = [cmd[index + 1] for index, argument in enumerate(cmd) if argument == "--runtime-hook"]
    assert hooks == [str(build.STDIO_RUNTIME_HOOK), str(build.GC_RUNTIME_HOOK), str(build.MONTY_RUNTIME_HOOK)]
    assert build.MONTY_RUNTIME_HOOK.is_file()


def _interpreter_with_scripts_dir(tmp_path: Path, scripts: Path) -> Path:
    """A stand-in for the build's Python that answers `sysconfig.get_path('scripts')` with `scripts`."""
    python = tmp_path / "python"
    python.write_text(f"#!/bin/sh\necho '{scripts}'\n", encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)
    return python


@pytest.mark.skipif(os.name == "nt", reason="the stand-in interpreter is a shell script")
def test_the_build_finds_the_worker_in_the_scripts_directory_of_its_own_python(inventory: ModuleType, tmp_path: Path) -> None:
    scripts = tmp_path / "venv" / "bin"
    scripts.mkdir(parents=True)
    worker = scripts / inventory.monty_worker_name()
    worker.write_text("", encoding="utf-8")

    assert inventory.installed_monty_worker(_interpreter_with_scripts_dir(tmp_path, scripts)) == worker


@pytest.mark.skipif(os.name == "nt", reason="the stand-in interpreter is a shell script")
def test_a_build_environment_without_the_worker_fails_before_pyinstaller_runs(inventory: ModuleType, tmp_path: Path) -> None:
    scripts = tmp_path / "venv" / "bin"
    scripts.mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="Monty worker is not installed"):
        inventory.installed_monty_worker(_interpreter_with_scripts_dir(tmp_path, scripts))
