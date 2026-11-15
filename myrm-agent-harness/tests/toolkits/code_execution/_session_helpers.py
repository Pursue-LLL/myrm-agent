"""Builders shared by the ``test_persistent_session*.py`` files."""

from __future__ import annotations

import os

from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession, SessionConfig
from myrm_agent_harness.toolkits.code_execution.session.models import SessionState


# Every session writes its tee logs under ``<work_dir>/.myrm/tee``. A test that reads that directory must pass a
# private ``work_dir``: under xdist another worker's sessions share ``/tmp`` and add newer logs to it.
def make_config(timeout: int = 10, work_dir: str = "/tmp") -> SessionConfig:
    return SessionConfig(session_id="test", work_dir=work_dir, timeout=timeout, sandbox_mode="disable")


def state_of(session: LocalPersistentSession) -> SessionState:
    """The state as it is now: mypy keeps narrowing ``session.state`` across awaits that change it."""
    return session.state


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
