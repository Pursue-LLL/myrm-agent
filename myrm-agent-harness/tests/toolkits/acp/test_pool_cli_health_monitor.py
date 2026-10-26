"""RuntimePool with the health monitor on, driving a real ``CliRuntime`` subprocess.

A CLI backend spawns one process per turn, so between turns it has no process by design. The monitor
reads that as a crash and, after its backoff, ``close()``s the backend, which would kill a turn that
started in the meantime and forget the CLI session id used for ``--resume``. These tests pin that the
pool keeps CLI backends away from the monitor.
"""

from __future__ import annotations

import asyncio
import json
import stat
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.core import health_monitor as health_monitor_module
from myrm_agent_harness.toolkits.acp.core.health_monitor import HealthMonitor
from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import RuntimeConfig, RuntimeEvent, RuntimeEventType

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake CLI is a POSIX shebang script")

# Behaves like `claude -p --output-format stream-json`: echoes the session id (the one passed via
# --resume, else a fresh one) in a result event, and records how every invocation ended.
_FAKE_CLAUDE = """\
#!__PYTHON__
import json, os, signal, sys, time, uuid

here = os.path.dirname(os.path.abspath(__file__))
resume = sys.argv[sys.argv.index("--resume") + 1] if "--resume" in sys.argv else None


def log(event):
    with open(os.path.join(here, "calls.jsonl"), "a") as handle:
        handle.write(json.dumps({"event": event, "resume": resume}) + "\\n")


def on_term(signum, frame):
    log("killed")
    os._exit(143)


signal.signal(signal.SIGTERM, on_term)
sys.stdin.read()
log("start")
time.sleep(float(open(os.path.join(here, "turn_seconds")).read()))
session_id = resume or uuid.uuid4().hex[:8]
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": session_id}]}}), flush=True)
print(json.dumps({"type": "result", "session_id": session_id}), flush=True)
log("done")
"""

# Short poll interval and backoff so a monitor that wrongly supervised the CLI would act within the test.
_POLL_INTERVAL_SECONDS = 0.02
_CRASH_BACKOFF_SECONDS = 0.3


@dataclass
class _FakeClaude:
    command: Path
    turn_seconds_file: Path
    calls_file: Path

    def set_turn_seconds(self, seconds: float) -> None:
        self.turn_seconds_file.write_text(str(seconds))

    def calls(self) -> list[dict[str, str | None]]:
        if not self.calls_file.exists():
            return []
        return [json.loads(line) for line in self.calls_file.read_text().splitlines()]


@pytest.fixture
def fake_claude(tmp_path: Path) -> _FakeClaude:
    # The basename must be `claude`: CliRuntime only resumes sessions for that command.
    command = tmp_path / "bin" / "claude"
    command.parent.mkdir()
    command.write_text(_FAKE_CLAUDE.replace("__PYTHON__", sys.executable))
    command.chmod(command.stat().st_mode | stat.S_IEXEC)
    fake = _FakeClaude(command, command.parent / "turn_seconds", command.parent / "calls.jsonl")
    fake.set_turn_seconds(0.05)
    return fake


@pytest.fixture
async def pool(fake_claude: _FakeClaude, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[RuntimePool]:
    monkeypatch.setattr(health_monitor_module, "_BASE_BACKOFF", _CRASH_BACKOFF_SECONDS)
    runtime_pool = RuntimePool(max_concurrent=2, enable_health_monitor=True)
    runtime_pool._health_monitor = HealthMonitor(check_interval=_POLL_INTERVAL_SECONDS)
    runtime_pool.register(
        "claude",
        RuntimeConfig(
            backend_type="cli",
            command=str(fake_claude.command),
            args=["-p", "--output-format", "stream-json"],
            permission_mode="safe",
            cwd=str(tmp_path),
            timeout_seconds=20,
        ),
    )
    await runtime_pool.start_monitoring()
    yield runtime_pool
    await runtime_pool.close_all()


async def _run_turn(runtime_pool: RuntimePool) -> tuple[str, list[RuntimeEvent]]:
    text: list[str] = []
    errors: list[RuntimeEvent] = []
    async for event in runtime_pool.run_turn("claude", "prompt", session_id="chat-1"):
        if event.type == RuntimeEventType.TEXT_DELTA:
            text.append(str(event.data.get("content")))
        elif event.type == RuntimeEventType.ERROR:
            errors.append(event)
    return "".join(text), errors


@pytest.mark.asyncio
async def test_cli_session_id_survives_the_idle_gap_between_turns(pool: RuntimePool, fake_claude: _FakeClaude) -> None:
    first, first_errors = await _run_turn(pool)
    # Long enough for the monitor to have detected the idle backend and run its crash backoff to close().
    await asyncio.sleep(_CRASH_BACKOFF_SECONDS + 0.3)
    second, second_errors = await _run_turn(pool)

    assert not first_errors
    assert not second_errors
    assert second == first
    assert [call["resume"] for call in fake_claude.calls() if call["event"] == "start"] == [None, first]


@pytest.mark.asyncio
async def test_cli_turn_started_after_an_idle_gap_is_not_killed_mid_flight(
    pool: RuntimePool, fake_claude: _FakeClaude
) -> None:
    await _run_turn(pool)
    fake_claude.set_turn_seconds(_CRASH_BACKOFF_SECONDS * 3)
    # A supervising monitor would now be inside its crash backoff, with close() due before this turn ends.
    await asyncio.sleep(_POLL_INTERVAL_SECONDS * 5)

    text, errors = await _run_turn(pool)

    assert not errors
    assert text
    assert [call["event"] for call in fake_claude.calls()] == ["start", "done", "start", "done"]
