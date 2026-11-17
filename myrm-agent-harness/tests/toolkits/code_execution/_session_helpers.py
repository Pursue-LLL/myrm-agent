"""Builders and probes shared by the persistent-session and shell-flavor tests."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from unittest.mock import patch

from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession, SessionConfig
from myrm_agent_harness.toolkits.code_execution.session.models import SessionState

# The line that closes the command block of ``BashFlavor.build_wrapped_command`` and seals its stdin.
BASH_BLOCK_CLOSE = "} </dev/null"


# Every session writes its tee logs under ``<work_dir>/.myrm/tee``. A test that reads that directory must pass a
# private ``work_dir``: under xdist another worker's sessions share ``/tmp`` and add newer logs to it.
def make_config(timeout: int = 10, work_dir: str = "/tmp") -> SessionConfig:
    return SessionConfig(session_id="test", work_dir=work_dir, timeout=timeout, sandbox_mode="disable")


def state_of(session: LocalPersistentSession) -> SessionState:
    """The state as it is now: mypy keeps narrowing ``session.state`` across awaits that change it."""
    return session.state


@contextlib.contextmanager
def captured_stdout_chunks() -> Iterator[list[str]]:
    """The live ``tool_stdout_chunk`` text the commands run inside the block emit, in emission order."""
    chunks: list[str] = []

    async def capture(event_type: str, data: dict[str, str]) -> None:
        if event_type == "tool_stdout_chunk":
            chunks.append(data["chunk"])

    with patch("myrm_agent_harness.utils.event_utils.dispatch_custom_event", side_effect=capture):
        yield chunks


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def split_bash_wrapper(wrapped: str) -> tuple[list[str], list[str], list[str]]:
    """The lines before, inside and after the command block of a wrapped bash command.

    The block ends at the line that seals its stdin, so a wrapper without that line cannot be split.
    """
    lines = wrapped.splitlines()
    start = lines.index("{")
    end = lines.index(BASH_BLOCK_CLOSE)
    return lines[:start], lines[start + 1 : end], lines[end + 1 :]
