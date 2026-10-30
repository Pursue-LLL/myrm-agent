"""Modules that guard a POSIX-only stdlib import still import where that module is missing, as on Windows."""

from __future__ import annotations

import subprocess
import sys

import pytest

# `sys.modules[name] = None` makes `import <name>` raise ImportError, the way a missing stdlib module does.
_IMPORT_WITHOUT_POSIX_MODULES = """
import importlib
import sys

for name in ("resource", "pty"):
    sys.modules[name] = None
importlib.import_module(sys.argv[1])
"""


@pytest.mark.parametrize(
    "module",
    [
        "myrm_agent_harness.observability.diagnostics.system_exhaustion",
        "myrm_agent_harness.runtime.survival.desktop_memory_watchdog",
        "myrm_agent_harness.toolkits.code_execution.executors.local._background_pty_spawn",
    ],
)
def test_module_imports_without_the_posix_only_modules(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_WITHOUT_POSIX_MODULES, module],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr[-2000:]
