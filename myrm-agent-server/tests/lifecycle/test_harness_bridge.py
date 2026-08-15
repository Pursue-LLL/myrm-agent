import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.runtime.events.skill_events import SkillFailureEvent
from myrm_agent_harness.runtime.events.system_events import (
    DelegationPolicyDecision,
    LocatorSelfHealedEvent,
    MCPAuthExpiredEvent,
    ResourceMetricsEvent,
    SubagentLifecycleData,
    SubagentLifecycleEvent,
)

from app.lifecycle.harness_bridge import (
    _emit_subagent_tree,
    _handle_resource_event,
    _handle_subagent_event,
    _pending_subagent_events,
    _rest_chat_id,
    setup_harness_bridge,
    stop_harness_bridge,
)


@pytest.mark.asyncio
async def test_subagent_event_throttle():
    """Test that multiple subagent events within the window are throttled."""
    session_id = "test_session_throttle"

    _pending_subagent_events.pop(session_id, None)

    with (
        patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus,
        patch("app.lifecycle.harness_bridge.get_agent_gateway"),
        patch(
            "myrm_agent_harness.agent.sub_agents.checkpoint.saver.SubagentCheckpointStorage.list_checkpoints",
            new_callable=AsyncMock,
        ) as mock_list_checkpoints,
    ):
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus
        mock_list_checkpoints.return_value = []

        for i in range(10):
            event = SubagentLifecycleEvent(
                session_id=session_id,
                event_name="progress",
                task_id=f"task_{i}",
                data=SubagentLifecycleData(extra={"progress": i}),
            )
            await _handle_subagent_event(event)

        assert session_id in _pending_subagent_events
        mock_bus.publish.assert_not_called()

        # Wait enough time for the coalesce timer to fire AND the created task to run.
        # call_later(0.25) + task scheduling overhead — use generous margin.
        for _ in range(20):
            await asyncio.sleep(0.05)
            if session_id not in _pending_subagent_events:
                break

        assert session_id not in _pending_subagent_events
        mock_bus.publish.assert_called_once()


@pytest.mark.asyncio
async def test_subagent_event_empty_session():
    """Test handling of event with empty session id."""
    event = SubagentLifecycleEvent(session_id="", event_name="progress", task_id="t1")
    # Should just return
    await _handle_subagent_event(event)


def test_subagent_event_no_loop():
    """Test handling of event without running loop."""
    event = SubagentLifecycleEvent(session_id="test", event_name="progress", task_id="t1")
    # This is tricky as pytest-asyncio provides a loop. We can patch asyncio.get_running_loop.
    with patch("asyncio.get_running_loop", side_effect=RuntimeError):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_handle_subagent_event(event))
        finally:
            loop.close()


@pytest.mark.asyncio
async def test_policy_denial_event_publishes_synthetic_node():
    session_id = "test_session_policy"
    decision = DelegationPolicyDecision(
        allowed=False,
        reason="role_escalation_denied",
        requested_role="orchestrator",
        effective_scope="leaf",
        agent_type="worker",
        details="Agent type 'worker' is not allowed to run as an orchestrator.",
    )
    event = SubagentLifecycleEvent(
        session_id=session_id,
        event_name="policy_denied",
        task_id="denied-1",
        data=SubagentLifecycleData(
            agent_type="worker",
            role="orchestrator",
            control_scope="leaf",
            policy=decision,
        ),
    )

    with patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus:
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus

        await _handle_subagent_event(event)

        mock_bus.publish.assert_called_once()
        published_event = mock_bus.publish.call_args.args[0]
        node = published_event.data["tree"][0]
        assert node["task_id"] == "denied-1"
        assert node["policy_reason"] == "role_escalation_denied"
        assert node["role"] == "orchestrator"


def test_rest_chat_id_strips_chat_prefix() -> None:
    assert _rest_chat_id("chat_abc-123") == "abc-123"
    assert _rest_chat_id("chat_chat_abc-123") == "abc-123"
    assert _rest_chat_id("abc-123") == "abc-123"


@pytest.mark.asyncio
async def test_policy_denial_publishes_rest_chat_id():
    session_id = "chat_policy-session"
    decision = DelegationPolicyDecision(
        allowed=False,
        reason="role_escalation_denied",
        requested_role="orchestrator",
        effective_scope="leaf",
        agent_type="worker",
        details="denied",
    )
    event = SubagentLifecycleEvent(
        session_id=session_id,
        event_name="policy_denied",
        task_id="denied-2",
        data=SubagentLifecycleData(
            agent_type="worker",
            role="orchestrator",
            control_scope="leaf",
            policy=decision,
        ),
    )

    with patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus:
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus

        await _handle_subagent_event(event)

        published_event = mock_bus.publish.call_args.args[0]
        assert published_event.data["chat_id"] == "policy-session"


@pytest.mark.asyncio
async def test_emit_subagent_tree_with_checkpoints():
    """Test emit_subagent_tree merges active and checkpointed subagents."""
    session_id = "test_session_emit"

    with (
        patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus,
        patch("app.lifecycle.harness_bridge.get_agent_gateway") as mock_get_gateway,
        patch(
            "myrm_agent_harness.agent.sub_agents.checkpoint.saver.SubagentCheckpointStorage.list_checkpoints",
            new_callable=AsyncMock,
        ) as mock_list_checkpoints,
    ):
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus

        class DummyCheckpoint:
            task_id = "t1"
            agent_type = "dummy"
            progress = 100
            last_tool = "test"
            interruption_reason = ""
            recovery_attempts = 0
            task_description = ""

        mock_list_checkpoints.return_value = [DummyCheckpoint()]

        # Mock active agent with children
        mock_agent_instance = MagicMock()
        mock_agent_instance.subagent_manager.list_children.return_value = [{"task_id": "t2", "status": "running"}]
        mock_info = MagicMock()
        mock_info.agent.return_value = mock_agent_instance

        mock_gateway = MagicMock()
        mock_gateway._session_info.get.return_value = mock_info
        mock_get_gateway.return_value = mock_gateway

        await _emit_subagent_tree(session_id)

        mock_bus.publish.assert_called_once()
        args, kwargs = mock_bus.publish.call_args
        published_event = args[0]

        assert published_event.event_type.value == "subagents_updated"
        tree = published_event.data["tree"]

        task_ids = [node["task_id"] for node in tree]
        assert "t2" in task_ids  # from active
        assert "t1" in task_ids  # from checkpoint


@pytest.mark.asyncio
async def test_emit_subagent_tree_exception_handling():
    """Test exception in emit is caught and timer cleaned up."""
    session_id = "test_session_exception"
    _pending_subagent_events[session_id] = "dummy_timer"

    with patch("app.lifecycle.harness_bridge.get_agent_gateway", side_effect=Exception("Test error")):
        await _emit_subagent_tree(session_id)

    assert session_id not in _pending_subagent_events


@pytest.mark.asyncio
async def test_handle_resource_event():
    """Test resource metrics event handling."""
    event = ResourceMetricsEvent(metrics={}, history=[{"cpu": 10}])

    with patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus:
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus

        await _handle_resource_event(event)

        mock_bus.publish.assert_called_once()


@pytest.mark.asyncio
async def test_handle_resource_event_exception():
    """Test resource metrics exception handling."""
    event = ResourceMetricsEvent(metrics={}, history=[{"cpu": 10}])

    with patch("app.lifecycle.harness_bridge.get_server_bus", side_effect=Exception("Test Error")):
        await _handle_resource_event(event)


@pytest.mark.asyncio
async def test_setup_stop_harness_bridge():
    with patch("app.lifecycle.harness_bridge.get_harness_bus") as mock_get_bus:
        mock_bus = MagicMock()
        mock_bus.stop = AsyncMock()
        mock_get_bus.return_value = mock_bus

        setup_harness_bridge()
        mock_bus.start.assert_called_once()
        assert [call.args[0] for call in mock_bus.subscribe.call_args_list] == [
            SubagentLifecycleEvent,
            ResourceMetricsEvent,
            SkillFailureEvent,
            LocatorSelfHealedEvent,
            MCPAuthExpiredEvent,
        ]

        await stop_harness_bridge()
        mock_bus.stop.assert_called_once()


@pytest.mark.asyncio
async def test_handle_mcp_auth_expired_event_publishes_app_event():
    """MCP auth expired event should be forwarded as MCP_AUTH_REQUIRED AppEvent."""
    from app.lifecycle.harness_bridge import _handle_mcp_auth_expired_event
    from app.services.event.app_event_bus import AppEventType

    event = MCPAuthExpiredEvent(server_name="github-mcp", error_detail="401 Unauthorized")
    with patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus:
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus
        await _handle_mcp_auth_expired_event(event)
        mock_bus.publish.assert_called_once()
        app_event = mock_bus.publish.call_args[0][0]
        assert app_event.event_type == AppEventType.MCP_AUTH_REQUIRED
        assert app_event.data["server_name"] == "github-mcp"
        assert app_event.data["error_detail"] == "401 Unauthorized"


@pytest.mark.asyncio
async def test_handle_mcp_auth_expired_event_error_tolerant():
    """Handler should not raise even if server bus fails."""
    from app.lifecycle.harness_bridge import _handle_mcp_auth_expired_event

    event = MCPAuthExpiredEvent(server_name="broken", error_detail="401")
    with patch("app.lifecycle.harness_bridge.get_server_bus", side_effect=Exception("Bus down")):
        await _handle_mcp_auth_expired_event(event)


@pytest.mark.asyncio
async def test_stale_event_publishes_subagent_stale_app_event():
    """Stale lifecycle event should bypass throttle and publish SUBAGENT_STALE immediately."""
    from app.services.event.app_event_bus import AppEventType

    session_id = "chat_stale-session"
    event = SubagentLifecycleEvent(
        session_id=session_id,
        event_name="stale",
        task_id="stale-task-1",
        data=SubagentLifecycleData(
            agent_type="researcher",
            extra={
                "stale_duration_seconds": 320.0,
                "wasted_tokens": 5000,
            },
        ),
    )

    with patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus:
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus

        await _handle_subagent_event(event)

        mock_bus.publish.assert_called_once()
        app_event = mock_bus.publish.call_args[0][0]
        assert app_event.event_type == AppEventType.SUBAGENT_STALE
        assert app_event.data["chat_id"] == "stale-session"
        assert app_event.data["task_id"] == "stale-task-1"
        assert app_event.data["agent_type"] == "researcher"
        assert app_event.data["stale_duration_seconds"] == 320.0
        assert app_event.data["wasted_tokens"] == 5000

    # Stale must NOT schedule a debounced tree emission
    assert session_id not in _pending_subagent_events


@pytest.mark.asyncio
async def test_stale_event_empty_extra_uses_defaults():
    """Stale event with empty extra dict should use 0 defaults."""
    from app.services.event.app_event_bus import AppEventType

    event = SubagentLifecycleEvent(
        session_id="chat_x",
        event_name="stale",
        task_id="t-empty",
        data=SubagentLifecycleData(agent_type="worker", extra={}),
    )
    with patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus:
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus
        await _handle_subagent_event(event)

        app_event = mock_bus.publish.call_args[0][0]
        assert app_event.event_type == AppEventType.SUBAGENT_STALE
        assert app_event.data["stale_duration_seconds"] == 0
        assert app_event.data["wasted_tokens"] == 0
