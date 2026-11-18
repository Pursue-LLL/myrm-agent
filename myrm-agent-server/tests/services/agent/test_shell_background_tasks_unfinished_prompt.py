"""A question that ends without a newline reaches the Activity panel as a structured prompt.

The harness reader keeps what a job printed after its last newline apart from the output lines, so a ``[Y/n]``
question is in none of them; the panel row adds that unfinished line when it parses the prompt.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.meta_tools.bash._background import types as background_types
from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol

from app.services.agent.shell_background_tasks import list_shell_background_tasks

_PID = 4101


class _HeldOpenPipe:
    """Delivers one chunk and then waits, as the pipe of a program that asks a question and waits does."""

    def __init__(self, chunk: bytes) -> None:
        self._chunk: bytes | None = chunk
        self._never = asyncio.Event()

    async def read(self, n: int = -1) -> bytes:
        if self._chunk is not None:
            chunk, self._chunk = self._chunk, None
            return chunk
        await self._never.wait()
        return b""


class _EndedPipe:
    async def read(self, n: int = -1) -> bytes:
        return b""


class _AskingJob:
    """A running program whose stdout asks a question and whose stdin is open."""

    def __init__(self, question: bytes) -> None:
        self._proc = MagicMock(pid=_PID)
        self.stdin = MagicMock()
        self.stdout = _HeldOpenPipe(question)
        self.stderr = _EndedPipe()
        self._exit = asyncio.Event()

    async def wait(self) -> int:
        await self._exit.wait()
        return 0

    def terminate(self) -> None:
        self._exit.set()

    def kill(self) -> None:
        self._exit.set()


@pytest.fixture
async def asking_registry(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[BackgroundProcessRegistry]:
    """A registry holding one job that asked and waits; the idle limit is short so the job counts as waiting at once."""
    monkeypatch.setattr(background_types, "INPUT_WAIT_IDLE_SECONDS", 0.05)
    registry = BackgroundProcessRegistry()
    job = _AskingJob(b"Proceed with installation? [Y/n] ")
    await registry.register(cast(AsyncProcessProtocol, job), command="installer", session_id="chat-panel")
    deadline = time.monotonic() + 5
    while not registry.get_partial_line(_PID) and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.1)
    yield registry
    job.terminate()
    await asyncio.sleep(0.05)


async def test_a_confirm_question_without_a_newline_becomes_a_structured_prompt(
    asking_registry: BackgroundProcessRegistry,
) -> None:
    assert asking_registry.get_output(_PID)["stdout"] == []

    with patch("myrm_agent_harness.api.hooks.get_background_registry", return_value=asking_registry):
        rows = list_shell_background_tasks()

    assert len(rows) == 1
    assert rows[0].waiting_for_input is True
    prompt = rows[0].interactive_prompt
    assert prompt is not None
    assert prompt.kind == "confirm"
    assert prompt.question == "Proceed with installation?"
    assert [option.value for option in prompt.options] == ["Y", "n"]
