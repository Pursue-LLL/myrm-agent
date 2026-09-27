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
