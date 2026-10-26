"""RuntimePool driving a real ``CliRuntime`` subprocess across turns.

A CLI backend spawns one process per turn; continuity between turns lives only in the runtime's
in-memory session id, replayed through ``--resume``. This pins that the second pool turn resumes the
session the first turn reported.
"""

from __future__ import annotations

import json
import stat
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import RuntimeConfig, RuntimeEvent, RuntimeEventType

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake CLI is a POSIX shebang script")

# Behaves like `claude -p --output-format stream-json`: echoes the session id (the one passed via
# --resume, else a fresh one) in a result event, and records every invocation's --resume argument.
_FAKE_CLAUDE = """\
#!__PYTHON__
import json, os, sys, uuid

here = os.path.dirname(os.path.abspath(__file__))
resume = sys.argv[sys.argv.index("--resume") + 1] if "--resume" in sys.argv else None
sys.stdin.read()
with open(os.path.join(here, "calls.jsonl"), "a") as handle:
    handle.write(json.dumps({"resume": resume}) + "\\n")
session_id = resume or uuid.uuid4().hex[:8]
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": session_id}]}}), flush=True)
print(json.dumps({"type": "result", "session_id": session_id}), flush=True)
"""


@dataclass
class _FakeClaude:
    command: Path
    calls_file: Path

    def resume_args(self) -> list[str | None]:
        if not self.calls_file.exists():
            return []
        return [json.loads(line)["resume"] for line in self.calls_file.read_text().splitlines()]


@pytest.fixture
def fake_claude(tmp_path: Path) -> _FakeClaude:
    # The basename must be `claude`: CliRuntime only resumes sessions for that command.
    command = tmp_path / "bin" / "claude"
    command.parent.mkdir()
    command.write_text(_FAKE_CLAUDE.replace("__PYTHON__", sys.executable))
    command.chmod(command.stat().st_mode | stat.S_IEXEC)
    return _FakeClaude(command, command.parent / "calls.jsonl")


@pytest.fixture
async def pool(fake_claude: _FakeClaude, tmp_path: Path) -> AsyncIterator[RuntimePool]:
    runtime_pool = RuntimePool(max_concurrent=2)
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
async def test_second_turn_resumes_the_session_the_first_turn_reported(
    pool: RuntimePool, fake_claude: _FakeClaude
) -> None:
    first, first_errors = await _run_turn(pool)
    second, second_errors = await _run_turn(pool)

    assert not first_errors
    assert not second_errors
    assert first
    assert second == first
    assert fake_claude.resume_args() == [None, first]
