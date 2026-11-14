"""Only the browser main processes of the dead driver's token are ended; nothing else is touched.

The scan reads the real process table, so these tests start real processes: bare Python sleepers whose command line
and environment are those of a browser main process started under a driver (or deliberately not).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from types import TracebackType
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.browser.pool import driver_leftovers
from myrm_agent_harness.toolkits.browser.pool.driver_leftovers import (
    DRIVER_ENV_VAR,
    new_driver_token,
    terminate_driver_browsers,
)

_BROWSER_FLAG = "--remote-debugging-pipe"
_HELPER_FLAG = "--type=renderer"
_SLEEPER = "import time\nprint('ready', flush=True)\ntime.sleep(300)\n"
_SETTLE_S = 0.5
_GONE_TIMEOUT_S = 5.0


class _Sleepers:
    """Spawns sleeping children and kills every one of them when the block ends."""

    def __init__(self) -> None:
        self._children: list[subprocess.Popen[str]] = []

    def spawn(self, *, token: str | None, flag: bool = True, helper: bool = False) -> subprocess.Popen[str]:
        """A child carrying ``token`` in its environment (none when ``None``).

        It has the browser flag unless ``flag`` is off, and is marked as a helper of a browser when ``helper`` is on.
        """
        env = {key: value for key, value in os.environ.items() if key != DRIVER_ENV_VAR}
        if token is not None:
            env[DRIVER_ENV_VAR] = token
        args = [
            sys.executable,
            "-u",
            "-c",
            _SLEEPER,
            *([_BROWSER_FLAG] if flag else []),
            *([_HELPER_FLAG] if helper else []),
        ]
        child = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, text=True)
        self._children.append(child)
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        return child

    def __enter__(self) -> _Sleepers:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        for child in self._children:
            if child.poll() is None:
                child.kill()
            child.wait()
            if child.stdout is not None:
                child.stdout.close()


@pytest.fixture
def sleepers() -> Iterator[_Sleepers]:
    with _Sleepers() as children:
        yield children


def _gone(child: subprocess.Popen[str]) -> bool:
    deadline = time.monotonic() + _GONE_TIMEOUT_S
    while time.monotonic() < deadline:
        if child.poll() is not None:
            return True
        time.sleep(0.02)
    return child.poll() is not None


async def test_the_browser_main_process_of_the_token_is_killed(sleepers: _Sleepers) -> None:
    token = new_driver_token()
    browser = sleepers.spawn(token=token)

    assert await terminate_driver_browsers(token) == 1

    assert _gone(browser)


async def test_every_browser_the_driver_started_is_killed(sleepers: _Sleepers) -> None:
    token = new_driver_token()
    browsers = [sleepers.spawn(token=token), sleepers.spawn(token=token)]

    assert await terminate_driver_browsers(token) == 2

    assert all(_gone(browser) for browser in browsers)


async def test_a_helper_of_the_browser_is_left_to_exit_with_its_main_process(sleepers: _Sleepers) -> None:
    """Renderers carry the pipe flag and the environment too; only the main process is signalled."""
    token = new_driver_token()
    browser = sleepers.spawn(token=token)
    renderer = sleepers.spawn(token=token, helper=True)

    assert await terminate_driver_browsers(token) == 1

    assert _gone(browser)
    time.sleep(_SETTLE_S)
    assert renderer.poll() is None


async def test_a_process_that_is_not_a_browser_of_that_driver_is_left_alone(sleepers: _Sleepers) -> None:
    token = new_driver_token()
    bystanders = {
        "an application the browser handed a link to inherits the environment but is no browser main process": (
            sleepers.spawn(token=token, flag=False)
        ),
        "a browser another driver started": sleepers.spawn(token=new_driver_token()),
        "a browser no driver of this toolkit started": sleepers.spawn(token=None),
    }

    assert await terminate_driver_browsers(token) == 0

    time.sleep(_SETTLE_S)
    survivors = {why: child.poll() is None for why, child in bystanders.items()}
    assert all(survivors.values()), survivors


async def test_nothing_is_killed_when_no_process_carries_the_token() -> None:
    assert await terminate_driver_browsers(new_driver_token()) == 0


async def test_without_psutil_there_is_nothing_to_kill(sleepers: _Sleepers) -> None:
    token = new_driver_token()
    browser = sleepers.spawn(token=token)

    with patch.dict("sys.modules", {"psutil": None}):
        assert await terminate_driver_browsers(token) == 0

    time.sleep(_SETTLE_S)
    assert browser.poll() is None


async def test_a_scan_that_fails_is_logged_and_never_raised(caplog: pytest.LogCaptureFixture) -> None:
    """The scan runs inside the recovery from a driver exit; a failed cleanup must not fail that recovery."""
    with (
        patch.object(driver_leftovers, "_kill_main_processes", side_effect=RuntimeError("process table unreadable")),
        caplog.at_level(logging.WARNING, logger=driver_leftovers.__name__),
    ):
        assert await terminate_driver_browsers(new_driver_token()) == 0

    assert "Could not look for browsers left behind" in caplog.text


async def test_killed_browsers_are_reported(sleepers: _Sleepers, caplog: pytest.LogCaptureFixture) -> None:
    token = new_driver_token()
    sleepers.spawn(token=token)

    with caplog.at_level(logging.WARNING, logger=driver_leftovers.__name__):
        await terminate_driver_browsers(token)

    assert "Killed 1 browser(s) left running by an exited Playwright driver" in caplog.text


def test_driver_tokens_are_never_shared() -> None:
    tokens = {new_driver_token() for _ in range(200)}

    assert len(tokens) == 200
    assert all(token and token.isalnum() for token in tokens)
