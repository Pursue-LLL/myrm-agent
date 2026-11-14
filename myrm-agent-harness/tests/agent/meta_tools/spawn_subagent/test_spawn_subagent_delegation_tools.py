"""Unit tests for spawn_subagent delegation tool factories (parallel + pause gate)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.agent.sub_agents.types import DELEGATION_CAPABILITY_MANIFEST


def _make_parent() -> MagicMock:
    parent = MagicMock()
    parent.config = None
    parent.engine_params = {}
    parent.list_children.return_value = []
    parent._last_context = {"session_id": "chat_test"}
    return parent


class CatalogStub:
    async def list_available(self) -> list[str]:
        return ["worker"]

    async def resolve(self, agent_type: str) -> object | None:
        return None


class TestExecuteParallelDelegation:
    def test_empty_tasks_returns_error(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent._delegate_batch import (
            execute_parallel_delegation,
        )

        parent = _make_parent()
        result = execute_parallel_delegation(parent, [])
        assert result["success"] is False
        assert "No tasks" in result["error"]

    def test_interrupt_payload_and_resume(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent._delegate_batch import (
            TaskRequest,
            execute_parallel_delegation,
        )

        parent = _make_parent()
        tasks = [
            TaskRequest(agent_type="worker", objective="research topic A"),
            TaskRequest(agent_type="worker", objective="research topic B"),
        ]
        fake_decisions = [{"task_id": "t1", "success": True}]

        with patch(
            "langgraph.types.interrupt",
            return_value=fake_decisions,
        ) as interrupt_mock:
            result = execute_parallel_delegation(parent, tasks)

        interrupt_mock.assert_called_once()
        payload = interrupt_mock.call_args.args[0]
        assert payload["action_type"] == "swarm_fission"
        assert len(payload["tasks"]) == 2
        assert result["success"] is True
        assert result["results"] == fake_decisions

    def test_paused_session_blocks_parallel(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent._delegate_batch import (
            TaskRequest,
            execute_parallel_delegation,
        )
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegation_pause_gate import (
            pause_delegation,
            resume_delegation,
        )

        parent = _make_parent()
        pause_delegation("chat_test")
        try:
            result = execute_parallel_delegation(
                parent,
                [TaskRequest(agent_type="worker", objective="blocked")],
            )
            assert result["success"] is False
            assert "paused" in str(result["error"]).lower()
        finally:
            resume_delegation("chat_test")


class TestDelegateTaskPauseGate:
    @pytest.mark.asyncio
    async def test_single_mode_blocked_when_paused(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegate_task_tool import (
            create_delegate_task_tool,
        )
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegation_pause_gate import (
            pause_delegation,
            resume_delegation,
        )

        parent = _make_parent()
        pause_delegation("chat_test")
        try:
            tool = create_delegate_task_tool(parent, lambda: [], CatalogStub())
            result = await tool.ainvoke(
                {"mode": "single", "agent_type": "worker", "objective": "do work", "wait": True}
            )
            assert result["success"] is False
            assert "paused" in str(result["error"]).lower()
        finally:
            resume_delegation("chat_test")

    @pytest.mark.asyncio
    async def test_batch_mode_blocked_when_paused(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegate_task_tool import (
            create_delegate_task_tool,
        )
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegation_pause_gate import (
            pause_delegation,
            resume_delegation,
        )

        parent = _make_parent()
        pause_delegation("chat_test")
        try:
            tool = create_delegate_task_tool(parent, lambda: [], CatalogStub())
            result = await tool.ainvoke(
                {
                    "mode": "batch",
                    "tasks": [{"agent_type": "worker", "objective": "blocked batch task"}],
                    "wait": True,
                }
            )
            assert result["success"] is False
            assert "paused" in str(result["error"]).lower()
        finally:
            resume_delegation("chat_test")

    @pytest.mark.asyncio
    async def test_parallel_mode_empty_tasks(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegate_task_tool import (
            create_delegate_task_tool,
        )

        tool = create_delegate_task_tool(_make_parent(), lambda: [], CatalogStub())
        result = await tool.ainvoke({"mode": "parallel", "tasks": []})
        assert result["success"] is False
        assert "No tasks" in result["error"]


class TestSubagentControlToolFactory:
    @pytest.mark.asyncio
    async def test_cancel_subagent_not_found(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.agent_manage_tool import (
            create_subagent_control_tool,
        )

        parent = _make_parent()
        parent.cancel_child.return_value = False
        tool = create_subagent_control_tool(parent)
        result = await tool.ainvoke({"action": "cancel", "task_id": "missing"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_cancel_subagent_success(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.agent_manage_tool import (
            create_subagent_control_tool,
        )

        parent = _make_parent()
        parent.cancel_child.return_value = True
        tool = create_subagent_control_tool(parent)
        result = await tool.ainvoke({"action": "cancel", "task_id": "task-1"})
        assert result["success"] is True
        assert result["task_id"] == "task-1"

    @pytest.mark.asyncio
    async def test_cancel_requires_task_id(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.agent_manage_tool import (
            create_subagent_control_tool,
        )

        tool = create_subagent_control_tool(_make_parent())
        result = await tool.ainvoke({"action": "cancel"})
        assert result["success"] is False
        assert "task_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_steer_requires_message(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.agent_manage_tool import (
            create_subagent_control_tool,
        )

        tool = create_subagent_control_tool(_make_parent())
        result = await tool.ainvoke({"action": "steer", "task_id": "task-1", "message": "  "})
        assert result["success"] is False
        assert "message is required" in result["error"]

    @pytest.mark.asyncio
    async def test_steer_success_and_failure(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.agent_manage_tool import (
            create_subagent_control_tool,
        )

        parent = _make_parent()
        tool = create_subagent_control_tool(parent)

        parent.steer_child.return_value = True
        ok = await tool.ainvoke({"action": "steer", "task_id": "task-1", "message": "fix it"})
        assert ok["success"] is True

        parent.steer_child.return_value = False
        bad = await tool.ainvoke({"action": "steer", "task_id": "gone", "message": "fix it"})
        assert bad["success"] is False

    @pytest.mark.asyncio
    async def test_list_subagents(self) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent.agent_manage_tool import (
            create_subagent_control_tool,
        )

        parent = _make_parent()
        parent.list_children.return_value = [{"task_id": "a1", "status": "running"}]
        tool = create_subagent_control_tool(parent)
        result = await tool.ainvoke({"action": "list"})
        assert result["total"] == 1
        assert result["running"] == 1


class TestDelegationCapabilityManifest:
    def test_orchestrator_child_tools_are_delegate_and_control(self) -> None:
        assert DELEGATION_CAPABILITY_MANIFEST.orchestrator_child_tools == (
            "delegate_task_tool",
            "subagent_control_tool",
        )
