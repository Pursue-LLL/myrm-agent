"""Desktop sidecar PATH hydration.

[INPUT]
- os.environ::MYRM_SHELL_PID (POS: injected only by the Tauri shell; gates the whole module)
- the user's login shell (POS: source of the PATH their terminal would have)

[OUTPUT]
- hydrate_desktop_path: merge the login-shell PATH and common tool directories into os.environ["PATH"]

[POS]
A GUI-launched macOS app inherits launchd's minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin), so tools the user
installed with Homebrew, nvm or cargo are invisible to the agent's bash tool and to skill `requires.bins`
checks. The desktop sidecar recovers the PATH once at startup, the same way terminal-integrated editors do.
Only PATH is touched; credentials and other variables are never imported from the shell.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

SHELL_PID_ENV = "MYRM_SHELL_PID"

_PROBE_TIMEOUT_SECONDS = 5.0
_START_MARKER = "__MYRM_PATH_START__"
_END_MARKER = "__MYRM_PATH_END__"
# Fill-in directories for users whose shell rc files do not export them; appended last so they only fill gaps.
_SEED_DIRS = ("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin", "~/.local/bin", "~/.cargo/bin")


def _spawned_by_desktop_shell() -> bool:
    return sys.platform != "win32" and bool(os.environ.get(SHELL_PID_ENV))


def _resolve_login_shell(account_shell: str) -> str | None:
    for candidate in (os.environ.get("SHELL"), account_shell):
        if candidate and os.path.isabs(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _parse_probe_output(raw: bytes) -> list[str]:
    """Extract absolute PATH entries between the markers, ignoring any rc-file noise around them."""
    text = raw.decode("utf-8", errors="replace")
    start = text.find(_START_MARKER)
    end = text.find(_END_MARKER, start + len(_START_MARKER)) if start >= 0 else -1
    if start < 0 or end < 0:
        return []
    value = text[start + len(_START_MARKER) : end]
    return [entry for entry in value.split(os.pathsep) if os.path.isabs(entry)]


def _probe_login_shell_path() -> list[str]:
    """Ask the user's interactive login shell for PATH.

    Interactive + login mirrors what VS Code and Cursor do, because many users export PATH from ~/.zshrc rather
    than ~/.zprofile. The shell gets no stdin, its own session (so it cannot grab a terminal) and a hard deadline;
    on timeout the whole process group is killed, but any PATH already printed is still used. Output goes to an
    anonymous file instead of a pipe: a daemon started by an rc file would inherit a pipe and keep it open, making
    the read wait on a shell that has already exited.
    """
    import pwd  # POSIX-only; imported lazily so this module stays importable on Windows

    try:
        account = pwd.getpwuid(os.getuid())
    except KeyError:
        return []
    shell = _resolve_login_shell(account.pw_shell)
    if shell is None:
        return []

    env = {key: value for key, value in os.environ.items() if key != "ZDOTDIR"}
    env["HOME"] = account.pw_dir
    # Markers are separate printf arguments: glued to `$PATH` the shell would read them as part of the name.
    script = f"printf '%s%s%s' {_START_MARKER} \"$PATH\" {_END_MARKER}"
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen(
                [shell, "-i", "-l", "-c", script],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            logger.warning("[Startup] Login shell PATH probe could not start: %s", exc)
            return []

        try:
            process.wait(timeout=_PROBE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            logger.warning("[Startup] Login shell PATH probe timed out after %.0fs", _PROBE_TIMEOUT_SECONDS)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        output.seek(0)
        return _parse_probe_output(output.read())


def _existing_seed_dirs() -> list[str]:
    expanded = (str(Path(seed).expanduser()) for seed in _SEED_DIRS)
    return [seed for seed in expanded if os.path.isdir(seed)]


def _merge_entries(*groups: Iterable[str]) -> list[str]:
    """Concatenate PATH groups, dropping empty entries (they mean the working directory) and duplicates."""
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for entry in group:
            if entry and entry not in seen:
                seen.add(entry)
                merged.append(entry)
    return merged


def hydrate_desktop_path() -> list[str]:
    """Merge the user's shell PATH into this process; returns the entries that were newly added.

    No-op unless launched by the desktop shell on a POSIX platform. Entries from the login shell come first so the
    user's own toolchain order wins over the system stubs in /usr/bin; the inherited PATH and the seed directories
    follow, so a failed probe still leaves the app strictly better off than the bare launchd PATH.
    """
    if not _spawned_by_desktop_shell():
        return []

    current = os.environ.get("PATH", "").split(os.pathsep)
    merged = _merge_entries(_probe_login_shell_path(), current, _existing_seed_dirs())
    added = [entry for entry in merged if entry not in current]
    os.environ["PATH"] = os.pathsep.join(merged)
    logger.info("[Startup] Desktop PATH hydrated: %d entries added", len(added))
    return added
