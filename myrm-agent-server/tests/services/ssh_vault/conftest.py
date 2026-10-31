"""Fixtures for the SSH vault tests: a program named `ssh` that stands in for the remote host.

[INPUT]
- pytest::MonkeyPatch, TempPathFactory fixtures
- contextlib, json, os, signal, sys, textwrap, collections.abc, dataclasses, pathlib

[OUTPUT]
- StandInSsh: The `ssh` program placed first on PATH, and what it should do on the next call.
- stand_in_ssh: Fixture that installs it for one test and kills a process it left running.

[POS]
Fixtures for tests in tests/services/ssh_vault/. `SSHAssetService` starts `ssh` as a real child process, so the tests
let it start a real one that never connects anywhere.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import sys
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

_SCRIPT = textwrap.dedent(
    """\
    #!{python}
    import json, os, sys, time

    behaviour = json.load(open({config!r}))
    open({pid_file!r}, "w").write(str(os.getpid()))
    mode = behaviour["mode"]
    if mode == "print":
        sys.stdout.write(behaviour["stdout"])
        sys.stdout.flush()
        sys.stderr.write(behaviour["stderr"])
        sys.stderr.flush()
        sys.exit(behaviour["exit_code"])
    if mode == "flood":
        stream = sys.stderr if behaviour["pipe"] == "stderr" else sys.stdout
        line = "x" * 1023 + "\\n"
        while True:
            stream.write(line)
    if mode == "hold":
        time.sleep(4711)
    """
)


@dataclass(frozen=True)
class StandInSsh:
    """The `ssh` program on PATH for one test. It never connects; it does what `behave_*` last said."""

    _config: Path
    _pid_file: Path

    def print_and_exit(self, *, stdout: str = "", stderr: str = "", exit_code: int = 0) -> None:
        """Write `stdout` and `stderr`, then exit with `exit_code`."""
        self._config.write_text(
            json.dumps({"mode": "print", "stdout": stdout, "stderr": stderr, "exit_code": exit_code}),
            encoding="utf-8",
        )

    def flood(self, pipe: str) -> None:
        """Write to `pipe` ("stdout" or "stderr") without end."""
        self._config.write_text(json.dumps({"mode": "flood", "pipe": pipe}), encoding="utf-8")

    def hold(self) -> None:
        """Stay silent and alive."""
        self._config.write_text(json.dumps({"mode": "hold"}), encoding="utf-8")

    def is_gone(self) -> bool:
        """True once the process of the last call no longer exists (a zombie counts as existing)."""
        pid = int(self._pid_file.read_text(encoding="utf-8"))
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False

    def was_started(self) -> bool:
        return self._pid_file.exists()

    def kill_leftover(self) -> None:
        """Stop the process of the last call if a failing test left it running."""
        if self.was_started() and not self.is_gone():
            with contextlib.suppress(ProcessLookupError):
                os.kill(int(self._pid_file.read_text(encoding="utf-8")), signal.SIGKILL)


@pytest.fixture
def stand_in_ssh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[StandInSsh]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    config = tmp_path / "behaviour.json"
    pid_file = tmp_path / "ssh.pid"
    script = bin_dir / "ssh"
    script.write_text(_SCRIPT.format(python=sys.executable, config=str(config), pid_file=str(pid_file)), encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    stand_in = StandInSsh(config, pid_file)
    stand_in.print_and_exit()
    yield stand_in
    stand_in.kill_leftover()
