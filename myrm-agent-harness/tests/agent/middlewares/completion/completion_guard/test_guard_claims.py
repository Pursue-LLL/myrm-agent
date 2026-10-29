"""The guard's entity-query grounding check and execution-claim gate."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

import myrm_agent_harness.agent.middlewares.completion.completion_guard.state as _cg_state
from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
    VerificationCategory,
)
from tests.support.completion_guard_harness import (
    LOOP_GUARD_PATCH,
    directive_of,
    make_state,
    reasons_of,
)


class TestCompletionGuardQueryGroundingIntegration:
    """Integration tests for query grounding enforcement in CompletionGuard."""

    def setup_method(self) -> None:
        self.guard = CompletionGuard()
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_query_intent_without_tool_calls_blocks_with_query_grounding_reason(self, tmp_path: Path) -> None:
        state = make_state(
            [
                HumanMessage(content="查一下订单 OD-10086 的发货状态"),
                AIMessage(content="订单 OD-10086 已经发货了，预计明天送达。"),
            ]
        )
        runtime = Runtime(context={"workspace_path": str(tmp_path)})

        mock_loop_guard = MagicMock()
        mock_loop_guard.recorded_calls.return_value = []

        with patch(LOOP_GUARD_PATCH, return_value=mock_loop_guard):
            res = await self.guard.aafter_model(state, runtime)

        assert "no query or MCP tool was executed" in reasons_of(res).query_grounding

    @pytest.mark.asyncio
    async def test_multi_entity_query_missing_one_entity_blocks_in_guard(self, tmp_path: Path) -> None:
        rec_od = CallRecord(
            tool_name="mcp__erp__query_order",
            args_hash="hash_query_od",
            args={"order_id": "OD-9921"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        state = make_state(
            [
                HumanMessage(content="帮我查一下订单 OD-9921 的状态，顺便看一下工单 TK-8802 的进度"),
                AIMessage(content="订单 OD-9921 已发货，工单 TK-8802 正在处理中。"),
            ]
        )
        runtime = Runtime(context={"workspace_path": str(tmp_path)})

        mock_loop_guard = MagicMock()
        mock_loop_guard.recorded_calls.return_value = [rec_od]

        with patch(LOOP_GUARD_PATCH, return_value=mock_loop_guard):
            res = await self.guard.aafter_model(state, runtime)

        assert "TK-8802" in reasons_of(res).query_grounding

    @pytest.mark.asyncio
    async def test_multi_entity_query_missing_one_with_honest_negative_passes_guard(self, tmp_path: Path) -> None:
        rec_od = CallRecord(
            tool_name="mcp__erp__query_order",
            args_hash="hash_query_od",
            args={"order_id": "OD-9921"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        state = make_state(
            [
                HumanMessage(content="帮我查一下订单 OD-9921 的状态，顺便看一下工单 TK-8802 的进度"),
                AIMessage(content="订单 OD-9921 已发货；系统查询显示工单 TK-8802 暂未查询到对应处理进度。"),
            ]
        )
        runtime = Runtime(context={"workspace_path": str(tmp_path)})

        mock_loop_guard = MagicMock()
        mock_loop_guard.recorded_calls.return_value = [rec_od]

        with patch(LOOP_GUARD_PATCH, return_value=mock_loop_guard):
            res = await self.guard.aafter_model(state, runtime)

        assert res is None

    @pytest.mark.asyncio
    async def test_multi_entity_query_all_grounded_passes_guard(self, tmp_path: Path) -> None:
        rec_od = CallRecord(
            tool_name="mcp__erp__query_order",
            args_hash="hash_query_od",
            args={"order_id": "OD-9921"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        rec_tk = CallRecord(
            tool_name="mcp__itsm__query_ticket",
            args_hash="hash_query_tk",
            args={"ticket_id": "TK-8802"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        state = make_state(
            [
                HumanMessage(content="帮我查一下订单 OD-9921 的状态，顺便看一下工单 TK-8802 的进度"),
                AIMessage(content="订单 OD-9921 已发货，工单 TK-8802 处理中。"),
            ]
        )
        runtime = Runtime(context={"workspace_path": str(tmp_path)})

        mock_loop_guard = MagicMock()
        mock_loop_guard.recorded_calls.return_value = [rec_od, rec_tk]

        with patch(LOOP_GUARD_PATCH, return_value=mock_loop_guard):
            res = await self.guard.aafter_model(state, runtime)

        assert res is None


class TestExecutionClaimGate:
    """Completion claims must be grounded by this run's tool records."""

    def setup_method(self) -> None:
        self.guard = CompletionGuard()
        reset_completion_guard()

    def teardown_method(self) -> None:
        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
            set_current_message_id,
        )

        set_current_message_id("")
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_blocks_unbacked_test_claim(self) -> None:
        state = make_state(
            [
                HumanMessage(content="帮我跑一下测试，告诉我结果"),
                AIMessage(content="我已经运行了完整测试套件：所有测试全部通过（pytest 236 passed, 0 failed）。"),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        reasons = reasons_of(result)
        assert reasons.execution_claim
        assert reasons.forced_finish is False

    @pytest.mark.asyncio
    async def test_allows_claim_backed_by_verification_record(self) -> None:
        record = CallRecord(
            tool_name="bash_code_execute_tool",
            args_hash="verify",
            args={"command": "pytest -q"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        record.verification_type = VerificationCategory.TEST

        state = make_state(
            [
                HumanMessage(content="帮我跑一下测试，告诉我结果"),
                AIMessage(content="所有测试全部通过。"),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [record]
            result = await self.guard.aafter_model(state, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_forced_finish_carries_claim_reason_and_notice(self) -> None:
        self.guard._max_rejections = 1
        _cg_state.current_run_state().rejections = 1
        state = make_state(
            [
                HumanMessage(content="帮我跑一下测试"),
                AIMessage(content="所有测试全部通过。"),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        reasons = reasons_of(result)
        assert reasons.forced_finish is True
        assert reasons.execution_claim
        assert "claimed work" in directive_of(result)

    @pytest.mark.asyncio
    async def test_mixed_message_path_keeps_tool_calls_for_unbacked_claim(self) -> None:
        filler = "\n".join(
            f"- 第 {index} 条分析结论：该模块在压力场景下表现稳定，相关指标与上一轮相比没有退化。"
            for index in range(12)
        )
        content = f"分析完成：\n{filler}\n所有测试全部通过。"
        assert len(content) > 500
        state = make_state(
            [
                HumanMessage(content="帮我跑一下测试，告诉我结果"),
                AIMessage(
                    content=content,
                    tool_calls=[{"id": "tc_read", "name": "file_read_tool", "args": {"path": "/tmp/a.txt"}}],
                ),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        # The claim cannot be grounded, so the Mixed Message Guard must not
        # strip the read-only call and terminate with an unbacked answer.
        assert result is None

    @pytest.mark.asyncio
    async def test_publishes_evidence_tier_for_work_turn(self) -> None:
        record = CallRecord(
            tool_name="file_write_tool",
            args_hash="write",
            args={"path": "report.md"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        state = make_state(
            [
                HumanMessage(content="帮我写一份报告"),
                AIMessage(content="报告已生成，详见工作区。"),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [record]
            result = await self.guard.aafter_model(state, None)

        assert result is None
        disclosure = _cg_state.pop_run_disclosure("")
        assert disclosure is not None
        tier = disclosure.get("deliverable_tier")
        assert isinstance(tier, dict)
        assert tier.get("tier") == "ARTIFACT"

    @pytest.mark.asyncio
    async def test_does_not_publish_plan_tier_for_casual_chat(self) -> None:
        state = make_state([HumanMessage(content="你喜欢什么颜色？"), AIMessage(content="我没有偏好。")])
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        assert result is None
        assert _cg_state.pop_run_disclosure("") is None

    @pytest.mark.asyncio
    async def test_staged_artifacts_are_published_for_disclosure(self, tmp_path: Path) -> None:
        self.guard._max_rejections = 1
        _cg_state.current_run_state().rejections = 1
        code_msg = (
            "```python\n"
            "# filename: app/calc.py\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "\n"
            "def sub(a, b):\n"
            "    return a - b\n"
            "```"
        )
        state = make_state([HumanMessage(content="帮我创建 calculator"), AIMessage(content=code_msg)])
        runtime = Runtime(context={"workspace_path": str(tmp_path)})
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, runtime)

        assert result is not None
        disclosure = _cg_state.pop_run_disclosure("")
        assert disclosure is not None
        staged = disclosure.get("staged_artifacts")
        assert isinstance(staged, list) and len(staged) == 1

    @pytest.mark.asyncio
    async def test_inline_copy_turn_publishes_no_plan_badge(self) -> None:
        state = make_state(
            [
                HumanMessage(content="帮我写三版产品文案"),
                AIMessage(content="这是三版文案：\n1. 版本一。\n2. 版本二。\n3. 版本三。"),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        assert result is None
        assert _cg_state.pop_run_disclosure("") is None

    @pytest.mark.asyncio
    async def test_unbacked_claim_publishes_plan_badge_for_disclosure(self) -> None:
        state = make_state(
            [
                HumanMessage(content="帮我跑一下测试"),
                AIMessage(content="所有测试全部通过。"),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        assert result is not None
        disclosure = _cg_state.pop_run_disclosure("")
        assert disclosure is not None
        assert disclosure.get("deliverable_tier", {}).get("tier") == "PLAN"

    @pytest.mark.asyncio
    async def test_disclosure_survives_a_later_segment_with_an_empty_window(self) -> None:
        """A resumed segment sees an empty loop window; the turn's write still discloses."""
        record = CallRecord(
            tool_name="file_write_tool",
            args_hash="write",
            args={"path": "/workspace/report.md"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        state = make_state(
            [
                HumanMessage(content="帮我写一份报告"),
                AIMessage(content="报告已生成，详见工作区。"),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [record]
            assert await self.guard.aafter_model(state, None) is None
        first = _cg_state.pop_run_disclosure("")
        assert first is not None and first["deliverable_tier"]["tier"] == "ARTIFACT"

        # New segment of the same turn: the loop window starts empty.
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            assert await self.guard.aafter_model(state, None) is None

        second = _cg_state.pop_run_disclosure("")
        assert second is not None
        assert second["deliverable_tier"]["tier"] == "ARTIFACT"

    @pytest.mark.asyncio
    async def test_concurrent_runs_keep_separate_rejection_budgets(self) -> None:
        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
            set_current_message_id,
        )

        state = make_state([HumanMessage(content="继续"), AIMessage(content="All done!")])
        write = CallRecord(
            tool_name="file_write_tool",
            args_hash="w",
            args={"path": "/tmp/test.py"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )

        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [write]

            set_current_message_id("msg_a")
            reset_completion_guard()
            assert await self.guard.aafter_model(state, None) is not None
            assert await self.guard.aafter_model(state, None) is not None

            set_current_message_id("msg_b")
            reset_completion_guard()
            assert await self.guard.aafter_model(state, None) is not None

        assert _cg_state._run_states["msg_a"].rejections == 2
        assert _cg_state._run_states["msg_b"].rejections == 1
        assert _cg_state._run_states["msg_a"].forced_finish is False
        assert _cg_state._run_states["msg_b"].forced_finish is False
