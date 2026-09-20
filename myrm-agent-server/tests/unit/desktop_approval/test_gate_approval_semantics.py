"""Unit tests for desktop approval semantics: fingerprint binding, durable deny,
deny-first order, settlement tri-state, registry bounds, and grant audit."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai_agents.desktop_control.gate import DesktopControlGate
from app.ai_agents.desktop_control.registry import (
    DesktopApprovalRegistry,
    approval_fingerprint,
    resolve_desktop_control_approval,
    resolve_desktop_control_approval_status,
)


def _run(coro):
    return asyncio.run(coro)


def _sink():
    sink = MagicMock()
    sink.emit = AsyncMock()
    return sink


def _fresh_gate(**kwargs):
    kwargs.setdefault("workspace_root", None)
    kwargs.setdefault("register_live", False)
    return DesktopControlGate(**kwargs)


def _request_id_of(sink) -> str:
    assert sink.emit.await_args_list, "expected an approval request emit"
    return sink.emit.await_args_list[0].args[0]["data"]["request_id"]


def _call(gate, sink, *, app_name="TextEdit", operation="interact", timeout=2.0):
    async def _go():
        with patch(
            "app.ai_agents.desktop_control.gate.get_tool_progress_sink",
            return_value=sink,
        ):
            return await gate(
                reason="test",
                operation=operation,
                estimated_duration_seconds=1.0,
                timeout_seconds=timeout,
                app_name=app_name,
            )

    return _go()


def _resolve_when_emitted(sink, *, granted, scope="once", reason=""):
    async def _go():
        for _ in range(200):
            if sink.emit.await_args_list:
                break
            await asyncio.sleep(0.005)
        request_id = _request_id_of(sink)
        resolve_desktop_control_approval(request_id, granted=granted, scope=scope, reason=reason)

    return _go()


def test_fingerprint_stable_and_scoped():
    fp1 = approval_fingerprint(operation="click", trust_key="textedit")
    fp2 = approval_fingerprint(operation="click", trust_key="textedit")
    assert fp1 == fp2
    assert approval_fingerprint(operation="type", trust_key="textedit") != fp1
    assert approval_fingerprint(operation="click", trust_key="safari") != fp1
    # Volatile presentation must not participate: same op+app is stable.
    assert len(fp1) == 16


def test_explicit_deny_is_session_final():
    DesktopApprovalRegistry._pending.clear()
    gate = _fresh_gate()
    sink = _sink()
    result = _run(_settle(_call(gate, sink), _resolve_when_emitted(sink, granted=False)))
    assert result.granted is False
    # Same app+operation is denied without a second prompt.
    sink2 = _sink()
    again = _run(_call(gate, sink2))
    assert again.granted is False
    assert sink2.emit.await_count == 0


def _settle(call_coro, resolve_coro):
    async def _go():
        task = asyncio.create_task(resolve_coro)
        result = await call_coro
        await task
        return result

    return _go()


def test_timeout_does_not_durable_deny():
    DesktopApprovalRegistry._pending.clear()
    gate = _fresh_gate()
    sink = _sink()
    result = _run(_call(gate, sink, timeout=0.05))
    assert result.granted is False
    # A timeout is not a user decision: the next request prompts again.
    sink2 = _sink()
    _run(_drain_emit_then_cancel(sink2, lambda: _call(gate, sink2, timeout=2.0)))
    assert sink2.emit.await_count == 1


async def _drain_emit_then_cancel(sink, call_factory):
    task = asyncio.ensure_future(call_factory())
    for _ in range(200):
        if sink.emit.await_args_list:
            break
        await asyncio.sleep(0.005)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


def test_deny_first_beats_session_cache():
    DesktopApprovalRegistry._pending.clear()
    gate = _fresh_gate()
    # Explicitly deny one operation on the app first (via prompt).
    sink = _sink()
    denied = _run(
        _settle(
            _call(gate, sink, operation="delete"),
            _resolve_when_emitted(sink, granted=False, reason="too risky"),
        )
    )
    assert denied.granted is False
    # Session-approve the same app via a different operation.
    sink2 = _sink()
    _run(
        _settle(
            _call(gate, sink2, operation="read"),
            _resolve_when_emitted(sink2, granted=True, scope="session"),
        )
    )
    # The denied (app, operation) pair stays denied without prompting...
    sink3 = _sink()
    assert _run(_call(gate, sink3, operation="delete")).granted is False
    assert sink3.emit.await_count == 0
    # ...while other operations on the session-approved app still pass.
    sink4 = _sink()
    assert _run(_call(gate, sink4, operation="read")).granted is True
    assert sink4.emit.await_count == 0
    DesktopApprovalRegistry._pending.clear()


def test_resolve_status_tristate():
    DesktopApprovalRegistry._pending.clear()
    DesktopApprovalRegistry._tombstones.clear()
    request_id, _pending = DesktopApprovalRegistry.create(reason="t", operation="op", app_name="App", fingerprint="fp")
    assert resolve_desktop_control_approval_status(request_id, granted=True, scope="once") == "resolved"
    assert resolve_desktop_control_approval_status(request_id, granted=True, scope="once") == "missing"
    request_id2, _pending2 = DesktopApprovalRegistry.create(reason="t", operation="op", app_name="App", fingerprint="fp")
    assert DesktopApprovalRegistry._settle_timeout(request_id2) is True
    assert resolve_desktop_control_approval_status(request_id2, granted=True, scope="once") == "expired"
    # First settlement wins: a late resolve loses to the timeout.
    assert resolve_desktop_control_approval(request_id2, granted=True, scope="once") is False


def test_resolve_bool_contract_preserved():
    DesktopApprovalRegistry._pending.clear()
    assert resolve_desktop_control_approval("missing-id", granted=True, scope="once") is False


def test_registry_cap_evicts_oldest_fail_closed():
    DesktopApprovalRegistry._pending.clear()
    DesktopApprovalRegistry._tombstones.clear()
    import app.ai_agents.desktop_control.registry as registry_mod

    old_max = registry_mod._MAX_PENDING
    registry_mod._MAX_PENDING = 3
    try:
        ids = [DesktopApprovalRegistry.create(reason="t", operation="op")[0] for _ in range(4)]
        assert len(DesktopApprovalRegistry._pending) == 3
        assert ids[0] not in DesktopApprovalRegistry._pending
        assert resolve_desktop_control_approval_status(ids[0], granted=True, scope="once") == "expired"
    finally:
        registry_mod._MAX_PENDING = old_max
        DesktopApprovalRegistry._pending.clear()
        DesktopApprovalRegistry._tombstones.clear()


def test_last_grants_bounded_at_capacity():
    import app.ai_agents.desktop_control.gate as gate_mod

    DesktopApprovalRegistry._pending.clear()
    gate = _fresh_gate()
    old_max = gate_mod._MAX_GRANTS
    gate_mod._MAX_GRANTS = 3
    try:
        for index in range(5):
            sink = _sink()
            _run(
                _settle(
                    _call(gate, sink, app_name=f"App{index}", operation="click"),
                    _resolve_when_emitted(sink, granted=True, scope="once"),
                )
            )
        assert len(gate._last_grants) == 3
        assert "app0" not in gate._last_grants
        assert "app4" in gate._last_grants
    finally:
        gate_mod._MAX_GRANTS = old_max
        DesktopApprovalRegistry._pending.clear()


def test_changed_flag_on_fingerprint_drift():
    DesktopApprovalRegistry._pending.clear()
    gate = _fresh_gate()
    sink = _sink()
    _run(
        _settle(
            _call(gate, sink, operation="click"),
            _resolve_when_emitted(sink, granted=True, scope="once"),
        )
    )
    sink2 = _sink()
    _run(_drain_emit_then_cancel(sink2, lambda: _call(gate, sink2, operation="delete")))
    data = sink2.emit.await_args_list[0].args[0]["data"]
    assert data["changed_since_last_grant"] is True
    assert data["fingerprint"]
    DesktopApprovalRegistry._pending.clear()


def test_persistent_deny_file(tmp_path):
    store = Path(str(tmp_path)) / ".agent" / "desktop_control"
    store.mkdir(parents=True)

    (store / "denied_apps.json").write_text(json.dumps({"denied": ["textedit"]}), encoding="utf-8")
    gate = DesktopControlGate(workspace_root=str(tmp_path), register_live=False)
    sink = _sink()
    assert _run(_call(gate, sink)).granted is False
    assert sink.emit.await_count == 0


def test_reset_clears_session_deny_keeps_persistent(tmp_path):
    store = Path(str(tmp_path)) / ".agent" / "desktop_control"
    store.mkdir(parents=True)
    (store / "denied_apps.json").write_text(json.dumps({"denied": ["safari"]}), encoding="utf-8")
    DesktopApprovalRegistry._pending.clear()
    gate = DesktopControlGate(workspace_root=str(tmp_path), register_live=False)
    sink = _sink()
    _run(
        _settle(
            _call(gate, sink, app_name="TextEdit"),
            _resolve_when_emitted(sink, granted=False),
        )
    )
    gate.reset_runtime_approval_state()
    # Session deny cleared: prompts again.
    sink2 = _sink()
    _run(_drain_emit_then_cancel(sink2, lambda: _call(gate, sink2, app_name="TextEdit", timeout=2.0)))
    assert sink2.emit.await_count == 1
    DesktopApprovalRegistry._pending.clear()
    # Persistent deny survives the reset.
    sink3 = _sink()
    assert _run(_call(gate, sink3, app_name="Safari")).granted is False
    assert sink3.emit.await_count == 0


def test_auto_grant_records_audit():
    DesktopApprovalRegistry._decisions.clear()
    gate = DesktopControlGate(workspace_root=None, register_live=False, auto_grant=True)
    result = _run(_call(gate, _sink()))
    assert result.granted is True
    decisions = DesktopApprovalRegistry.decision_snapshot()
    assert decisions and decisions[-1]["decision"] == "auto_granted"
    DesktopApprovalRegistry._decisions.clear()


def test_deny_reason_recorded_in_decisions():
    DesktopApprovalRegistry._pending.clear()
    DesktopApprovalRegistry._decisions.clear()
    gate = _fresh_gate()
    sink = _sink()
    _run(
        _settle(
            _call(gate, sink),
            _resolve_when_emitted(sink, granted=False, reason="not now"),
        )
    )
    decisions = DesktopApprovalRegistry.decision_snapshot()
    assert decisions and decisions[-1]["decision"] == "denied"
    assert decisions[-1]["reason"] == "not now"
    DesktopApprovalRegistry._decisions.clear()
