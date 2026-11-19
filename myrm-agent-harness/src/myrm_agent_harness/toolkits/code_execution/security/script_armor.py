"""Script armor suite — file-backed subprocess invocation & quote/syntax escaping armor.

[INPUT]
utils.scratch_dir::ensure_scratch_dir, scratch_dir (POS: The harness's own directories inside a workspace, hidden from git)

[OUTPUT]
- ScriptArmorConfig: Dataclass configuring direct execution thresholds
- ArmoredCommandString: String subclass carrying is_armored execution tag
- should_materialize_script: Dual-mode heuristic decision probe
- materialize_script_to_file: Atomic 0700 script file creation in a given directory
- build_file_backed_command: Subshell invocation command formatter
- cleanup_materialized_script: Safe file unlink cleanup
- sweep_stale_materialized_scripts: Removes the stale scripts a killed process left in a workspace
- prepare_armored_command: Context manager wrapping materialization, execution, and cleanup

[POS]
Execution security armor. Protects persistent sessions against beacon swallowing,
exit-statement process deaths, and quote bombs by materializing complex scripts to
0700 files executed via subshells, while preserving the direct execution
fast-path for session state modifiers (cd, export, source). The scripts live in the
workspace's ``.myrm/exec`` directory, which git ignores, so a commit never picks one up.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import os
import re
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

from myrm_agent_harness.toolkits.code_execution.utils.scratch_dir import ensure_scratch_dir, scratch_dir

logger: logging.Logger = logging.getLogger(__name__)

_SCRIPT_DIR_NAME = "exec"
_SCRIPT_PREFIX = ".myrm_exec_"

# Fast-path commands that must execute directly in the parent persistent shell
# to preserve session-level state (directory changes, environment variables).
_PARENT_STATE_PREFIXES: tuple[str, ...] = (
    "cd ",
    "cd\t",
    "pushd ",
    "pushd\t",
    "popd",
    "export ",
    "export\t",
    "unset ",
    "unset\t",
    "source ",
    "source\t",
    ". ",
    ".\t",
)

# Regex to detect heredoc patterns (e.g. <<EOF, <<'EOF', <<-"EOF")
_HEREDOC_PATTERN: re.Pattern[str] = re.compile(r"<<-?\s*['\"]?[A-Za-z0-9_]+['\"]?")

# Regex to detect top-level exit commands that could terminate the parent persistent shell
_EXIT_PATTERN: re.Pattern[str] = re.compile(r"(?:^|[;&|\s])exit(?:\s+[0-9]+)?(?:\s*[;&|]|\s*$)")


@dataclasses.dataclass(frozen=True, slots=True)
class ScriptArmorConfig:
    """Configuration options for script materialization armor."""

    enabled: bool = True
    direct_max_bytes: int = 512
    max_direct_lines: int = 2


class ArmoredCommandString(str):
    """String subclass tagging armored subshell execution status.

    Behaves identically to a normal ``str`` for all operations, but carries an
    ``is_armored: bool`` attribute indicating whether the command was materialized
    to a file-backed subshell.
    """

    is_armored: bool

    def __new__(cls, value: str, is_armored: bool = False) -> ArmoredCommandString:
        obj = super().__new__(cls, value)
        obj.is_armored = is_armored
        return obj


def should_materialize_script(command: str, config: ScriptArmorConfig | None = None) -> bool:
    """Determine whether *command* should be materialized to a file and run in a subshell.

    Returns False (Direct Fast-Path) for:
      - Parent state modifying commands: cd, pushd, popd, export, unset, source, .
      - Simple short single-line commands (e.g. ls, git status, echo $VAR) without heredocs,
        nested exit statements, or unbalanced syntax blocks.

    Returns True (File-Backed Armor) for:
      - Multiline commands (> max_direct_lines)
      - Commands containing heredoc syntax (<<EOF)
      - Commands containing exit statements (which would kill the parent shell)
      - Commands exceeding direct_max_bytes
    """
    if config is None:
        config = ScriptArmorConfig()

    if not config.enabled:
        return False

    stripped: str = command.strip()
    if not stripped:
        return False

    # Check for direct state modifiers first.
    # If the entire command is a single-line parent state modification, keep it in parent shell.
    lines: list[str] = [line for line in stripped.splitlines() if line.strip()]
    if len(lines) <= 1:
        for prefix in _PARENT_STATE_PREFIXES:
            # Single-line state modifications must run directly in the parent shell
            # so environment variables and directory changes persist in the session.
            if stripped.startswith(prefix) or stripped == prefix.strip():
                return False

    # Check line count
    if len(lines) > config.max_direct_lines:
        return True

    # Check byte size
    if len(command.encode("utf-8", errors="replace")) > config.direct_max_bytes:
        return True

    # Check for heredocs (<<EOF or <<'EOF')
    if _HEREDOC_PATTERN.search(command):
        return True

    # Check for exit statements that could kill the persistent parent process
    return bool(_EXIT_PATTERN.search(command))


def materialize_script_to_file(command: str, script_dir: Path) -> Path:
    """Atomically write *command* to a secured executable shell script in the existing *script_dir*.

    File permissions are explicitly set to 0700 (owner read, write, execute only).
    """
    script_path: Path = script_dir / f"{_SCRIPT_PREFIX}{uuid.uuid4().hex}.sh"

    # Use os.open with O_CREAT | O_WRONLY | O_EXCL to prevent symlink attacks and race conditions
    fd: int = os.open(str(script_path), os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o700)
    try:
        content: str = command if command.endswith("\n") else command + "\n"
        with open(fd, "w", encoding="utf-8", closefd=True) as f:
            f.write(content)
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        script_path.unlink(missing_ok=True)
        raise

    return script_path


def build_file_backed_command(script_path: str | Path, shell_bin: str = "bash") -> str:
    """Build the subshell execution command string for *script_path*."""
    resolved_path: str = str(Path(script_path).resolve())
    return f'{shell_bin} "{resolved_path}"'


def cleanup_materialized_script(script_path: str | Path | None) -> None:
    """Safely unlink the temporary script file."""
    if script_path is None:
        return
    with contextlib.suppress(OSError):
        Path(script_path).unlink(missing_ok=True)


def sweep_stale_materialized_scripts(work_dir: str | Path, max_age_seconds: float = 3600.0) -> int:
    """Unlink the scripts of the workspace *work_dir* that are older than *max_age_seconds*.

    A session calls this when it starts, to clear what a process that was killed under a command (OOM kill) left
    behind. Returns the number of files removed.
    """
    cleaned: int = 0
    now: float = time.time()
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


@contextlib.contextmanager
def prepare_armored_command(
    command: str,
    work_dir: str | Path,
    is_windows: bool = False,
    config: ScriptArmorConfig | None = None,
) -> Iterator[str]:
    """Context manager to optionally materialize complex scripts to a temporary file.

    Executes complex scripts via child subshell, while preserving direct parent shell
    execution for directory changes, environment variable exports, and simple short commands.
    Yields an ArmoredCommandString carrying is_armored=True when materialized, False otherwise.
    """
    if is_windows or not should_materialize_script(command, config):
        yield ArmoredCommandString(command, is_armored=False)
        return

    materialized_path: Path | None = None
    try:
        # The script stays in the workspace: a sandbox may give the shell a private /tmp, but it mounts the workspace.
        materialized_path = materialize_script_to_file(command, ensure_scratch_dir(work_dir, _SCRIPT_DIR_NAME))
        yield ArmoredCommandString(build_file_backed_command(materialized_path), is_armored=True)
    except Exception as e:
        logger.warning("Script materialization failed, fallback to direct: %s", e)
        yield ArmoredCommandString(command, is_armored=False)
    finally:
        cleanup_materialized_script(materialized_path)
