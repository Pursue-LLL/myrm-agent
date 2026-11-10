"""Process start-up leaves the bytecode caches alone.

[INPUT]
- app.startup.env_loader (POS: environment initialisation that runs first on every launch)

[OUTPUT]
- Coverage of the premise (CPython never runs a stale .pyc) and the guard (start-up deletes no cache)

[POS]
Startup tests. Wiping `app/**/__pycache__` on every launch forces ~2,000 modules to be compiled again (about 1.4 s
before the first request is answered) and protects against nothing: the import system compares each .pyc with the
modification time and size of its source and recompiles on a mismatch.
"""

from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

from app.startup import env_loader

_IMPORT_VALUE = "import sys; sys.path.insert(0, sys.argv[1]); import cached_module; print(cached_module.VALUE)"


def _import_cached_module(directory: Path) -> str:
    return subprocess.run(
        [sys.executable, "-c", _IMPORT_VALUE, str(directory)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()


def test_a_stale_bytecode_cache_never_shadows_changed_source(tmp_path: Path) -> None:
    """The premise: with the source's modification time unchanged, a different size still forces a recompile."""
    source = tmp_path / "cached_module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    assert _import_cached_module(tmp_path) == "1"
    assert list((tmp_path / "__pycache__").glob("cached_module.*.pyc"))
    stamp = source.stat()

    source.write_text("VALUE = 22\n", encoding="utf-8")
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    assert _import_cached_module(tmp_path) == "22"


def test_environment_initialisation_deletes_no_bytecode_cache() -> None:
    """The guard: no `rmtree` (or a call that wraps it) on the start-up path."""
    tree = ast.parse(inspect.getsource(env_loader))
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    referenced |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    assert "rmtree" not in referenced
    assert not hasattr(env_loader, "clean_pycache")
