"""``start_one_time_work`` starts the token-vocabulary load and the toolchain probe without waiting for either."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest

from myrm_agent_harness.agent._factory import one_time_work
from myrm_agent_harness.toolkits.code_execution import env_probe
from myrm_agent_harness.utils import text_utils

_VOCABULARY_THREAD = "tiktoken-warm-up"


@pytest.fixture(autouse=True)
def _fresh_process_state() -> Iterator[None]:
    """The vocabulary load is once per process; each test starts before it."""
    one_time_work._start_token_vocabulary.cache_clear()
    yield
    one_time_work._start_token_vocabulary.cache_clear()


def _join(thread_name: str) -> None:
    for thread in threading.enumerate():
        if thread.name == thread_name:
            thread.join(timeout=5)


def test_the_vocabulary_loads_on_its_own_thread_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    ran_on: list[str] = []
    monkeypatch.setattr(text_utils, "preheat_tiktoken", lambda *_args: ran_on.append(threading.current_thread().name))
    monkeypatch.setattr(env_probe, "warm_up_environment_probe", lambda: None)

    one_time_work.start_one_time_work(shell_tools=True)
    one_time_work.start_one_time_work(shell_tools=True)
    _join(_VOCABULARY_THREAD)

    assert ran_on == [_VOCABULARY_THREAD]


@pytest.mark.parametrize(("shell_tools", "expected_calls"), [(True, 1), (False, 0)])
def test_the_toolchain_probe_starts_only_with_the_bash_tool(
    monkeypatch: pytest.MonkeyPatch, shell_tools: bool, expected_calls: int
) -> None:
    probe_warm_ups: list[int] = []
    monkeypatch.setattr(text_utils, "preheat_tiktoken", lambda *_args: True)
    monkeypatch.setattr(env_probe, "warm_up_environment_probe", lambda: probe_warm_ups.append(1))

    one_time_work.start_one_time_work(shell_tools=shell_tools)
    _join(_VOCABULARY_THREAD)

    assert len(probe_warm_ups) == expected_calls


def test_it_returns_while_the_vocabulary_is_still_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    monkeypatch.setattr(text_utils, "preheat_tiktoken", lambda *_args: release.wait(timeout=5))
    monkeypatch.setattr(env_probe, "warm_up_environment_probe", lambda: None)

    started = time.monotonic()
    one_time_work.start_one_time_work(shell_tools=True)
    returned_after = time.monotonic() - started
    release.set()
    _join(_VOCABULARY_THREAD)

    assert returned_after < 2
