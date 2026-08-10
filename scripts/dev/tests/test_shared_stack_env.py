"""Unit tests for stack_mutation_policy._shared_stack_env (§26.28-B)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from stack_mutation_policy import (  # noqa: E402
    _PRIVATE_RUNTIME_ENV_KEYS,
    _shared_stack_env,
)


@pytest.fixture(autouse=True)
def _purge_private_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _PRIVATE_RUNTIME_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_shared_stack_env_purges_all_private_runtime_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", "/tmp/private/kanban-e2e-3")
    monkeypatch.setenv("MYRM_RUNTIME_NAMESPACE", "kanban-e2e-3")
    monkeypatch.setenv("MYRM_BACKEND_PORT", "18088")
    monkeypatch.setenv("E2E_API_BASE", "http://127.0.0.1:18088")
    monkeypatch.setenv(
        "MYRM_STACK_EPOCH_FILE", "/tmp/private/kanban-e2e-3/stack-epoch.json"
    )
    env = _shared_stack_env()
    for key in _PRIVATE_RUNTIME_ENV_KEYS:
        assert key not in env, f"private runtime env key leaked: {key}"


def test_shared_stack_env_preserves_shared_relevant_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_WAVE_GATE_BYPASS", "0")
    monkeypatch.setenv("MYRM_SUPERVISOR_BYPASS", "0")
    env = _shared_stack_env()
    assert env["MYRM_WAVE_GATE_BYPASS"] == "1"
    assert env["MYRM_SUPERVISOR_BYPASS"] == "1"


def test_shared_stack_env_keeps_unrelated_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HOME", "/root")
    env = _shared_stack_env()
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["HOME"] == "/root"
