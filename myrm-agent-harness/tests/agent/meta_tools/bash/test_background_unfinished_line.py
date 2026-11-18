"""A job's unfinished last line: how the registry serves it, and what real programs that print one look like.

A prompt such as ``Continue? [y/N] `` ends without a newline, so it is in no output line. The registry keeps what each
stream printed after its last newline and serves it on request (``get_partial_line``); the auto-detach return,
``output`` and ``wait`` show it, and a job that only redraws one line is not taken for a silent one.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable
from typing import cast
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background import types as background_types
from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.agent.meta_tools.bash._background.types import BackgroundProcessInfo
from myrm_agent_harness.agent.meta_tools.bash._executor.auto_yield import build_auto_yield_return
from myrm_agent_harness.toolkits.code_execution.executors.local import _background_pty_spawn
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeOutputPipe, FakeProc, wait_until
from tests.agent.meta_tools.bash.real_stack import RealBashStack

_SESSION = "unfinished-line"
_PROMPT = b"Continue? [y/N] "


class _Rig:
    """A registry of its own and the fake jobs started in it."""

    def __init__(self) -> None:
        self.registry = BackgroundProcessRegistry()
        self._procs: list[FakeProc] = []

    async def start(self, pid: int, stdout: FakeOutputPipe, stderr: FakeOutputPipe | None = None) -> FakeProc:
        proc = FakeProc(pid=pid, stdout=[], stdout_pipe=stdout, stderr_pipe=stderr, stdin=MagicMock())
        self._procs.append(proc)
        await self.registry.register(cast(AsyncProcessProtocol, proc), command="job", session_id=_SESSION)
        return proc

    async def unfinished_line(self, pid: int, *, expect: str = "") -> str:
        """The unfinished line once there is one, or once it equals *expect*."""
        await wait_until(
            lambda: (
                self.registry.get_partial_line(pid) == expect if expect else self.registry.get_partial_line(pid) != ""
            ),
            what="the unfinished line",
        )
        return self.registry.get_partial_line(pid)

    async def exited(self, pid: int) -> BackgroundProcessInfo:
        def _status() -> str | None:
            info = self.registry.get(pid)
            return info.status if info is not None else None

        await wait_until(lambda: _status() == "exited", what="the job to exit")
        info = self.registry.get(pid)
        assert info is not None
        return info


@pytest.fixture
async def rig() -> AsyncIterator[_Rig]:
    """Every job a test started is finished at teardown, so no reader task outlives its test."""
    rig = _Rig()
    yield rig
    for proc in rig._procs:
        proc.finish(0)
    await asyncio.sleep(0.05)


async def test_the_unfinished_line_of_a_running_job_is_its_prompt_and_in_no_output_line(
    rig: _Rig,
) -> None:
    await rig.start(72001, FakeOutputPipe([_PROMPT], hold_open=True))

    assert await rig.unfinished_line(72001) == "Continue? [y/N]"
    assert rig.registry.get_output(72001)["stdout"] == []


def test_a_pid_nobody_started_has_no_unfinished_line() -> None:
    assert BackgroundProcessRegistry().get_partial_line(72002) == ""


async def test_a_job_that_has_exited_has_no_unfinished_line(rig: _Rig) -> None:
    proc = await rig.start(72003, FakeOutputPipe([b"last words"]))
    proc.finish(0)
    await rig.exited(72003)

    assert rig.registry.get_partial_line(72003) == ""
    assert rig.registry.get_output(72003)["stdout"] == ["last words"]


async def test_the_stream_that_spoke_last_supplies_the_unfinished_line(rig: _Rig) -> None:
    stdout = FakeOutputPipe([b"building"], hold_open=True)
    stderr = FakeOutputPipe(hold_open=True)
    await rig.start(72004, stdout, stderr)
    assert await rig.unfinished_line(72004) == "building"

    await asyncio.sleep(0.02)
    stderr.feed(b"Password: ")
    assert await rig.unfinished_line(72004, expect="Password:") == "Password:"

    await asyncio.sleep(0.02)
    stdout.feed(b" again")
    assert await rig.unfinished_line(72004, expect="building again") == "building again"


async def test_escape_sequences_and_line_redraws_are_dropped(rig: _Rig) -> None:
    redrawn = b"\x1b[32mdownloading 10%\r\x1b[Kdownloading 20%\r"
    await rig.start(72005, FakeOutputPipe([redrawn], hold_open=True))

    assert await rig.unfinished_line(72005) == "downloading 20%"


async def test_a_secret_in_the_unfinished_line_is_masked(rig: _Rig) -> None:
    prompt = b"Enter token sk-ant-api03-abcdefghijklmnop1234567890: "
    await rig.start(72006, FakeOutputPipe([prompt], hold_open=True))

    line = await rig.unfinished_line(72006)

    assert "abcdefghijklmnop" not in line
    assert line.startswith("Enter token sk-ant")


async def test_a_secret_is_masked_before_the_line_is_cut_to_its_final_characters(
    rig: _Rig,
) -> None:
    """Cut first, the length limit would split the key and leave a tail that no longer looks like one."""
    token = "sk-ant-api03-" + "Zq8" * 15
    await rig.start(72007, FakeOutputPipe([f"{token} {'w' * 150}".encode()], hold_open=True))

    line = await rig.unfinished_line(72007)

    assert "Zq8Zq8Zq8Zq8" not in line
    assert "sk-ant" in line


async def test_the_unfinished_line_is_cut_to_its_final_200_characters(rig: _Rig) -> None:
    await rig.start(72008, FakeOutputPipe([b"x" * 300 + b"END"], hold_open=True))

    assert await rig.unfinished_line(72008) == "x" * 197 + "END"


async def test_reading_the_unfinished_line_while_the_reader_writes_never_returns_torn_text(
    rig: _Rig,
) -> None:
    pipe = FakeOutputPipe(hold_open=True)
    await rig.start(72009, pipe)
    done = threading.Event()
    seen: set[str] = set()
    failures: list[BaseException] = []

    def _poll() -> None:
        while not done.is_set():
            try:
                text = rig.registry.get_partial_line(72009)
            except BaseException as exc:
                failures.append(exc)
                return
            if text:
                seen.add(text)

    poller = asyncio.get_running_loop().run_in_executor(None, _poll)
    for number in range(3000):
        pipe.feed(f"{number:06d}\r".encode())
        if number % 20 == 0:
            await asyncio.sleep(0)
    done.set()
    await poller

    assert failures == []
    assert seen
    assert all(re.fullmatch(r"\d{6}", text) for text in seen), sorted(seen)[:5]


async def test_the_auto_detach_return_shows_the_unfinished_line_after_the_output(
    rig: _Rig,
) -> None:
    await rig.start(72010, FakeOutputPipe([b"Building...\n" + _PROMPT], hold_open=True))
    await rig.unfinished_line(72010)
    info = rig.registry.get(72010)
    assert info is not None

    content = str(build_auto_yield_return(info=info, yield_seconds=10, registry=rig.registry)["content"])

    assert "detached as background job" in content
    assert content.index("Partial output:\nBuilding...") < content.index(
        "Unfinished last line (no newline yet): Continue? [y/N]"
    )


async def test_the_auto_detach_return_of_a_job_with_no_unfinished_line_has_no_such_section(
    rig: _Rig,
) -> None:
    await rig.start(72011, FakeOutputPipe([b"Building...\n"], hold_open=True))
    await wait_until(lambda: rig.registry.get_output(72011)["stdout"] == ["Building..."], what="the output line")
    info = rig.registry.get(72011)
    assert info is not None

    content = str(build_auto_yield_return(info=info, yield_seconds=10, registry=rig.registry)["content"])

    assert "Partial output:\nBuilding..." in content
    assert "Unfinished last line" not in content


async def test_the_auto_detach_return_of_a_job_that_ended_inside_the_window_is_unchanged(
    rig: _Rig,
) -> None:
    proc = await rig.start(72012, FakeOutputPipe([b"done\nfinal"]))
    proc.finish(0)
    info = await rig.exited(72012)

    payload = build_auto_yield_return(info=info, yield_seconds=10, registry=rig.registry)

    assert cast(dict[str, object], payload["metadata"])["completed_in_yield_window"] is True
    assert "done\nfinal" in str(payload["content"])
    assert "Unfinished last line" not in str(payload["content"])


# --- real programs on a pseudo-terminal and on plain pipes ---

_ASK = "import time\nname = input('q? ')\nprint('hi', name, flush=True)\ntime.sleep(60)\n"
_REDRAW = "import sys, time\nfor i in range(1, 60):\n    sys.stdout.write(f'\\rprogress {i}%')\n    sys.stdout.flush()\n    time.sleep(0.3)\n"
_QUIET = "import time\ntime.sleep(60)\n"
_TOKEN_PROMPT = "import time\ninput('Enter token sk-ant-api03-abcdefghijklmnop1234567890: ')\ntime.sleep(60)\n"

_real = pytest.mark.skipif(sys.platform == "win32", reason="POSIX pseudo-terminals")
_on_pty_or_pipes = pytest.mark.parametrize("on_pty", [True, False], ids=["pty", "pipes"])


def _use_pipes_unless(on_pty: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    if not on_pty:
        monkeypatch.setattr(_background_pty_spawn, "pty_spawn_eligible", lambda *, sandbox_enabled: False)


async def _read_until(
    stack: RealBashStack, pid: int, ready: Callable[[dict[str, object]], bool], *, what: str, seconds: float = 10.0
) -> dict[str, object]:
    deadline = time.monotonic() + seconds
    while True:
        content = await stack.read_job(pid)
        if ready(content):
            return content
        if time.monotonic() > deadline:
            raise AssertionError(f"Timed out waiting for {what}; last read: {content!r}")
        await asyncio.sleep(0.2)


@_real
@pytest.mark.slow
@_on_pty_or_pipes
async def test_a_prompt_without_a_newline_is_in_partial_line_not_in_stdout_and_gone_after_the_reply(
    shared_real_stack: RealBashStack, monkeypatch: pytest.MonkeyPatch, on_pty: bool
) -> None:
    _use_pipes_unless(on_pty, monkeypatch)
    (shared_real_stack.workspace / "ask.py").write_text(_ASK, encoding="utf-8")
    pid = await shared_real_stack.start_background("python3 ask.py")
    try:
        asked = await _read_until(shared_real_stack, pid, lambda c: "partial_line" in c, what="the prompt")
        assert asked["partial_line"] == "q?"
        assert "q?" not in "\n".join(cast(list[str], asked["stdout"]))

        await shared_real_stack.send_to_job(pid, "Ada")
        answered = await _read_until(
            shared_real_stack,
            pid,
            lambda c: any("hi Ada" in line for line in cast(list[str], c["stdout"])),
            what="the greeting",
        )
        assert "partial_line" not in answered
    finally:
        await shared_real_stack.stop_job(pid)


@_real
@pytest.mark.slow
@_on_pty_or_pipes
async def test_a_secret_in_a_real_prompt_is_masked_in_partial_line(
    shared_real_stack: RealBashStack, monkeypatch: pytest.MonkeyPatch, on_pty: bool
) -> None:
    _use_pipes_unless(on_pty, monkeypatch)
    (shared_real_stack.workspace / "token.py").write_text(_TOKEN_PROMPT, encoding="utf-8")
    pid = await shared_real_stack.start_background("python3 token.py")
    try:
        asked = await _read_until(shared_real_stack, pid, lambda c: "partial_line" in c, what="the prompt")
        assert "abcdefghijklmnop" not in str(asked["partial_line"])
        assert "abcdefghijklmnop1234567890" not in str(asked)
        assert str(asked["partial_line"]).startswith("Enter token sk-ant")
    finally:
        await shared_real_stack.stop_job(pid)


@_real
@pytest.mark.slow
async def test_a_job_that_redraws_one_line_is_not_flagged_as_waiting_and_a_quiet_job_still_is(
    shared_real_stack: RealBashStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The idle limit is cut to one second so the cases run in seconds; the rule is the same at 15."""
    monkeypatch.setattr(background_types, "INPUT_WAIT_IDLE_SECONDS", 1.0)
    (shared_real_stack.workspace / "redraw.py").write_text(_REDRAW, encoding="utf-8")
    (shared_real_stack.workspace / "quiet.py").write_text(_QUIET, encoding="utf-8")
    redrawing = await shared_real_stack.start_background("python3 redraw.py")
    quiet = await shared_real_stack.start_background("python3 quiet.py")
    try:
        quiet_read = await _read_until(
            shared_real_stack, quiet, lambda c: c["waiting_for_input"] is True, what="the quiet job to be flagged"
        )
        redrawing_read = await shared_real_stack.read_job(redrawing)

        assert "partial_line" not in quiet_read
        assert redrawing_read["waiting_for_input"] is False
        assert str(redrawing_read["partial_line"]).startswith("progress ")
    finally:
        await shared_real_stack.stop_job(redrawing)
        await shared_real_stack.stop_job(quiet)


@_real
@pytest.mark.slow
@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
@_on_pty_or_pipes
async def test_the_return_of_a_command_that_became_a_background_job_shows_its_prompt(
    shared_real_stack: RealBashStack, monkeypatch: pytest.MonkeyPatch, on_pty: bool
) -> None:
    _use_pipes_unless(on_pty, monkeypatch)
    (shared_real_stack.workspace / "ask.py").write_text(_ASK, encoding="utf-8")
    (shared_real_stack.workspace / "Makefile").write_text("test:\n\tpython3 ask.py\n", encoding="utf-8")

    content, pid = await shared_real_stack.run_detaching("make test", yield_after_seconds=2)
    try:
        assert "detached as background job" in content
        assert "Unfinished last line (no newline yet): q?" in content
    finally:
        await shared_real_stack.stop_job(pid)
