"""A CLI chat keeps its ``--resume`` session across the registry's idle window (real pool, fake ``claude``).

Idle cleanup exists to free resident processes. A CLI backend has none between turns, so cleaning up an
idle CLI chat must not cost it the session id that the next turn replays through ``--resume``.
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
from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import RuntimeConfig, RuntimeEventType

from app.services.external_agents.runtime_pool_registry import (
    ChatRuntimePoolRegistry,
    ChatScopedRuntimePoolFacade,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake CLI is a POSIX shebang script")

_IDLE_SECONDS = 0.05
_FINGERPRINT = "fp-a"

# Behaves like `claude -p --output-format stream-json`: echoes the session id (the one passed via
# --resume, else a fresh one) and records every invocation's --resume argument.
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
async def registry() -> AsyncIterator[ChatRuntimePoolRegistry]:
    chat_registry = ChatRuntimePoolRegistry(idle_seconds=_IDLE_SECONDS)
    yield chat_registry
    await chat_registry.close_all()


def _builder(fake_claude: _FakeClaude, cwd: Path):
    async def build_pool() -> RuntimePool:
        pool = RuntimePool(max_concurrent=2)
        pool.register(
            "claude",
            RuntimeConfig(
                backend_type="cli",
                command=str(fake_claude.command),
                args=["-p", "--output-format", "stream-json"],
                permission_mode="safe",
                cwd=str(cwd),
                timeout_seconds=20,
            ),
        )
        return pool

    return build_pool


async def _unexpected_build() -> RuntimePool:
    raise AssertionError("the chat's pool must be reused, not rebuilt")


async def _delegate(facade: ChatScopedRuntimePoolFacade) -> str:
    text: list[str] = []
    async for event in facade.run_turn("claude", "prompt", session_id="claude-chat-1"):
        if event.type == RuntimeEventType.TEXT_DELTA:
            text.append(str(event.data.get("content")))
    return "".join(text)


async def _idle_past_the_window() -> None:
    await asyncio.sleep(_IDLE_SECONDS * 3)


@pytest.mark.asyncio
async def test_follow_up_resumes_after_another_chat_triggered_the_idle_pass(
    registry: ChatRuntimePoolRegistry, fake_claude: _FakeClaude, tmp_path: Path
) -> None:
    """The cached execution unit keeps its facade; another chat's acquire runs the idle pass meanwhile."""
    build = _builder(fake_claude, tmp_path)
    pool = await registry.acquire("chat-1", _FINGERPRINT, build)
    facade = ChatScopedRuntimePoolFacade(pool, "chat-1", registry, _FINGERPRINT)
    first = await _delegate(facade)
    await _idle_past_the_window()
    await registry.acquire("chat-2", _FINGERPRINT, build)

    follow_up = await _delegate(facade)

    assert follow_up == first
    assert fake_claude.resume_args() == [None, first]


@pytest.mark.asyncio
async def test_follow_up_resumes_after_the_chat_rebuilt_its_agent_past_the_idle_window(
    registry: ChatRuntimePoolRegistry, fake_claude: _FakeClaude, tmp_path: Path
) -> None:
    """A new message rebuilds the agent and acquires the pool again; the idle pass must hand the same pool back."""
    pool = await registry.acquire("chat-1", _FINGERPRINT, _builder(fake_claude, tmp_path))
    first = await _delegate(ChatScopedRuntimePoolFacade(pool, "chat-1", registry, _FINGERPRINT))
    await _idle_past_the_window()

    returned = await registry.acquire("chat-1", _FINGERPRINT, _unexpected_build)
    follow_up = await _delegate(ChatScopedRuntimePoolFacade(returned, "chat-1", registry, _FINGERPRINT))

    assert returned is pool
    assert follow_up == first
    assert fake_claude.resume_args() == [None, first]
