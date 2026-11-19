"""The stand-in for a container host: the sandbox probe finds no OS sandbox, and every pseudo-terminal spawn is recorded as the executor made it."""

from __future__ import annotations

from typing import cast

import pytest
from myrm_agent_harness.toolkits.code_execution import sandbox
from myrm_agent_harness.toolkits.code_execution.executors.local import _background_pty_spawn
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import NullProvider

from tests.support.container_host import record_pty_spawns, without_os_sandbox

_PROCESS = cast(AsyncProcessProtocol, object())
_SPAWN_KWARGS: dict[str, object] = {
    "full_cmd_array": ["/bin/bash", "-c", "true"],
    "effective_cwd": None,
    "env": {"KEY": "value"},
    "preexec_fn": None,
    "process_group_kwargs": {"start_new_session": True},
}


def _spawn_answering(monkeypatch: pytest.MonkeyPatch, *answers: AsyncProcessProtocol | None) -> list[dict[str, object]]:
    """The executor's pseudo-terminal spawn, answering with each of `answers` in turn; the list is what each call was given."""
    pending = iter(answers)
    calls: list[dict[str, object]] = []

    async def spawn(**kwargs: object) -> AsyncProcessProtocol | None:
        calls.append(kwargs)
        return next(pending)

    monkeypatch.setattr(_background_pty_spawn, "try_spawn_background_pty", spawn)
    return calls


async def _spawn_once() -> AsyncProcessProtocol | None:
    return await _background_pty_spawn.try_spawn_background_pty(
        full_cmd_array=["/bin/bash", "-c", "true"],
        effective_cwd=None,
        env={"KEY": "value"},
        preexec_fn=None,
        process_group_kwargs={"start_new_session": True},
    )


def test_the_probe_finds_no_os_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    without_os_sandbox(monkeypatch)

    provider, status = sandbox.detect_sandbox_provider()

    assert isinstance(provider, NullProvider)
    assert status.enabled is False


async def test_each_spawn_is_recorded_with_whether_it_produced_a_process(monkeypatch: pytest.MonkeyPatch) -> None:
    _spawn_answering(monkeypatch, _PROCESS, None)
    outcomes = record_pty_spawns(monkeypatch)

    await _spawn_once()
    await _spawn_once()

    assert outcomes == [True, False]


async def test_a_recorded_spawn_gets_and_gives_what_it_would_unrecorded(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _spawn_answering(monkeypatch, _PROCESS, None)
    record_pty_spawns(monkeypatch)

    first = await _spawn_once()
    second = await _spawn_once()

    assert (first, second) == (_PROCESS, None)
    assert calls == [_SPAWN_KWARGS, _SPAWN_KWARGS]
