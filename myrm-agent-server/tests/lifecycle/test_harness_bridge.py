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
from app.services.event.app_event_bus import AppEventType


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
async def test_subagent_spawn_publishes_subagent_spawned_event():
    """Spawn lifecycle events must publish SUBAGENT_SPAWNED for outbound webhooks."""
    session_id = "chat_test_spawn_webhook"
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

        event = SubagentLifecycleEvent(
            session_id=session_id,
            event_name="spawn",
            task_id="task-spawn-1",
            data=SubagentLifecycleData(agent_type="researcher", description="Compare competitors"),
        )
        await _handle_subagent_event(event)

        spawn_publish = [
            call
            for call in mock_bus.publish.call_args_list
            if call.args[0].event_type == AppEventType.SUBAGENT_SPAWNED
        ]
        assert len(spawn_publish) == 1
        payload = spawn_publish[0].args[0].data
        assert payload["task_id"] == "task-spawn-1"
        assert payload["agent_type"] == "researcher"


@pytest.mark.asyncio
async def test_subagent_complete_publishes_subagent_merged_event():
    """Complete lifecycle events must publish SUBAGENT_MERGED for outbound webhooks."""
    session_id = "chat_test_merge_webhook"
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

        event = SubagentLifecycleEvent(
            session_id=session_id,
            event_name="complete",
            task_id="task-complete-1",
            data=SubagentLifecycleData(
                agent_type="researcher",
                description="Compare competitors",
                status="success",
                result={"summary": "done"},
            ),
        )
        await _handle_subagent_event(event)

        merged_publish = [
            call
            for call in mock_bus.publish.call_args_list
            if call.args[0].event_type == AppEventType.SUBAGENT_MERGED
        ]
        assert len(merged_publish) == 1
        payload = merged_publish[0].args[0].data
        assert payload["status"] == "success"
        assert payload["result"] == {"summary": "done"}


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


class _FullCheckpoint:
    task_id = "t-cp-full"
    agent_type = "researcher"
    progress = 42.0
    last_tool = "web_search"
    interruption_reason = "user_interrupt"
    recovery_attempts = 1
    task_description = "Research market size"


class _PlainCheckpoint:
    task_id = "t-cp-plain"
    agent_type = "researcher"
    progress = 100.0
    last_tool = "final_answer"
    interruption_reason = None
    recovery_attempts = 0
    task_description = ""


@pytest.mark.asyncio
async def test_emit_subagent_tree_checkpoint_full_fields_node():
    """Re-initiate flow: interrupted checkpoint node must carry full metadata and no resumable flag."""
    session_id = "test_session_full_cp"

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
        mock_list_checkpoints.return_value = [_FullCheckpoint()]
        mock_get_gateway.return_value._session_info.get.return_value = None

        await _emit_subagent_tree(session_id)

        published_event = mock_bus.publish.call_args.args[0]
        node = published_event.data["tree"][0]
        assert node["status"] == "interrupted"
        assert node["interruption_reason"] == "user_interrupt"
        assert node["recovery_attempts"] == 1
        assert node["description"] == "Research market size"
        assert "resumable" not in node


@pytest.mark.asyncio
async def test_emit_subagent_tree_checkpoint_plain_node():
    """A checkpoint without interruption reason maps to status=checkpoint with no optional fields."""
    session_id = "test_session_plain_cp"

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
        mock_list_checkpoints.return_value = [_PlainCheckpoint()]
        mock_get_gateway.return_value._session_info.get.return_value = None

        await _emit_subagent_tree(session_id)

        node = mock_bus.publish.call_args.args[0].data["tree"][0]
        assert node["status"] == "checkpoint"
        assert "interruption_reason" not in node
        assert "recovery_attempts" not in node
        assert "description" not in node
        assert "resumable" not in node


@pytest.mark.asyncio
async def test_emit_subagent_tree_deduplicates_checkpoint_vs_active():
    """A checkpoint whose task_id is still active must not be duplicated."""
    session_id = "test_session_dedup"

    with (
        patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus,
        patch("app.lifecycle.harness_bridge.get_agent_gateway") as mock_get_gateway,
        patch(
            "myrm_agent_harness.agent.sub_agents.checkpoint.saver.SubagentCheckpointStorage.list_checkpoints",
            new_callable=AsyncMock,
        ) as mock_list_checkpoints,
        patch(
            "myrm_agent_harness.agent.sub_agents.session_tree.merge_active_subagent_children",
            return_value=[{"task_id": "t1", "status": "running"}],
        ),
    ):
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus
        plain = _PlainCheckpoint()
        plain.task_id = "t1"
        mock_list_checkpoints.return_value = [plain]
        mock_get_gateway.return_value._session_info.get.return_value = None

        await _emit_subagent_tree(session_id)

        tree = mock_bus.publish.call_args.args[0].data["tree"]
        assert [node["task_id"] for node in tree] == ["t1"]


@pytest.mark.asyncio
async def test_emit_subagent_tree_hydrates_teammate_messages():
    """Persisted teammate mailbox rows are attached onto tree nodes."""
    session_id = "chat_hydrate-session"
    teammate_msg = {"task_id": "t-hyd", "role": "user", "content": "hi"}

    with (
        patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus,
        patch("app.lifecycle.harness_bridge.get_agent_gateway") as mock_get_gateway,
        patch(
            "app.services.chat.chat_service.ChatService.ensure_default_workspace_dir",
            new_callable=AsyncMock,
        ) as mock_ws,
        patch("myrm_agent_harness.agent.coordination.mailbox.list_teammate_history") as mock_history,
        patch("myrm_agent_harness.agent.coordination.mailbox.group_history_by_task") as mock_group,
        patch(
            "myrm_agent_harness.agent.sub_agents.checkpoint.saver.SubagentCheckpointStorage.list_checkpoints",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "myrm_agent_harness.agent.sub_agents.session_tree.merge_active_subagent_children",
            return_value=[{"task_id": "t-hyd", "status": "running"}],
        ),
    ):
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus
        mock_get_gateway.return_value._session_info.get.return_value = None
        mock_ws.return_value = "/tmp/ws"
        mock_history.return_value = [teammate_msg]
        mock_group.return_value = {"t-hyd": [teammate_msg]}

        await _emit_subagent_tree(session_id)

        node = mock_bus.publish.call_args.args[0].data["tree"][0]
        assert node["teammate_messages"] == [teammate_msg]
        mock_history.assert_called_once_with("hydrate-session", "/tmp/ws", limit=200)


@pytest.mark.asyncio
async def test_emit_subagent_tree_falls_back_to_raw_session_id():
    """When rest_chat_id lookup misses, the raw harness session_id must be consulted."""
    session_id = "chat_fallback-session"
    mock_agent_instance = MagicMock()
    mock_agent_instance.subagent_manager.list_children.return_value = []
    mock_info = MagicMock()
    mock_info.agent.return_value = mock_agent_instance

    with (
        patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus,
        patch("app.lifecycle.harness_bridge.get_agent_gateway") as mock_get_gateway,
        patch(
            "myrm_agent_harness.agent.sub_agents.checkpoint.saver.SubagentCheckpointStorage.list_checkpoints",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus
        mock_get_gateway.return_value._session_info.get.side_effect = [None, mock_info]

        await _emit_subagent_tree(session_id)

        published_event = mock_bus.publish.call_args.args[0]
        assert published_event.data["chat_id"] == "fallback-session"
        mock_agent_instance.subagent_manager.list_children.assert_called_once()


@pytest.mark.asyncio
async def test_emit_subagent_tree_checkpoint_list_exception_tolerated():
    """A checkpoint listing failure must not abort the whole tree emission."""
    session_id = "test_session_cp_error"

    with (
        patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus,
        patch("app.lifecycle.harness_bridge.get_agent_gateway") as mock_get_gateway,
        patch(
            "myrm_agent_harness.agent.sub_agents.checkpoint.saver.SubagentCheckpointStorage.list_checkpoints",
            new_callable=AsyncMock,
            side_effect=RuntimeError("storage down"),
        ),
        patch(
            "myrm_agent_harness.agent.sub_agents.session_tree.merge_active_subagent_children",
            return_value=[],
        ),
    ):
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus
        mock_get_gateway.return_value._session_info.get.return_value = None

        await _emit_subagent_tree(session_id)

        assert mock_bus.publish.call_count == 1
        assert mock_bus.publish.call_args.args[0].data["tree"] == []


@pytest.mark.asyncio
async def test_emit_subagent_tree_teammate_hydrate_exception_and_non_dict_child():
    """Hydrate failures are tolerated and non-dict children are skipped."""
    session_id = "chat_hydrate-error-session"

    with (
        patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus,
        patch("app.lifecycle.harness_bridge.get_agent_gateway") as mock_get_gateway,
        patch(
            "app.services.chat.chat_service.ChatService.ensure_default_workspace_dir",
            side_effect=RuntimeError("ws down"),
        ),
        patch(
            "myrm_agent_harness.agent.sub_agents.checkpoint.saver.SubagentCheckpointStorage.list_checkpoints",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "myrm_agent_harness.agent.sub_agents.session_tree.merge_active_subagent_children",
            return_value=[{"task_id": "t-ok"}, "not-a-dict", 42],
        ),
    ):
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus
        mock_get_gateway.return_value._session_info.get.return_value = None

        await _emit_subagent_tree(session_id)

        published_event = mock_bus.publish.call_args.args[0]
        tree = published_event.data["tree"]
        assert len(tree) == 3
        dict_task_ids = [c["task_id"] for c in tree if isinstance(c, dict)]
        assert dict_task_ids == ["t-ok"]


@pytest.mark.asyncio
async def test_handle_skill_failure_event_delegates_and_tolerates_error():
    """Skill failure events must be routed to the immune service and never raise."""
    from app.lifecycle.harness_bridge import _handle_skill_failure_event

    event = SkillFailureEvent(
        tool_name="memory.search",
        error_message="boom",
        error_signature="sig",
        candidates=(),
        session_id="chat_skill-session",
    )

    with patch(
        "app.services.agent.evolution.skill_immune_service.handle_skill_failure_event",
        new_callable=AsyncMock,
    ) as mock_handle:
        await _handle_skill_failure_event(event)
        mock_handle.assert_awaited_once_with(event)

    with patch(
        "app.services.agent.evolution.skill_immune_service.handle_skill_failure_event",
        side_effect=RuntimeError("immune down"),
    ):
        await _handle_skill_failure_event(event)


@pytest.mark.asyncio
async def test_handle_locator_healed_event_publishes_and_tolerates_error():
    """Locator healed events must be forwarded as LOCATOR_HEALED AppEvents."""
    from app.lifecycle.harness_bridge import _handle_locator_healed_event
    from app.services.event.app_event_bus import AppEventType

    event = LocatorSelfHealedEvent(
        ref="locator-1",
        old_name="old",
        new_name="new",
        url="https://example.com",
        role="button",
        distance=0.3,
    )

    with patch("app.lifecycle.harness_bridge.get_server_bus") as mock_get_bus:
        mock_bus = MagicMock()
        mock_get_bus.return_value = mock_bus
        await _handle_locator_healed_event(event)
        app_event = mock_bus.publish.call_args[0][0]
        assert app_event.event_type == AppEventType.LOCATOR_HEALED
        assert app_event.data["ref"] == "locator-1"
        assert app_event.data["new_name"] == "new"

    with patch("app.lifecycle.harness_bridge.get_server_bus", side_effect=Exception("Bus down")):
        await _handle_locator_healed_event(event)


@pytest.mark.asyncio
async def test_close_harness_resources_drains_bridge_and_mcp():
    """close_harness_resources must stop the bridge and drain the MCP lifecycle."""
    from app.lifecycle.harness_bridge import close_harness_resources

    with (
        patch("app.lifecycle.harness_bridge.get_harness_bus") as mock_get_bus,
        patch(
            "myrm_agent_harness.toolkits.mcp.lifecycle.mcp_lifecycle.shutdown",
            new_callable=AsyncMock,
        ) as mock_shutdown,
    ):
        mock_bus = MagicMock()
        mock_bus.stop = AsyncMock()
        mock_get_bus.return_value = mock_bus

        await close_harness_resources()
        mock_bus.stop.assert_awaited_once()
        mock_shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_harness_resources_tolerates_teardown_errors():
    """Teardown errors must be logged, not raised."""
    from app.lifecycle.harness_bridge import close_harness_resources

    with (
        patch("app.lifecycle.harness_bridge.get_harness_bus", side_effect=RuntimeError("bus gone")),
        patch(
            "myrm_agent_harness.toolkits.mcp.lifecycle.mcp_lifecycle.shutdown",
            side_effect=RuntimeError("mcp gone"),
        ),
    ):
        await close_harness_resources()
