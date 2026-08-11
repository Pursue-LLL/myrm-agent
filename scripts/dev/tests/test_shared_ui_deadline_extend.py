"""Regression tests for R269 shared UI bridge deadline extension."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from e2e_session_runtime.lifecycle import (  # noqa: E402
    ENV_WALL_PHASE,
    ENV_WALL_STARTED,
    export_session_env,
)
from e2e_shared_ui_session import (
    _extend_shared_ui_deadline_if_wall_allows,
)  # noqa: E402


def test_extend_expired_deadline_when_body_wall_has_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E2E_SIGNOFF", "1")
    env = export_session_env(phase="body")
    monkeypatch.setenv(ENV_WALL_STARTED, env[ENV_WALL_STARTED])
    monkeypatch.setenv(ENV_WALL_PHASE, env[ENV_WALL_PHASE])

    start = float(env[ENV_WALL_STARTED])
    clock = {"now": start + 30.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    expired = start + 5.0
    extended = _extend_shared_ui_deadline_if_wall_allows(expired)
    assert extended is not None
    assert extended > clock["now"]


def test_no_extend_when_wall_budget_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E2E_SIGNOFF", "1")
    env = export_session_env(phase="body")
    monkeypatch.setenv(ENV_WALL_STARTED, env[ENV_WALL_STARTED])
    monkeypatch.setenv(ENV_WALL_PHASE, env[ENV_WALL_PHASE])

    start = float(env[ENV_WALL_STARTED])
    clock = {"now": start + 10_000.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    expired = start + 5.0
    assert _extend_shared_ui_deadline_if_wall_allows(expired) == expired
