"""An external CLI agent keeps its conversation across a server restart: pool wiring + registry + chat row + real CLI process.

The fake ``claude`` echoes the session id passed through ``--resume`` (a fresh one otherwise) in a ``result`` event, the
way ``claude -p --output-format stream-json`` reports it. Nothing between the mixin and the subprocess is mocked.
"""

from __future__ import annotations

import json
import stat
import sys
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.acp.types import RuntimeEventType

from app.ai_agents.general_agent.external_agents import ExternalAgentsMixin
from app.database.models.chat import Chat
from app.platform_utils import get_session_factory
from app.services.external_agents.runtime_pool_registry import get_chat_runtime_pool_registry

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake CLI is a POSIX shebang script")

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
    workdir: Path

    def resume_args(self) -> list[str | None]:
        calls = self.command.parent / "calls.jsonl"
        return [json.loads(line)["resume"] for line in calls.read_text().splitlines()] if calls.exists() else []


@pytest.fixture
async def fake_claude(tmp_path: Path) -> AsyncIterator[_FakeClaude]:
    await get_chat_runtime_pool_registry().close_all()
    # The basename must be `claude`: only that command supports --resume.
    command = tmp_path / "bin" / "claude"
    command.parent.mkdir()
    command.write_text(_FAKE_CLAUDE.replace("__PYTHON__", sys.executable))
    command.chmod(command.stat().st_mode | stat.S_IEXEC)
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    yield _FakeClaude(command, workdir)
    await get_chat_runtime_pool_registry().close_all()


async def _create_chat(*, incognito: bool = False) -> str:
    chat_id = f"resume-wiring-{uuid.uuid4().hex[:10]}"
    async with get_session_factory()() as db:
        db.add(Chat(id=chat_id, title="external agent", is_incognito=incognito))
        await db.commit()
    return chat_id


def _new_mixin(cli: _FakeClaude, scope_id: str | None) -> ExternalAgentsMixin:
    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin.external_agents_config = [
        {
            "name": "claude",
            "type": "cli",
            "command": str(cli.command),
            "args": ["-p", "--output-format", "stream-json"],
            "cwd": str(cli.workdir),
            "permissionMode": "safe",
            "timeout": 20,
        }
    ]
    mixin._runtime_pool_scope_id = scope_id
    mixin._runtime_pool = None
    mixin._runtime_pool_from_registry = False
    mixin._owned_runtime_pool = None
    mixin.agent_id = "general"
    mixin.force_external_agent = None
    return mixin


async def _turn(mixin: ExternalAgentsMixin, session_id: str) -> str:
    """Run one delegation turn and return the session id the fake CLI answered with."""
    assert mixin._runtime_pool is not None
    text: list[str] = []
    async for event in mixin._runtime_pool.run_turn("claude", "prompt", session_id):
        assert event.type != RuntimeEventType.ERROR, event.data
        if event.type == RuntimeEventType.TEXT_DELTA:
            text.append(str(event.data.get("content")))
    return "".join(text)


async def _restart_server(cli: _FakeClaude, scope_id: str | None) -> ExternalAgentsMixin:
    """Every in-memory pool is gone; the next request builds the delegation setup from scratch."""
    await get_chat_runtime_pool_registry().close_all()
    mixin = _new_mixin(cli, scope_id)
    await mixin._do_setup_external_agents([], mount_invoke_acp_agent_tool=False)
    return mixin


async def test_a_restarted_server_resumes_the_external_session_of_the_chat(fake_claude: _FakeClaude) -> None:
    chat_id = await _create_chat()
    session_id = f"claude-{chat_id}"
    first_server = _new_mixin(fake_claude, chat_id)
    await first_server._do_setup_external_agents([], mount_invoke_acp_agent_tool=False)
    first = await _turn(first_server, session_id)

    restarted = await _restart_server(fake_claude, chat_id)
    second = await _turn(restarted, session_id)

    assert first
    assert second == first
    assert fake_claude.resume_args() == [None, first]


async def test_an_incognito_chat_starts_a_new_external_session_after_a_restart(fake_claude: _FakeClaude) -> None:
    """Incognito keeps nothing on disk about the conversation, so a restart ends the external session too."""
    chat_id = await _create_chat(incognito=True)
    session_id = f"claude-{chat_id}"
    first_server = _new_mixin(fake_claude, chat_id)
    await first_server._do_setup_external_agents([], mount_invoke_acp_agent_tool=False)
    first = await _turn(first_server, session_id)

    restarted = await _restart_server(fake_claude, chat_id)
    second = await _turn(restarted, session_id)

    assert second != first
    assert fake_claude.resume_args() == [None, None]


async def test_without_a_chat_scope_nothing_is_persisted(fake_claude: _FakeClaude) -> None:
    ephemeral = _new_mixin(fake_claude, None)
    await ephemeral._do_setup_external_agents([], mount_invoke_acp_agent_tool=False)
    first = await _turn(ephemeral, "claude-ephemeral")

    again = _new_mixin(fake_claude, None)
    await again._do_setup_external_agents([], mount_invoke_acp_agent_tool=False)
    second = await _turn(again, "claude-ephemeral")

    assert second != first
    assert fake_claude.resume_args() == [None, None]


async def test_flushing_the_chat_makes_the_external_agent_start_over(fake_claude: _FakeClaude) -> None:
    """The user cleared the context: the next external turn must not resume the flushed conversation.

    Both halves are needed: the stored session id would be picked up by the next pool, and the pool still
    alive in this process remembers it in memory.
    """
    from app.services.chat.chat_service import ChatService

    chat_id = await _create_chat()
    session_id = f"claude-{chat_id}"
    before = _new_mixin(fake_claude, chat_id)
    await before._do_setup_external_agents([], mount_invoke_acp_agent_tool=False)
    first = await _turn(before, session_id)

    assert await ChatService.focus_flush_session(chat_id) is True

    after = _new_mixin(fake_claude, chat_id)
    await after._do_setup_external_agents([], mount_invoke_acp_agent_tool=False)
    second = await _turn(after, session_id)

    assert second != first
    assert fake_claude.resume_args() == [None, None]
