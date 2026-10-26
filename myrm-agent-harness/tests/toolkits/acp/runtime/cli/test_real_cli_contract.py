"""The real CLI binaries still behave the way ``CliRuntime`` assumes. Offline: nothing here needs a login or a model.

These guard against CLI drift, which no stand-in can: the flags the runtime passes still exist, and resuming a
conversation the CLI does not have fails the way the stale-session detection expects (a non-zero exit before the
CLI announces any session). Run with ``-m integration``; a CLI that is not installed skips its tests.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli.dialect import dialect_for
from myrm_agent_harness.toolkits.acp.runtime.cli.failure import classify_failure
from myrm_agent_harness.toolkits.acp.runtime.cli.process import spawn_cli_process
from myrm_agent_harness.toolkits.acp.runtime.cli.turn_parser import TurnParser
from myrm_agent_harness.toolkits.acp.types import AcpErrorCode, RuntimeEventType

pytestmark = pytest.mark.integration

_CLAUDE = shutil.which("claude")
_CODEX = shutil.which("codex")
_UNKNOWN_ID = "11111111-2222-4333-8444-555555555555"

needs_claude = pytest.mark.skipif(_CLAUDE is None, reason="claude CLI not installed")
needs_codex = pytest.mark.skipif(_CODEX is None, reason="codex CLI not installed")


def _help(*argv: str) -> str:
    done = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    return done.stdout + done.stderr


@needs_claude
@pytest.mark.asyncio
async def test_claude_refuses_an_unknown_session_before_announcing_anything(tmp_path: Path) -> None:
    dialect = dialect_for("claude")
    assert dialect is not None
    # The command line of a real turn: an unknown flag would make the CLI fail on its usage, not on the session.
    base = [str(_CLAUDE), "-p", "--output-format", "stream-json", "--verbose"]
    args = dialect.with_resume(dialect.with_max_turns(dialect.with_partial_messages(base), 3), _UNKNOWN_ID)
    assert args is not None
    parser = TurnParser("s1")
    (tmp_path / "claude-config").mkdir()
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(tmp_path / "claude-config")}

    async with spawn_cli_process(args, env=env, cwd=str(tmp_path), stdin_text="hello") as process:
        async with asyncio.timeout(60):
            events = [event for line in [line async for line in process.lines()] for event in parser.feed(line)]
            returncode = await process.wait()
        stderr = process.stderr_text

    assert returncode > 0
    assert parser.take_announced() is None
    assert [e.type for e in events if e.type is not RuntimeEventType.USAGE_UPDATE] == []
    assert parser.result is not None and parser.result.is_error
    assert "No conversation found" in stderr
    error = classify_failure(result=parser.result, returncode=returncode, stderr=stderr, killed=False)
    assert error is not None and error.code is not AcpErrorCode.CANCELLED


@needs_codex
def test_codex_exec_resume_still_takes_its_options_then_the_session_id_then_the_prompt() -> None:
    text = _help(str(_CODEX), "exec", "resume", "--help")

    assert "[SESSION_ID] [PROMPT]" in text
    assert "--json" in text
    assert "--skip-git-repo-check" in text


@needs_codex
@pytest.mark.asyncio
async def test_codex_refuses_an_unknown_thread_before_announcing_anything(tmp_path: Path) -> None:
    dialect = dialect_for("codex")
    assert dialect is not None
    base = [str(_CODEX), "--sandbox", "read-only", "exec", "--json", "--skip-git-repo-check"]
    args = dialect.with_resume(base, _UNKNOWN_ID)
    assert args is not None
    parser = TurnParser("s1")
    (tmp_path / "codex-home").mkdir()
    env = {**os.environ, "CODEX_HOME": str(tmp_path / "codex-home")}

    async with spawn_cli_process([*args, "hello"], env=env, cwd=str(tmp_path), stdin_text=None) as process:
        async with asyncio.timeout(60):
            for line in [line async for line in process.lines()]:
                parser.feed(line)
            returncode = await process.wait()
        stderr = process.stderr_text

    assert returncode > 0
    assert parser.take_announced() is None
    assert "no rollout found" in stderr
