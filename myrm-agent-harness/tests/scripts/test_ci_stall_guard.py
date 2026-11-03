"""Unit tests for ``scripts/ci_stall_guard.py`` and the SIGUSR1 stack dump it relies on.

The guard is exercised against real child processes: a silent command must be dumped and killed
together with its descendants, a command that keeps printing must never be touched, and the pytest
side (``tests/conftest.py``) must really write stacks to the real stderr while a test is running
under fd capture.
"""

from __future__ import annotations

import io
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts import ci_stall_guard
from scripts.ci_stall_guard import STALL_EXIT_CODE, run_guarded

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GUARD = _REPO_ROOT / "scripts" / "ci_stall_guard.py"


def _silent_in_named_frame(announce: str) -> str:
    """Child source: dump all stacks on SIGUSR1 exactly as ``tests/conftest.py`` does, then go silent."""
    return f"""
import faulthandler, os, signal, time
faulthandler.register(signal.SIGUSR1, file=os.dup(2), all_threads=True)
print({announce!r}, os.getpid(), flush=True)
def wait_here():
    time.sleep(120)
wait_here()
"""


_SILENT_WITH_DUMP_HANDLER = _silent_in_named_frame("ready")
_SILENT_WITHOUT_HANDLER = "import time; print('ready', flush=True); time.sleep(120)"
# Parent without a handler that leaves a silent grandchild with one, like uv -> pytest -> worker.
_SPAWNS_SILENT_GRANDCHILD = (
    "import subprocess, sys, time\n"
    f"subprocess.Popen([sys.executable, '-c', {_silent_in_named_frame('grandchild=')!r}])\n"
    "time.sleep(120)\n"
)


def _guard(
    command: list[str],
    tmp_path: Path,
    *,
    stall_seconds: float = 4.0,
    sample_seconds: float = 0.0,
) -> tuple[int, str, str]:
    console = io.BytesIO()
    code = run_guarded(
        command,
        stall_seconds=stall_seconds,
        sample_seconds=sample_seconds,
        log_path=tmp_path / "run.log",
        console=console,
    )
    return code, console.getvalue().decode(), (tmp_path / "run.log").read_text()


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False).stdout
    return bool(state.strip()) and not state.strip().startswith("Z")


def _wait_until(condition: Callable[[], bool], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return condition()


def test_silent_command_is_dumped_then_killed(tmp_path: Path) -> None:
    started = time.monotonic()
    code, console, log = _guard([sys.executable, "-c", _SILENT_WITH_DUMP_HANDLER], tmp_path, sample_seconds=0.4)

    assert code == STALL_EXIT_CODE
    assert time.monotonic() - started < 30
    assert re.search(r"\[ci-stall\] no output for \d+s", console)
    assert "wait_here" in console, "the stack of the silent frame must be in the dump"
    assert "[ci-sample]" in console, "sampling must not hide the stall"
    assert console == log
    pid = int(re.search(r"\[ci-stall\] stacks of pid=(\d+)", console).group(1))  # type: ignore[union-attr]
    assert _wait_until(lambda: not _is_running(pid), 5)


def test_command_without_a_dump_handler_is_still_killed(tmp_path: Path) -> None:
    code, console, _ = _guard([sys.executable, "-c", _SILENT_WITHOUT_HANDLER], tmp_path)

    assert code == STALL_EXIT_CODE
    assert "[ci-stall] killing the process group" in console


def test_stall_dumps_and_kills_the_whole_process_tree(tmp_path: Path) -> None:
    code, console, _ = _guard([sys.executable, "-c", _SPAWNS_SILENT_GRANDCHILD], tmp_path, stall_seconds=5.0)

    assert code == STALL_EXIT_CODE
    assert "wait_here" in console, "a descendant's stack must be dumped too"
    grandchild = int(re.search(r"grandchild= (\d+)", console).group(1))  # type: ignore[union-attr]
    assert _wait_until(lambda: not _is_running(grandchild), 5)


def test_command_that_keeps_printing_is_left_alone(tmp_path: Path) -> None:
    chatty = "import time\nfor n in range(8):\n    print('line', n, flush=True)\n    time.sleep(0.2)"
    code, console, log = _guard([sys.executable, "-c", chatty], tmp_path, sample_seconds=0.3)

    assert code == 0
    assert all(f"line {n}" in console for n in range(8))
    assert "[ci-stall]" not in console
    assert console == log


def test_output_without_newline_counts_as_progress(tmp_path: Path) -> None:
    dots = (
        "import sys, time\nfor _ in range(8):\n    sys.stdout.write('.')\n    sys.stdout.flush()\n    time.sleep(0.2)"
    )
    code, console, _ = _guard([sys.executable, "-c", dots], tmp_path)

    assert code == 0
    assert "........" in console


def test_exit_code_of_the_command_is_returned(tmp_path: Path) -> None:
    assert _guard([sys.executable, "-c", "import sys; sys.exit(3)"], tmp_path)[0] == 3


def test_command_ended_by_a_signal_maps_to_128_plus_signal(tmp_path: Path) -> None:
    code = _guard([sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"], tmp_path)[0]

    assert code == 128 + signal.SIGTERM


def test_cli_passes_everything_after_double_dash_to_the_command(tmp_path: Path) -> None:
    probe = "import sys; print(sys.argv[1:]); sys.exit(7)"
    guard = [sys.executable, str(_GUARD), "--log", str(tmp_path / "cli.log"), "--sample-seconds", "0"]
    result = subprocess.run(
        [*guard, "--", sys.executable, "-c", probe, "-n", "2", "--stall-seconds", "9"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 7
    assert "['-n', '2', '--stall-seconds', '9']" in result.stdout
    assert (tmp_path / "cli.log").read_text() == result.stdout


def test_cli_without_a_command_is_a_usage_error(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_GUARD), "--log", str(tmp_path / "cli.log")],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 2
    assert "no command given" in result.stderr


def test_cancelling_the_guard_takes_the_command_down_with_it(tmp_path: Path) -> None:
    long_running = "import os, time; print('pid=', os.getpid(), flush=True); time.sleep(120)"
    guard = subprocess.Popen(
        [sys.executable, str(_GUARD), "--log", str(tmp_path / "cancel.log"), "--", sys.executable, "-c", long_running],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert guard.stdout is not None
        command_pid = int(re.match(r"pid= (\d+)", guard.stdout.readline()).group(1))  # type: ignore[union-attr]
        guard.send_signal(signal.SIGTERM)
        assert guard.wait(timeout=30) == 128 + signal.SIGTERM
        assert _wait_until(lambda: not _is_running(command_pid), 5)
    finally:
        guard.kill()
        guard.wait()


def test_guard_lines_end_an_open_line_and_do_not_reset_the_stall_clock() -> None:
    console, log = io.BytesIO(), io.BytesIO()
    output = ci_stall_guard._Output(console, log)

    output.from_command(b"[gw0] [ 75%] PASSED tests/a.py::test_x ")
    clock = output.last_write
    output.from_guard("[ci-sample] +60s load=1.0")
    output.from_command(b"next\n")
    output.from_guard("[ci-stall] after a closed line")

    assert console.getvalue() == (
        b"[gw0] [ 75%] PASSED tests/a.py::test_x \n[ci-sample] +60s load=1.0\nnext\n[ci-stall] after a closed line\n"
    )
    assert log.getvalue() == console.getvalue()
    assert output.last_write > clock, "only the command's own output moves the clock, and it did so for 'next'"


def test_descendants_follow_parent_links_at_any_depth() -> None:
    table = {1: (0, "init"), 10: (1, "uv"), 11: (10, "python"), 12: (11, "python"), 13: (11, "python"), 20: (1, "sshd")}

    assert sorted(ci_stall_guard._descendants(10, table)) == [11, 12, 13]
    assert ci_stall_guard._descendants(12, table) == []


@pytest.fixture()
def fake_proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A /proc with one process (pid 100): a sleeping thread and one in uninterruptible I/O wait."""
    proc = tmp_path / "proc"
    (proc / "pressure").mkdir(parents=True)
    (proc / "meminfo").write_text(
        "MemTotal: 16777216 kB\nMemAvailable: 2097152 kB\nSwapTotal: 1048576 kB\nSwapFree: 524288 kB\n"
    )
    (proc / "pressure" / "cpu").write_text("some avg10=1.50 avg60=0.50 avg300=0.10 total=123\n")
    (proc / "100").mkdir()
    (proc / "100" / "status").write_text("Name:\tpython\nVmRSS:\t 3145728 kB\n")
    threads = {"100": ("S", "futex_wait_queue", "py thon"), "101": ("D", "io_schedule", "worker")}
    for tid, (state, wchan, name) in threads.items():
        task = proc / "100" / "task" / tid
        task.mkdir(parents=True)
        (task / "stat").write_text(f"{tid} ({name}) {state} 1 100 100 0 -1 4194560\n")
        (task / "wchan").write_text(wchan)
        (task / "comm").write_text(f"{name}\n")
    monkeypatch.setattr(ci_stall_guard, "_PROC", proc)
    return proc


def test_thread_rows_report_state_wait_channel_and_name(fake_proc: Path) -> None:
    assert ci_stall_guard._thread_rows(100) == [
        "    tid=100 state=S wchan=futex_wait_queue comm=py thon",
        "    tid=101 state=D wchan=io_schedule comm=worker",
    ]
    assert ci_stall_guard._thread_rows(999) == []


def test_system_snapshot_reads_memory_swap_rss_and_pressure(fake_proc: Path) -> None:
    snapshot = ci_stall_guard._system_snapshot([100, 999])

    assert re.fullmatch(
        r"load=\d+\.\d mem_available_mb=2048 swap_used_mb=512 tree_rss_mb=3072 psi_cpu=1\.50 psi_memory=\? psi_io=\?",
        snapshot,
    )


def test_system_snapshot_is_load_only_without_proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ci_stall_guard, "_PROC", tmp_path / "missing")

    assert re.fullmatch(r"load=\d+\.\d", ci_stall_guard._system_snapshot([100]))


def test_pytest_process_writes_its_stacks_to_real_stderr_on_sigusr1(tmp_path: Path) -> None:
    """The dump must survive fd capture, which discards whatever a running test writes to fd 2."""
    ready = tmp_path / "ready"
    target = tmp_path / "test_target.py"
    target.write_text(
        "import time\n"
        "from pathlib import Path\n"
        "def blocked_in_the_test():\n"
        f"    Path({str(ready)!r}).touch()\n"
        "    time.sleep(120)\n"
        "def test_blocks():\n"
        "    blocked_in_the_test()\n",
        encoding="utf-8",
    )
    pytest_run = subprocess.Popen(
        [
            *(sys.executable, "-m", "pytest", "-c", "pyproject.toml", "-p", "tests.conftest"),
            *("-p", "no:cacheprovider", "--rootdir", str(tmp_path), str(target)),
        ],
        cwd=_REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_until(lambda: ready.exists() or pytest_run.poll() is not None, 120)
        started = ready.exists()
        pytest_run.send_signal(signal.SIGUSR1)
        time.sleep(1.0)
    finally:
        pytest_run.kill()
        stdout, stderr = pytest_run.communicate(timeout=30)

    assert started, f"the target test never started:\n{stdout}\n{stderr}"
    assert "blocked_in_the_test" in stderr
