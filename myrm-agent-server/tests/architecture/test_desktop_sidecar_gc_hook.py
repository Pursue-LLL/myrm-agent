"""The sidecar starts with the cycle collector paused, and the server settles it once start-up is done.

The sidecar entry imports the whole server before uvicorn runs, and the full collections during that import add
about a second to the time before the first request is answered. The runtime hook pauses the collector first;
``app.startup.gc_policy`` freezes the surviving heap and turns collection back on. Each test starts a fresh
interpreter, the way the packaged executable starts one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.support.desktop_release import sidecar_build_module

_SERVER_ROOT = Path(__file__).resolve().parents[2]

_HOOK_THEN_REPORT = """
import gc
import runpy
import sys

runpy.run_path(sys.argv[1])
print(gc.isenabled())
"""

_HOOK_THEN_SETTLE = """
import gc
import runpy
import sys

runpy.run_path(sys.argv[1])
from app.startup.gc_policy import settle_collection

settle_collection()
print(gc.isenabled(), gc.get_freeze_count() > 0)
"""


@pytest.fixture(scope="module")
def build_module() -> ModuleType:
    return sidecar_build_module()


def _run(script: str, hook: Path) -> str:
    completed = subprocess.run(
        [sys.executable, "-c", script, str(hook)],
        cwd=_SERVER_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return completed.stdout.strip()


def test_the_hook_pauses_the_collector(build_module: ModuleType) -> None:
    assert _run(_HOOK_THEN_REPORT, build_module.GC_RUNTIME_HOOK) == "False"


def test_settling_after_the_hook_freezes_the_heap_and_resumes_collection(build_module: ModuleType) -> None:
    assert _run(_HOOK_THEN_SETTLE, build_module.GC_RUNTIME_HOOK) == "True True"


def test_the_sidecar_build_registers_the_hook_after_the_stdio_hook(build_module: ModuleType) -> None:
    cmd = build_module.pyinstaller_command(Path("python"), Path("work"))

    hooks = [cmd[index + 1] for index, argument in enumerate(cmd) if argument == "--runtime-hook"]

    assert hooks == [str(build_module.STDIO_RUNTIME_HOOK), str(build_module.GC_RUNTIME_HOOK)]
    assert build_module.GC_RUNTIME_HOOK.is_file()
