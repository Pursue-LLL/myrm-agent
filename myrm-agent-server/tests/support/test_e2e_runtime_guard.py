"""Tests for the mandatory live-E2E lease and runtime guard."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from e2e_resource_ledger import register_e2e_resource

from tests.support.e2e_runtime_guard import (
    assert_chrome_attach_health,
    assert_e2e_runtime_unchanged,
    heartbeat_e2e_lease,
    reap_chrome_e2e_session_hygiene,
    require_e2e_runtime_lease,
)


def test_heartbeat_noop_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_E2E_LEASE_ID", raising=False)
    monkeypatch.delenv("MYRM_E2E_AGENT_ID", raising=False)
    heartbeat_e2e_lease()


def test_heartbeat_swallows_wave_subprocess_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    import e2e_unified_heartbeat as unified_module

    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-timeout")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", "agent-timeout")

    def _timeout_run(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["wave.sh"], timeout=30)

    monkeypatch.setattr(unified_module.subprocess, "run", _timeout_run)
    heartbeat_e2e_lease()


def test_heartbeat_loop_extends_lease_without_peer_reaper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    import e2e_unified_heartbeat

    from tests.support.e2e_runtime_guard import e2e_lease_heartbeat_loop

    heartbeat_calls: list[int] = []

    def _fake_heartbeat(**kwargs: object) -> None:
        heartbeat_calls.append(1)

    monkeypatch.delenv("MYRM_E2E_SESSION_HEARTBEAT_PID", raising=False)
    monkeypatch.setattr(e2e_unified_heartbeat, "heartbeat_once", _fake_heartbeat)
    with e2e_lease_heartbeat_loop(interval_sec=0.05):
        time.sleep(0.12)
    assert len(heartbeat_calls) >= 2


def test_heartbeat_loop_skips_thread_when_shell_loop_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading
    import time

    import e2e_unified_heartbeat

    from tests.support.e2e_runtime_guard import e2e_lease_heartbeat_loop

    heartbeat_calls: list[int] = []

    def _fake_heartbeat(**kwargs: object) -> None:
        heartbeat_calls.append(1)

    monkeypatch.setenv("MYRM_E2E_SESSION_HEARTBEAT_PID", str(os.getpid()))
    monkeypatch.setattr(e2e_unified_heartbeat, "heartbeat_once", _fake_heartbeat)
    before = threading.active_count()
    with e2e_lease_heartbeat_loop(interval_sec=0.05):
        time.sleep(0.08)
    after = threading.active_count()
    assert len(heartbeat_calls) == 2
    assert after == before


def test_assert_chrome_attach_health_passes_on_ready_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def _fake_run(cmd: list[str], **kwargs: object) -> object:
        captured.append(list(cmd))
        return type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr("tests.support.e2e_runtime_guard.subprocess.run", _fake_run)
    assert_chrome_attach_health()
    assert captured
    assert "--require-attach-ready" in captured[0]


def test_assert_chrome_attach_health_signoff_uses_stream_ready_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def _fake_run(cmd: list[str], **kwargs: object) -> object:
        captured.append(list(cmd))
        return type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setenv("E2E_SIGNOFF", "1")
    monkeypatch.setattr("tests.support.e2e_runtime_guard.subprocess.run", _fake_run)
    assert_chrome_attach_health()
    assert captured
    assert "--require-signoff-stream-ready" in captured[0]
    assert "--require-attach-ready" not in captured[0]


def test_assert_chrome_attach_health_raises_when_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_CHROME_E2E_ATTACH_WAIT_SEC", "0")
    monkeypatch.setattr(
        "tests.support.e2e_runtime_guard.subprocess.run",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {"returncode": 1, "stderr": "mux not ready", "stdout": ""},
        )(),
    )
    with pytest.raises(
        RuntimeError, match="CHROME_E2E_ATTACH_NOT_READY: mux not ready"
    ):
        assert_chrome_attach_health()


def test_reap_chrome_e2e_session_hygiene_is_heartbeat_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeat_calls = 0

    def _fake_heartbeat() -> None:
        nonlocal heartbeat_calls
        heartbeat_calls += 1

    monkeypatch.setattr(
        "tests.support.e2e_runtime_guard.heartbeat_e2e_lease",
        _fake_heartbeat,
    )
    monkeypatch.setattr(
        "tests.support.e2e_runtime_guard.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subprocess.run must not be called")
        ),
    )
    reap_chrome_e2e_session_hygiene()
    assert heartbeat_calls == 1


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
            {
                "returncode": 1,
                "stderr": "LEDGER_DENIED: active lease not found: lease-1",
                "stdout": "",
            },
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
                        "expiresAt": (
                            datetime.now(UTC) + timedelta(minutes=5)
                        ).isoformat(),
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
                        "expiresAt": (
                            datetime.now(UTC) + timedelta(minutes=5)
                        ).isoformat(),
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


def test_private_backend_ignores_shared_hot_runtime_drift_under_parallel_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_state(tmp_path, runtime_id="private-runtime-b219")
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-1")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", "test-agent")
    monkeypatch.setenv("MYRM_E2E_STACK_FP", "private-runtime-b219")
    monkeypatch.setenv("MYRM_E2E_PRIVATE_BACKEND", "1")
    monkeypatch.setattr(
        "tests.support.e2e_runtime_guard._shared_hot_stack_runtime_id",
        lambda: "parallel-runtime-73fc",
    )

    lease = require_e2e_runtime_lease()
    assert lease.runtime_id == "private-runtime-b219"
    assert_e2e_runtime_unchanged(lease)


def test_formal_chrome_e2e_auto_heals_stale_lease_on_runtime_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0-A: drift heal reads state file updated by Coordinator (no subprocess reap).

    Scenario: Coordinator has already healed the state file (runtime-healed).
    The test process reads the healed state and succeeds without invoking subprocess.
    """
    agent_id = "e2e-parent-48344-49446-ea479a04"
    _write_state(tmp_path, runtime_id="runtime-healed")
    state_dir = tmp_path / "state"
    state_path = state_dir / "wave-orchestrator.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    for item in payload.get("leases", []):
        if isinstance(item, dict):
            item["agentId"] = agent_id
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(state_dir))
    monkeypatch.setenv("MYRM_E2E_LEASE_ID", "lease-1")
    monkeypatch.setenv("MYRM_E2E_AGENT_ID", agent_id)
    monkeypatch.setenv("MYRM_E2E_STACK_FP", "runtime-healed")

    monkeypatch.setattr(
        "tests.support.e2e_runtime_guard.heartbeat_e2e_lease",
        lambda: None,
    )
    monkeypatch.setattr(
        "tests.support.e2e_runtime_guard.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("P0-A: subprocess.run must not be called for wave reap")
        ),
    )
    monkeypatch.setattr(
        "tests.support.e2e_runtime_guard._shared_hot_stack_runtime_id",
        lambda: "runtime-healed",
    )

    lease = require_e2e_runtime_lease()
    assert lease.runtime_id == "runtime-healed"
    assert_e2e_runtime_unchanged(lease)


def test_e2e_lock_holder_roundtrip(tmp_path: Path) -> None:
    from tests.support.e2e_parallel_snapshot import (
        clear_e2e_lock_holder,
        read_e2e_lock_holder,
        write_e2e_lock_holder,
    )

    lock_path = tmp_path / "myrm-live-agent-stream.lock"
    write_e2e_lock_holder(lock_path, "tests/e2e/demo.py::test_demo")
    holder = read_e2e_lock_holder(lock_path)
    assert holder is not None
    assert holder.pid == os.getpid()
    assert holder.label == "tests/e2e/demo.py::test_demo"
    clear_e2e_lock_holder(lock_path)
    assert read_e2e_lock_holder(lock_path) is None


def test_snapshot_live_e2e_processes_reads_session_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify snapshot_live_e2e_processes reads session snapshots + lock holders."""
    from tests.support.e2e_parallel_snapshot import snapshot_live_e2e_processes

    monkeypatch.setenv("TMPDIR", str(tmp_path))

    stream_lock = tmp_path / "myrm-live-agent-stream.lock"
    desktop_lock = tmp_path / "myrm-desktop-approval-e2e.lock"
    write_holder = tmp_path / "myrm-live-agent-stream.lock.holder"
    write_holder.write_text(
        f"{os.getpid()}:tests/e2e/holder.py::test_holder\n", encoding="utf-8"
    )

    session_dir = tmp_path / "myrm-e2e-session"
    session_dir.mkdir()
    (session_dir / f"{os.getpid()}.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "phase": "body",
                "node": "tests/e2e/test_demo.py::test_demo",
                "started_at": "2026-08-01T12:00:00Z",
                "heartbeat_at": "2026-08-01T12:00:30Z",
            }
        ),
        encoding="utf-8",
    )

    def _fake_run(cmd: list[str], **kwargs: object) -> object:
        return type("Result", (), {"returncode": 1, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("e2e_session_registry.subprocess.run", _fake_run)

    snapshot = snapshot_live_e2e_processes(
        agent_stream_lock_path=stream_lock,
        desktop_approval_lock_path=desktop_lock,
    )
    assert snapshot.agent_stream_lock is not None
    assert snapshot.agent_stream_lock.pid == os.getpid()
    assert len(snapshot.active_tests) >= 1
    active_pids = {t.pid for t in snapshot.active_tests}
    assert os.getpid() in active_pids


def test_snapshot_live_e2e_processes_empty_when_no_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify empty snapshot when no session files exist."""
    from tests.support.e2e_parallel_snapshot import snapshot_live_e2e_processes

    monkeypatch.setenv("TMPDIR", str(tmp_path))

    stream_lock = tmp_path / "myrm-live-agent-stream.lock"
    desktop_lock = tmp_path / "myrm-desktop-approval-e2e.lock"

    def _fake_run(cmd: list[str], **kwargs: object) -> object:
        return type("Result", (), {"returncode": 1, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("e2e_session_registry.subprocess.run", _fake_run)

    snapshot = snapshot_live_e2e_processes(
        agent_stream_lock_path=stream_lock,
        desktop_approval_lock_path=desktop_lock,
    )
    assert snapshot.agent_stream_lock is None
    assert len(snapshot.active_tests) == 0
