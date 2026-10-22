"""Importing the app must not open any database the archive carries.

The pre-boot swap replaces carried databases before ``init_database`` runs; a module that opened one at
import time would hold the pre-swap file open. Databases opened at import must all be runtime-only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from app.services.instance_archive.policy import PathCategory, classify_path

_SERVER_ROOT = Path(__file__).resolve().parents[3]
_HARNESS_SRC = _SERVER_ROOT.parent.parent / "myrm-agent-harness" / "src"

_SPY = textwrap.dedent(
    """
    import json, sqlite3
    opened = []
    _connect = sqlite3.connect
    def spy(database, *a, **k):
        opened.append(str(database))
        return _connect(database, *a, **k)
    sqlite3.connect = spy
    try:
        import aiosqlite
        _aio = aiosqlite.connect
        def aio_spy(database, *a, **k):
            opened.append(str(database))
            return _aio(database, *a, **k)
        aiosqlite.connect = aio_spy
    except ImportError:
        pass
    import app.main  # noqa: F401
    print("OPENED=" + json.dumps(opened))
    """
)


def test_databases_opened_at_import_are_runtime_only(tmp_path: Path) -> None:
    state = (tmp_path / "state").resolve()
    state.mkdir()
    env = {
        **os.environ,
        "MYRM_DATA_DIR": str(state),
        "PYTHONPATH": os.pathsep.join([str(_HARNESS_SRC), str(_SERVER_ROOT)]),
    }

    result = subprocess.run(
        [sys.executable, "-c", _SPY], cwd=_SERVER_ROOT, env=env, capture_output=True, text=True, timeout=240, check=False
    )

    assert result.returncode == 0, result.stderr[-2000:]
    line = next(entry for entry in result.stdout.splitlines() if entry.startswith("OPENED="))
    opened = json.loads(line.removeprefix("OPENED="))
    inside_state = [Path(d) for d in opened if Path(d).is_relative_to(state)]
    assert inside_state, f"the spy saw no state-dir database at import: {opened}"
    for path in inside_state:
        decision = classify_path(path.relative_to(state).parts)
        assert decision.category is not PathCategory.DATA, f"{path} is opened at import but would be carried"
