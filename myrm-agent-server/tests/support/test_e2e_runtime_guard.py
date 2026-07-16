"""Tests for the mandatory live-E2E lease and runtime guard."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.support.e2e_runtime_guard import (
    assert_e2e_runtime_unchanged,
    heartbeat_e2e_lease,
    register_e2e_resource,
    require_e2e_runtime_lease,
)


def test_heartbeat_noop_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_E2E_LEASE_ID", raising=False)
    monkeypatch.delenv("MYRM_E2E_AGENT_ID", raising=False)
    heartbeat_e2e_lease()


def test_register_e2e_resource_rejects_empty_ref() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        register_e2e_resource("lease-1", kind="chat", ref="  ", namespace="ns")


def test_register_e2e_resource_noop_on_inactive_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tests.support.e2e_runtime_guard.subprocess.run",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {"returncode": 1, "stderr": "LEDGER_DENIED: active lease not found: lease-1", "stdout": ""},
        )(),
    )
    register_e2e_resource("lease-1", kind="chat", ref="chat-1", namespace="ns")


def _write_state(
    tmp_path: Path,
    *,
    lease_id: str = "lease-1",
    runtime_id: str = "runtime-1",
    lane: str = "LIVE_AGENT",
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "wave-orchestrator.json").write_text(
        json.dumps(
            {
                "version": 2,
                "wave": {"status": "open", "runtimeId": runtime_id},
                "leases": [
                    {
                        "leaseId": lease_id,
                        "agentId": "test-agent",
                        "lane": lane,
                        "runtimeId": runtime_id,
                        "status": "active",
                        "expiresAt": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                    }
                ],
                "resources": [],
            }
        ),
        encoding="utf-8",
    )


def test_requires_lease_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_E2E_LEASE_ID", raising=False)
    with pytest.raises(RuntimeError, match="E2E_LEASE_REQUIRED"):
        require_e2e_runtime_lease(runtime_id_reader=lambda: "runtime-1")


def test_accepts_active_live_agent_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_state(tmp_path)
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-1")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", "test-agent")

    lease = require_e2e_runtime_lease(runtime_id_reader=lambda: "runtime-1")

    assert lease.lease_id == "lease-1"
    assert lease.runtime_id == "runtime-1"
    assert lease.lane == "LIVE_AGENT"


def test_accepts_declared_read_only_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_state(tmp_path, lane="READ")
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-1")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", "test-agent")
    monkeypatch.setenv("MYRM_E2E_LANE", "READ")

    lease = require_e2e_runtime_lease(runtime_id_reader=lambda: "runtime-1")

    assert lease.lane == "READ"


def test_accepts_declared_global_write_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_state(tmp_path, lane="GLOBAL_WRITE")
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-1")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", "test-agent")
    monkeypatch.setenv("MYRM_E2E_LANE", "GLOBAL_WRITE")

    lease = require_e2e_runtime_lease(runtime_id_reader=lambda: "runtime-1")

    assert lease.lane == "GLOBAL_WRITE"


def test_rejects_lane_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_state(tmp_path, lane="READ")
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-1")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", "test-agent")
    monkeypatch.setenv("MYRM_E2E_LANE", "LIVE_AGENT")

    with pytest.raises(RuntimeError, match="does not match MYRM_E2E_LANE"):
        require_e2e_runtime_lease(runtime_id_reader=lambda: "runtime-1")


def test_rejects_runtime_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_state(tmp_path)
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-1")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", "test-agent")

    with pytest.raises(RuntimeError, match="RUNTIME_DRIFT"):
        require_e2e_runtime_lease(runtime_id_reader=lambda: "runtime-2")

    lease = require_e2e_runtime_lease(runtime_id_reader=lambda: "runtime-1")
    with pytest.raises(RuntimeError, match="RUNTIME_DRIFT"):
        assert_e2e_runtime_unchanged(lease, runtime_id_reader=lambda: "runtime-2")


def test_private_backend_reads_shared_wave_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_state = tmp_path / "private-state"
    private_state.mkdir()
    wave_state = tmp_path / "wave-state"
    wave_state.mkdir()
    (wave_state / "wave-orchestrator.json").write_text(
        json.dumps(
            {
                "version": 2,
                "wave": {"status": "open", "runtimeId": "runtime-1"},
                "leases": [
                    {
                        "leaseId": "lease-1",
                        "agentId": "test-agent",
                        "lane": "LIVE_AGENT",
                        "runtimeId": "runtime-1",
                        "status": "active",
                        "expiresAt": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                    }
                ],
                "resources": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(private_state))
    monkeypatch.setenv("MYRM_WAVE_STATE_DIR", str(wave_state))
    monkeypatch.setenv("MYRM_E2E_PRIVATE_RUNTIME_ID", "myrm-test-private")
    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-1")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", "test-agent")

    lease = require_e2e_runtime_lease(runtime_id_reader=lambda: "runtime-1")

    assert lease.lease_id == "lease-1"
    assert (private_state / "wave-orchestrator.json").exists() is False


def test_isolated_mode_uses_stack_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_state(tmp_path)
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-1")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", "test-agent")
    monkeypatch.setenv("MYRM_E2E_ISOLATED", "1")
    monkeypatch.setenv("MYRM_E2E_STACK_FP", "stack-fp-abc")
    monkeypatch.setattr(
        "tests.support.e2e_runtime_guard._stack_scoped_runtime_id",
        lambda: "stack-fp-abc",
    )

    lease = require_e2e_runtime_lease()
    assert lease.runtime_id == "stack-fp-abc"
    assert_e2e_runtime_unchanged(lease)


def test_shared_hot_stack_fp_pins_runtime_for_shpoib(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_state(tmp_path, runtime_id="shared-hot-runtime")
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-1")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", "test-agent")
    monkeypatch.setenv("MYRM_E2E_STACK_FP", "shared-hot-runtime")
    monkeypatch.setenv("MYRM_E2E_PRIVATE_BACKEND", "1")

    lease = require_e2e_runtime_lease()
    assert lease.runtime_id == "shared-hot-runtime"
    assert_e2e_runtime_unchanged(lease)
