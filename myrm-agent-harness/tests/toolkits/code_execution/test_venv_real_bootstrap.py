"""The shared venv with real subprocesses: ``python -m venv`` (which runs ``ensurepip``) and bash, all offline.

The fakes of test_venv_pip_bootstrap.py cannot show what a real venv command does when its parent exits first, or what a real
shell runs for ``pip``; these tests can.
"""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import sys
import textwrap
import time
import zipfile
from pathlib import Path

import pytest

import myrm_agent_harness
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext

pytest.importorskip("ensurepip")
pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(sys.platform == "win32", reason="the shared venv layout (bin/) and the bash tool are POSIX"),
]

PIP_WAIT_SECONDS = 120

EXITS_WHILE_PIP_INSTALLS = textwrap.dedent(
    """
    import asyncio
    import os
    import sys

    from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
    from myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager import VenvManager


    async def main(venv: str, exit_at_once: bool) -> None:
        config = ExecutionConfig()
        config.local.shared_venv_path = venv
        await VenvManager(config).get_python_executable()
        if exit_at_once:
            os._exit(0)  # no loop shutdown, no cleanup: what a killed process leaves behind
        await asyncio.sleep(0.3)  # the build is still installing pip when the loop shuts down


    asyncio.run(main(sys.argv[1], sys.argv[2] == "at_once"))
    """
)


def _offline_wheel(directory: Path) -> None:
    """A pure-Python wheel with a valid RECORD, so a real pip installs it without a network."""
    name, version = "demo_pkg", "1.0"
    files = {
        f"{name}/__init__.py": b"VALUE = 1\n",
        f"{name}-{version}.dist-info/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode(),
        f"{name}-{version}.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = f"{name}-{version}.dist-info/RECORD"
    lines = [
        f"{path},sha256={base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()},{len(data)}"
        for path, data in files.items()
    ]
    files[record] = ("\n".join([*lines, f"{record},,"]) + "\n").encode()
    directory.mkdir(parents=True)
    with zipfile.ZipFile(directory / f"{name}-{version}-py3-none-any.whl", "w") as archive:
        for path, data in files.items():
            archive.writestr(path, data)


def _imports(python: str, module: str) -> bool:
    return subprocess.run([python, "-c", f"import {module}"], capture_output=True, check=False).returncode == 0


@pytest.mark.parametrize("exit_mode", ["at_once", "after_a_moment"])
def test_pip_arrives_even_when_the_process_that_started_the_build_exits_first(tmp_path: Path, exit_mode: str) -> None:
    venv = tmp_path / "venvs"
    source = Path(myrm_agent_harness.__file__).parents[1]

    subprocess.run(
        [sys.executable, "-c", EXITS_WHILE_PIP_INSTALLS, str(venv), exit_mode],
        env={**os.environ, "PYTHONPATH": str(source)},
        check=True,
        timeout=PIP_WAIT_SECONDS,
    )

    pip = venv / "bin" / "pip"
    deadline = time.monotonic() + PIP_WAIT_SECONDS
    while not pip.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert pip.exists()


async def test_a_command_naming_pip_waits_for_the_venv_pip_and_installs_into_the_venv_only(tmp_path: Path) -> None:
    # The venv sits inside the workspace so that the sandbox of the bash tool, which writes only there, can install into it.
    workspace = tmp_path
    wheels = workspace / "wheels"
    _offline_wheel(wheels)
    config = ExecutionConfig()
    config.local.shared_venv_path = str(workspace / "venvs")
    executor = LocalExecutor(config, workspace_path=str(workspace))

    def command(code: str, *, network: bool = False) -> ExecutionContext:
        return ExecutionContext(
            code=code,
            workspace_root=str(workspace),
            work_dir=str(workspace),
            timeout=PIP_WAIT_SECONDS,
            allow_network=network,
        )

    try:
        executor.warm_up()
        version = await executor.execute_bash(command("pip --version"))
        install = await executor.execute_bash(
            command(f"pip install --no-index --find-links {wheels} demo_pkg", network=True)
        )
    finally:
        await executor.close()

    assert version.success, (version.stdout, version.error)
    assert "/venvs/lib/" in (version.stdout or "")
    assert install.success, (install.stdout, install.stderr, install.error)
    assert _imports(str(workspace / "venvs" / "bin" / "python"), "demo_pkg")
    assert not _imports(sys.executable, "demo_pkg")
