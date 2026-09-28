"""Unit tests for DesktopEnvelopeManager and DesktopControlGate envelope integration."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.computer_use.envelope import IntentEnvelopeSpec
from myrm_agent_harness.toolkits.computer_use.types import ForegroundPermissionScope

from app.ai_agents.desktop_control.envelope_manager import DesktopEnvelopeManager
from app.ai_agents.desktop_control.gate import DesktopControlGate


@pytest.fixture
def envelope_manager() -> DesktopEnvelopeManager:
    return DesktopEnvelopeManager()


def test_envelope_manager_registration_and_get(envelope_manager: DesktopEnvelopeManager) -> None:
    spec = IntentEnvelopeSpec(
        task_id="task_calc_1",
        allowed_app_names=("Calculator", "Notes"),
        max_actions=15,
    )
    envelope_manager.register_envelope(spec)

    active = envelope_manager.active_envelope
    assert active is not None
    assert active.task_id == "task_calc_1"
    assert active.max_actions == 15
    assert active.remaining_budget() == 15

    assert envelope_manager.get_envelope("task_calc_1") is active
    envelope_manager.clear_envelope("task_calc_1")
    assert envelope_manager.active_envelope is None


def test_envelope_manager_lease_extension(envelope_manager: DesktopEnvelopeManager) -> None:
    spec = IntentEnvelopeSpec(
        task_id="task_calc_2",
        allowed_app_names=("Calculator",),
        max_actions=10,
        used_actions=8,
    )
    envelope_manager.register_envelope(spec)

    new_limit = envelope_manager.extend_lease(additional_steps=10)
    assert new_limit == 20
    assert spec.max_actions == 20
    assert spec.remaining_budget() == 12


def test_envelope_manager_evaluate_and_consume(envelope_manager: DesktopEnvelopeManager) -> None:
    spec = IntentEnvelopeSpec(
        task_id="task_calc_3",
        allowed_app_names=("Calculator",),
        allowed_app_ids=("com.apple.calculator",),
        max_actions=2,
    )
    envelope_manager.register_envelope(spec)

    # 1. First action in envelope
    allowed, reason, detail = envelope_manager.evaluate_and_consume(
        app_name="Calculator",
        app_id="com.apple.calculator",
        window_title="Calculator",
    )
    assert allowed is True
    assert reason == "ok"
    assert spec.used_actions == 1

    # 2. Second action in envelope
    allowed, reason, detail = envelope_manager.evaluate_and_consume(
        app_name="Calculator",
        app_id="com.apple.calculator",
    )
    assert allowed is True
    assert spec.used_actions == 2

    # 3. Third action exhausts budget
    allowed, reason, detail = envelope_manager.evaluate_and_consume(
        app_name="Calculator",
        app_id="com.apple.calculator",
    )
    assert allowed is False
    assert reason == "budget_exhausted"


def test_envelope_manager_blocks_out_of_boundary_app(envelope_manager: DesktopEnvelopeManager) -> None:
    spec = IntentEnvelopeSpec(
        task_id="task_calc_4",
        allowed_app_names=("Calculator",),
        allowed_app_ids=("com.apple.calculator",),
    )
    envelope_manager.register_envelope(spec)

    allowed, reason, detail = envelope_manager.evaluate_and_consume(
        app_name="Terminal",
        app_id="com.apple.Terminal",
    )
    assert allowed is False
    assert reason == "out_of_boundary"
    assert "outside envelope" in detail


def test_envelope_manager_system_modal_inheritance(envelope_manager: DesktopEnvelopeManager) -> None:
    spec = IntentEnvelopeSpec(
        task_id="task_calc_5",
        allowed_app_names=("Google Chrome",),
        allowed_app_ids=("com.google.Chrome",),
        allow_system_dialogs=True,
    )
    envelope_manager.register_envelope(spec)

    # Modal window with parent Chrome
    allowed, reason, detail = envelope_manager.evaluate_and_consume(
        app_name="Open and Save Panel Service",
        app_id="com.apple.appkit.xpc.openandsavepanelservice",
        parent_app_id="com.google.Chrome",
        is_system_dialog=True,
    )
    assert allowed is True
    assert reason == "ok"


@pytest.mark.asyncio
async def test_gate_with_active_envelope_fast_path(tmp_path: pytest.TempPathFactory) -> None:
    mgr = DesktopEnvelopeManager()
    spec = IntentEnvelopeSpec(
        task_id="task_fast_1",
        allowed_app_names=("TextEdit",),
        allowed_app_ids=("com.apple.TextEdit",),
        max_actions=5,
    )
    mgr.register_envelope(spec)

    gate = DesktopControlGate(
        workspace_root=str(tmp_path),
        envelope_manager=mgr,
        register_live=False,
    )

    # Should grant immediately without hitting SSE / approval sink
    result = await gate(
        reason="Edit note",
        operation="click",
        estimated_duration_seconds=0.5,
        app_name="TextEdit",
        app_id="com.apple.TextEdit",
    )
    assert result.granted is True
    assert result.scope == ForegroundPermissionScope.once
    assert spec.used_actions == 1


@pytest.mark.asyncio
async def test_gate_with_envelope_escalation_on_violation(tmp_path: pytest.TempPathFactory) -> None:
    mgr = DesktopEnvelopeManager()
    spec = IntentEnvelopeSpec(
        task_id="task_fast_2",
        allowed_app_names=("TextEdit",),
        allowed_app_ids=("com.apple.TextEdit",),
        max_actions=5,
    )
    mgr.register_envelope(spec)

    gate = DesktopControlGate(
        workspace_root=str(tmp_path),
        envelope_manager=mgr,
        register_live=False,
    )

    mock_sink = AsyncMock()
    with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=mock_sink):
        # Triggering Terminal should violate envelope and escalate to approval
        task = asyncio.create_task(
            gate(
                reason="Execute script",
                operation="click",
                estimated_duration_seconds=0.5,
                timeout_seconds=0.1,  # Short timeout to fail fast
                app_name="Terminal",
                app_id="com.apple.Terminal",
            )
        )
        res = await task
        assert res.granted is False
        # Verify the approval request was emitted with escalation prefix
        assert mock_sink.emit.called
        req_args = mock_sink.emit.call_args_list[0][0][0]
        assert "[OUT_OF_BOUNDARY]" in req_args["data"]["reason"]


def test_envelope_manager_idle_timeout(envelope_manager: DesktopEnvelopeManager) -> None:
    spec = IntentEnvelopeSpec(
        task_id="task_idle_1",
        allowed_app_names=("Calculator",),
        allowed_app_ids=("com.apple.calculator",),
        idle_timeout_seconds=0.1,  # Short timeout for testing
    )
    envelope_manager.register_envelope(spec)

    # Immediately allowed
    allowed, reason, _ = envelope_manager.evaluate_and_consume(
        app_name="Calculator",
        app_id="com.apple.calculator",
    )
    assert allowed is True
    assert reason == "ok"

    # Simulate idle time passing
    envelope_manager._last_active_by_task[spec.task_id] -= 1.0

    allowed, reason, detail = envelope_manager.evaluate_and_consume(
        app_name="Calculator",
        app_id="com.apple.calculator",
    )
    assert allowed is False
    assert reason == "idle_timeout"
    assert "idle timed out" in detail

    # Extending lease resets the idle timer
    envelope_manager.extend_lease(task_id=spec.task_id)
    allowed, reason, _ = envelope_manager.evaluate_and_consume(
        app_name="Calculator",
        app_id="com.apple.calculator",
    )
    assert allowed is True
    assert reason == "ok"


@pytest.mark.asyncio
async def test_gate_with_envelope_keystroke_violation_escalation(tmp_path: pytest.TempPathFactory) -> None:
    mgr = DesktopEnvelopeManager()
    spec = IntentEnvelopeSpec(
        task_id="task_key_1",
        allowed_app_names=("TextEdit",),
        allowed_app_ids=("com.apple.TextEdit",),
        max_actions=5,
    )
    mgr.register_envelope(spec)

    gate = DesktopControlGate(
        workspace_root=str(tmp_path),
        envelope_manager=mgr,
        register_live=False,
    )

    mock_sink = AsyncMock()
    with patch("app.ai_agents.desktop_control.gate.get_tool_progress_sink", return_value=mock_sink):
        # Typing dangerous command inside allowed app should be caught and escalated
        task = asyncio.create_task(
            gate(
                reason="Execute destructive command",
                operation="type: rm -rf /",
                estimated_duration_seconds=0.5,
                timeout_seconds=0.1,
                app_name="TextEdit",
                app_id="com.apple.TextEdit",
            )
        )
        res = await task
        assert res.granted is False
        assert mock_sink.emit.called
        req_args = mock_sink.emit.call_args_list[0][0][0]
        assert "[KEYSTROKE_VIOLATION]" in req_args["data"]["reason"]


def test_envelope_manager_pause_emergency_stop(envelope_manager: DesktopEnvelopeManager) -> None:
    spec1 = IntentEnvelopeSpec(task_id="t1", allowed_app_names=("TextEdit",), max_actions=10)
    spec2 = IntentEnvelopeSpec(task_id="t2", allowed_app_names=("Notes",), max_actions=10)
    envelope_manager.register_envelope(spec1)
    envelope_manager.register_envelope(spec2)

    # Emergency pause t1 only
    paused = envelope_manager.pause_envelope(task_id="t1")
    assert paused is True
    assert envelope_manager.get_envelope("t1") is None
    # t2 remains active
    assert envelope_manager.get_envelope("t2") is not None

    # Global emergency pause
    paused_all = envelope_manager.pause_envelope()
    assert paused_all is True
    assert envelope_manager.active_envelope is None
    assert envelope_manager.get_envelope("t2") is None


@pytest.mark.asyncio
async def test_gate_envelope_task_id_isolation(tmp_path: pytest.TempPathFactory) -> None:
    mgr = DesktopEnvelopeManager()
    spec1 = IntentEnvelopeSpec(task_id="task_A", allowed_app_names=("TextEdit",), max_actions=5)
    spec2 = IntentEnvelopeSpec(task_id="task_B", allowed_app_names=("Notes",), max_actions=5)
    mgr.register_envelope(spec1)
    mgr.register_envelope(spec2)

    gate_a = DesktopControlGate(
        workspace_root=str(tmp_path),
        envelope_manager=mgr,
        register_live=False,
        task_id="task_A",
    )
    gate_b = DesktopControlGate(
        workspace_root=str(tmp_path),
        envelope_manager=mgr,
        register_live=False,
        task_id="task_B",
    )

    # Gate A operates on TextEdit under task_A
    res_a = await gate_a(
        reason="Edit file",
        operation="type: hello",
        estimated_duration_seconds=0.1,
        app_name="TextEdit",
        app_id="com.apple.TextEdit",
    )
    assert res_a.granted is True
    assert spec1.used_actions == 1
    assert spec2.used_actions == 0

    # Gate B operates on Notes under task_B
    res_b = await gate_b(
        reason="Take note",
        operation="type: world",
        estimated_duration_seconds=0.1,
        app_name="Notes",
        app_id="com.apple.Notes",
    )
    assert res_b.granted is True
    assert spec1.used_actions == 1
    assert spec2.used_actions == 1


@pytest.mark.asyncio
async def test_envelope_manager_emit_progress_payload() -> None:
    from myrm_agent_harness.core.events.types import AgentEventType

    mgr = DesktopEnvelopeManager()
    spec = IntentEnvelopeSpec(task_id="t_emit", allowed_app_names=("TextEdit",), max_actions=10, used_actions=3)
    mgr.register_envelope(spec)

    mock_sink = AsyncMock()
    with patch("app.ai_agents.desktop_control.envelope_manager.get_tool_progress_sink", return_value=mock_sink):
        await mgr.emit_progress(task_id="t_emit")
        assert mock_sink.emit.called
        event = mock_sink.emit.call_args[0][0]
        assert event["type"] == AgentEventType.DESKTOP_ENVELOPE_PROGRESS
        data = event["data"]
        assert data["task_id"] == "t_emit"
        assert data["used_actions"] == 3
        assert data["max_actions"] == 10
        assert data["remaining_budget"] == 7
        assert data["can_extend"] is True



