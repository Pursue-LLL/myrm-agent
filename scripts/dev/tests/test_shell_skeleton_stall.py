"""Regression tests for R73-A skeleton stall fail-fast."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_bootstrap import CdpChatBootstrap  # noqa: E402
from dev_gate_contract import (  # noqa: E402
    E2E_SHELL_SKELETON_STALL_TOKEN,
    SHELL_PROBE_STALL_FAIL_FAST_SEC,
)


def _bootstrap() -> CdpChatBootstrap:
    return CdpChatBootstrap(MagicMock())


def test_skeleton_stall_clears_when_shell_ready() -> None:
    bootstrap = _bootstrap()
    bootstrap._check_skeleton_stall(
        {"skeleton": True, "hasInput": False},
        phase="unit",
    )
    assert bootstrap._shell_skeleton_since is not None
    bootstrap._check_skeleton_stall(
        {"skeleton": False, "hasInput": True, "hasLayout": True},
        phase="unit",
    )
    assert bootstrap._shell_skeleton_since is None


def test_skeleton_stall_fail_fast_at_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap = _bootstrap()
    start = 10_000.0
    clock = {"now": start}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    bootstrap._check_skeleton_stall(
        {"skeleton": True, "hasInput": False},
        phase="unit",
    )
    clock["now"] = start + float(SHELL_PROBE_STALL_FAIL_FAST_SEC) + 1.0

    with pytest.raises(RuntimeError, match=E2E_SHELL_SKELETON_STALL_TOKEN):
        bootstrap._check_skeleton_stall(
            {"skeleton": True, "hasInput": False},
            phase="unit",
        )
