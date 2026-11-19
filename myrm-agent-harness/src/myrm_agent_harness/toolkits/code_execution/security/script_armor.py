"""Script armor — every command of a POSIX shell session runs from a script file.

[INPUT]
utils.scratch_dir::ensure_scratch_dir, scratch_dir (POS: The harness's own directories inside a workspace, hidden from git)

[OUTPUT]
- prepare_armored_command: Context manager that writes a command to a 0700 script and yields the shell line that runs it; the script is removed on exit
- sweep_stale_materialized_scripts: Removes the stale scripts a killed process left in a workspace

[POS]
Execution security armor: every POSIX command runs from a script file in the workspace. A command typed straight into
the persistent shell can swallow the markers that delimit its output (an open heredoc or quote), end the shell
(``exit``, ``exec``) or change its state; run as ``bash <script>`` it can do none of that. Windows shells take the
command as it is. The scripts live in the workspace's ``.myrm/exec`` directory, which git ignores, so a commit never
picks one up. A script that cannot be written fails the command: it is never run unarmored.
"""

from __future__ import annotations

import contextlib
import os
import shlex
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

from myrm_agent_harness.toolkits.code_execution.utils.scratch_dir import ensure_scratch_dir, scratch_dir

_SCRIPT_DIR_NAME = "exec"
_SCRIPT_PREFIX = ".myrm_exec_"


def _write_script(command: str, script_dir: Path) -> Path:
    """Write *command* to a new 0700 script (owner read, write, execute only) in *script_dir* and return its path."""
    script_path = script_dir / f"{_SCRIPT_PREFIX}{uuid.uuid4().hex}.sh"

    # O_EXCL: never write through a symlink or into a file another process put under the name first.
    fd = os.open(script_path, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o700)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as script:
            script.write(command if command.endswith("\n") else command + "\n")
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        script_path.unlink(missing_ok=True)
        raise
    return script_path


@contextlib.contextmanager
def prepare_armored_command(command: str, work_dir: str | Path, is_windows: bool = False) -> Iterator[str]:
    """Yield the shell line that runs *command*: ``bash`` on a script that holds it, or *command* itself on Windows.

    The script is written into the workspace *work_dir* and removed when the block ends, whatever happened in it.
    One that cannot be written raises ``OSError`` before anything is yielded, so the command does not run.
    """
    if is_windows:
        yield command
        return

    script_path = _write_script(command, ensure_scratch_dir(work_dir, _SCRIPT_DIR_NAME))
    try:
        yield f"bash {shlex.quote(str(script_path.resolve()))}"
    finally:
        with contextlib.suppress(OSError):
            script_path.unlink(missing_ok=True)


def sweep_stale_materialized_scripts(work_dir: str | Path, max_age_seconds: float = 3600.0) -> int:
    """Unlink the scripts of the workspace *work_dir* that are older than *max_age_seconds*.

    A session calls this when it starts, to clear what a process that was killed under a command (OOM kill) left
    behind. Returns the number of files removed.
    """
    cleaned = 0
    now = time.time()
    try:
        for path in scratch_dir(work_dir, _SCRIPT_DIR_NAME).glob(f"{_SCRIPT_PREFIX}*.sh"):
            try:
                if (now - path.stat().st_mtime) > max_age_seconds:
                    path.unlink(missing_ok=True)
                    cleaned += 1
            except OSError:
                continue
    except OSError:
        pass
    return cleaned
