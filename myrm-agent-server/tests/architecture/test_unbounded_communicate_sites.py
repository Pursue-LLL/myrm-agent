"""Every ``Process.communicate()`` call in the server is either replaced by ``communicate_bounded`` or accounted for here.

``communicate()`` keeps everything the child writes and, called alone, waits without a deadline. A command whose output
the server does not control (anything that runs text from a user, a model or a job definition) can therefore grow the
process's memory or hold a request for as long as it likes. A new call must be a conscious decision: use the harness's
``communicate_bounded``, or list the file below with the number of calls and why their output and run time are already
bounded.

The scan counts the ``.communicate(`` spelling only: ``subprocess.run(capture_output=True)`` and a pipe read by hand
are not covered.
"""

from __future__ import annotations

import ast
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent.parent / "app"

# file -> (number of calls, why the command's output and run time are bounded already)
_BOUNDED_BY_THE_COMMAND: dict[str, tuple[int, str]] = {
    "api/channels/test_connections.py": (
        1,
        "`<binary> --version` of a binary the user configured, 10 s deadline; only the first line is used",
    ),
    "remote_access/tailscale_service.py": (
        2,
        "`tailscale status --json` and `tailscale serve status --json`: small JSON, the caller's deadline",
    ),
}

# file -> (number of calls, what is not bounded). Each one is a known gap waiting for a decision: bound it with
# communicate_bounded, or move it up to the table above once its bound is shown.
_UNBOUNDED_PENDING_DECISION: dict[str, tuple[int, str]] = {
    "channels/providers/whatsapp/bridge.py": (1, "`npm install --production`: no deadline"),
    "services/meeting_notes/service.py": (
        1,
        "`ffmpeg -i <audio> -f null -` decodes the whole recording to find its length: no deadline",
    ),
}


def communicate_call_lines(source: str) -> list[int]:
    """Line numbers of ``<anything>.communicate(...)`` calls."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "communicate"
    ]


def _calls_per_file() -> dict[str, int]:
    found: dict[str, int] = {}
    for path in _APP_ROOT.rglob("*.py"):
        lines = communicate_call_lines(path.read_text(encoding="utf-8"))
        if lines:
            found[path.relative_to(_APP_ROOT).as_posix()] = len(lines)
    return found


def test_the_detector_finds_a_communicate_call_however_it_is_written() -> None:
    assert communicate_call_lines("await proc.communicate()") == [1]
    assert communicate_call_lines("out, err = await proc.communicate(input=b'x')") == [1]
    assert communicate_call_lines("await asyncio.wait_for(proc.communicate(), timeout=5)") == [1]
    assert communicate_call_lines("a.communicate()\nb.communicate()") == [1, 2]


def test_the_detector_ignores_everything_that_is_not_a_communicate_call() -> None:
    assert communicate_call_lines("await communicate_bounded(proc, timeout=5, on_abort=stop)") == []
    assert communicate_call_lines("class P:\n    async def communicate(self): ...") == []
    assert communicate_call_lines("communicate()") == []
    assert communicate_call_lines("note = 'proc.communicate() keeps everything'") == []
    assert communicate_call_lines("handler = proc.communicate") == []


def test_every_communicate_call_is_accounted_for() -> None:
    accounted = {**_BOUNDED_BY_THE_COMMAND, **_UNBOUNDED_PENDING_DECISION}
    unaccounted = {rel: count for rel, count in _calls_per_file().items() if rel not in accounted}

    assert not unaccounted, (
        f"Process.communicate() keeps all output and has no deadline of its own: {unaccounted}. "
        "Use the harness's communicate_bounded, or list the file in _BOUNDED_BY_THE_COMMAND "
        "with its number of calls and the reason their output and run time are bounded already."
    )


def test_the_accounted_files_make_exactly_the_calls_they_are_listed_for() -> None:
    found = _calls_per_file()
    accounted = {**_BOUNDED_BY_THE_COMMAND, **_UNBOUNDED_PENDING_DECISION}
    drifted = {rel: (count, found.get(rel, 0)) for rel, (count, _) in accounted.items() if found.get(rel, 0) != count}

    assert not drifted, (
        f"(listed, found) calls differ for {drifted}. A file that no longer calls communicate() leaves the "
        "allowlist; a file that gained a call needs that call's bound shown, or communicate_bounded instead."
    )


def test_a_file_is_listed_once_and_every_entry_gives_its_reason() -> None:
    assert not _BOUNDED_BY_THE_COMMAND.keys() & _UNBOUNDED_PENDING_DECISION.keys()
    entries = [*_BOUNDED_BY_THE_COMMAND.values(), *_UNBOUNDED_PENDING_DECISION.values()]
    assert all(count > 0 and reason.strip() for count, reason in entries)
