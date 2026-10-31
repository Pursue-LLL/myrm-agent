"""Every ``Process.communicate()`` call is either replaced by ``communicate_bounded`` or accounted for here.

``communicate()`` keeps everything the child writes and, called alone, waits without a deadline. A command whose output
the framework does not control (anything that runs text from a user, a model, a skill or a repository) can therefore
grow the host's memory or hold a run for as long as it likes. A new call must be a conscious decision: use
``core.security.bounded_communicate.communicate_bounded``, or list the file below with the number of calls and why their
output and run time are already bounded.

The scan counts the ``.communicate(`` spelling only: ``subprocess.run(capture_output=True)`` and a pipe read by hand
are not covered.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent.parent / "src" / "myrm_agent_harness"

# file -> (number of calls, why the command's output and run time are bounded already)
_BOUNDED_BY_THE_COMMAND: dict[str, tuple[int, str]] = {
    "agent/file_snapshot/factory.py": (1, "`git --version`; both pipes are discarded"),
    "runtime/doctor/capability_verifier.py": (1, "runs a fixed `echo`; the output is one word"),
    "toolkits/acp/core/backend_detector.py": (
        1,
        "`<binary> --version` of an installed agent CLI, 10 s deadline; only the first line is used",
    ),
    "toolkits/code_execution/sandbox/providers/appcontainer.py": (
        1,
        "`icacls /Q` (quiet) on a path the host chose, 30 s deadline",
    ),
    "toolkits/code_execution/session/persistent_session.py": (
        2,
        "`bash -n` syntax check: stdout discarded, stderr is the syntax error, 10 s deadline then kill",
    ),
    "toolkits/computer_use/backends/macos/backend.py": (
        1,
        "`screencapture` writes the image to a file; the pipes carry only an error line",
    ),
    "toolkits/computer_use/backends/macos/background.py": (
        1,
        "`screencapture -l` writes the image to a file; the pipes carry only an error line",
    ),
    "toolkits/computer_use/backends/linux/backend.py": (
        1,
        "fixed `xdotool` / `xprop` / screenshot helpers run without a shell; a deadline or a cancel kills them",
    ),
    "toolkits/code_execution/executors/common/subprocess_guard.py": (
        1,
        "deadline-and-terminate wrapper; its one caller runs `python -m venv`, 120 s deadline",
    ),
    "toolkits/vnc/server.py": (1, "`x11vnc -storepasswd` writes a password file, 5 s deadline"),
    "toolkits/browser/pool/browser_launcher.py": (
        1,
        "`patchright install chromium` log, deadline `_INSTALL_TIMEOUT_S`",
    ),
    "agent/skills/market/installers/git_installer.py": (
        1,
        "`git clone` prints little when not on a terminal; 60 s deadline then kill",
    ),
    "agent/meta_tools/file_ops/observers/format_observer.py": (
        1,
        "formatter on one file, stdout discarded, 10 s deadline; only the first 200 characters of stderr are used",
    ),
    "agent/goals/continuation_git_drift.py": (
        1,
        "hardened `git rev-parse` / `rev-list` / `rebase` answers, 15 s deadline",
    ),
    "toolkits/file_parsers/__init__.py": (
        1,
        "`soffice --convert-to` writes to a directory, 60 s deadline; only the first 500 characters of stderr are used",
    ),
}

# file -> (number of calls, what is not bounded). Each one is a known gap waiting for a decision: bound it with
# communicate_bounded, or move it up to the table above once its bound is shown.
_UNBOUNDED_PENDING_DECISION: dict[str, tuple[int, str]] = {
    "agent/file_snapshot/shadow_git_store.py": (
        1,
        "git over the whole workspace (`add --all`, `diff`, `ls-tree`): no deadline, all output held in memory",
    ),
    "agent/sub_agents/cli_adapter/adapter.py": (
        3,
        "external CLI agent: all output held in memory until `timeout_seconds`; the deadline signals only the leader",
    ),
    "toolkits/ssh_remote/executor.py": (
        1,
        "remote command: all output held in memory until the deadline, which does not stop the process",
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
    for path in _SRC.rglob("*.py"):
        lines = communicate_call_lines(path.read_text(encoding="utf-8"))
        if lines:
            found[path.relative_to(_SRC).as_posix()] = len(lines)
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
        "Use core.security.bounded_communicate.communicate_bounded, or list the file in _BOUNDED_BY_THE_COMMAND "
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
