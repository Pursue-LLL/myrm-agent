"""When ``CompletionGuard.aafter_model`` holds an answer attempt back and when it lets it through, and what a hold leaves in the thread."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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
)
from tests.support.completion_guard_harness import (
    LOOP_GUARD_PATCH,
    make_state,
    pending,
    reasons_of,
)


class TestCompletionGuardTriggerConditions:
    """Test trigger conditions for CompletionGuard.aafter_model.

    After removing one-shot WARNING, only CRITICAL blocking remains:
    the guard triggers only when code files were modified without verification.
    """

    def setup_method(self) -> None:
        self.guard = CompletionGuard()
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_skips_when_ai_has_tool_calls(self) -> None:
        """Should skip when AIMessage HAS tool_calls (except finish tools)."""
        state = make_state(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "tc1", "name": "file_read_tool", "args": {}}],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_triggers_when_ai_calls_finish_tool_with_unverified_writes(
        self,
    ) -> None:
        """Should trigger when AIMessage calls finish tool after modifying code without verification."""
        state = make_state(
            [
                HumanMessage(content="Change main.py and tell me when it is done."),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "tc_answer",
                            "name": "request_answer_user_tool",
                            "args": {"reason": "Task complete"},
                        }
                    ],
                ),
            ]
        )

        code_write_record = CallRecord(
            tool_name="file_write_tool",
            args_hash="hash_code_write",
            args={"path": "/src/main.py"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )

        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [code_write_record]
            result = await self.guard.aafter_model(state, None)

        user_message = state["messages"][0]
        assert pending(result).anchor_id == user_message.id

    @pytest.mark.asyncio
    async def test_skips_when_no_critical_errors(self) -> None:
        """Should pass through when no critical errors (no unverified code writes)."""
        state = make_state([AIMessage(content="All done.")])
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_blocks_when_external_evidence_required_but_missing(self) -> None:
        """Freshness query without evidence tools should be blocked before finish."""
        state = make_state(
            [
                HumanMessage(content="今天最新的 AI 新闻是什么？"),
                AIMessage(content="All done."),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        assert reasons_of(result).evidence

    @pytest.mark.asyncio
    async def test_allows_when_external_evidence_exists(self) -> None:
        """Freshness query with successful web evidence should pass through."""
        state = make_state(
            [
                HumanMessage(content="Please give today's latest AI news summary."),
                AIMessage(content="All done."),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [
                CallRecord(
                    tool_name="web_search_tool",
                    args_hash="evidence1",
                    args={"query": "latest ai news"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            result = await self.guard.aafter_model(state, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_blocks_when_unwritten_deliverable_detected_without_write(self) -> None:
        """Substantial code deliverable without write calls should be blocked."""
        code_body = (
            "```python\n"
            "# filename: src/server.py\n"
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "\n"
            "@app.get('/health')\n"
            "def health():\n"
            "    return {'status': 'healthy'}\n"
            "```"
        )
        state = make_state(
            [
                HumanMessage(content="请帮我写一个 FastAPI 服务代码"),
                AIMessage(content=f"这是实现的服务：\n{code_body}"),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        assert "Substantial unpersisted deliverables" in reasons_of(result).deliverable_write

    @pytest.mark.asyncio
    async def test_unwritten_deliverable_auto_staged_at_max_rejections(self) -> None:
        """At max rejections, unwritten deliverables should be auto-staged to workspace."""
        import tempfile

        code_body = (
            "```python\n"
            "# filename: draft_worker.py\n"
            "import time\n"
            "\n"
            "def run_worker():\n"
            "    print('working')\n"
            "    time.sleep(1)\n"
            "```"
        )
        state = make_state(
            [
                HumanMessage(content="写一个 worker 脚本"),
                AIMessage(content=f"完成：\n{code_body}"),
            ]
        )
        guard = CompletionGuard(max_rejections=1)
        reset_completion_guard()

        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = Runtime(context={"workspace_path": tmp_dir})
            with patch(LOOP_GUARD_PATCH) as mock_guard:
                mock_guard.return_value.recorded_calls.return_value = []
                # First rejection (rejection_count=1)
                r1 = await guard.aafter_model(state, runtime)
                assert r1 is not None

                # Second attempt hits max_rejections -> forced finish with auto-staging
                r2 = await guard.aafter_model(state, runtime)
                forced = reasons_of(r2)
                assert forced.forced_finish is True
                staged = forced.staged_artifacts
                assert len(staged) == 1
                assert staged[0]["original_hint"] == "draft_worker.py"

                # Check physical file staged in workspace
                staged_path = Path(tmp_dir) / staged[0]["relative_path"]
                assert staged_path.exists()
                assert "run_worker" in staged_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_blocks_when_long_code_lines_without_write(self) -> None:
        """Substantial code deliverable without write calls should be blocked."""
        code_lines = "\n".join(f"line_{i} = {i} * 2" for i in range(40))
        msg_content = f"Here is the complete implementation:\n```python\n# filename: app.py\n{code_lines}\n```"
        state = make_state(
            [
                HumanMessage(content="请帮我写一个完整的数据处理程序并保存"),
                AIMessage(content=msg_content),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        assert "Substantial unpersisted deliverables detected" in reasons_of(result).deliverable_write

    @pytest.mark.asyncio
    async def test_allows_when_mcp_ptc_bash_evidence_exists(self) -> None:
        """Freshness query with successful MCP PTC bash should pass through."""
        state = make_state(
            [
                HumanMessage(content="Please give today's latest AI news summary."),
                AIMessage(content="All done."),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [
                CallRecord(
                    tool_name="bash_code_execute_tool",
                    args_hash="mcpbash1",
                    args={"command": "from skills.mcp_news_skill import fetch_latest"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            result = await self.guard.aafter_model(state, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_does_not_block_plain_programming_question(self) -> None:
        """Non-freshness coding questions should not trigger external evidence gate."""
        state = make_state(
            [
                HumanMessage(content="How do I link two lists in Python?"),
                AIMessage(content="All done."),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_does_not_block_keyword_substring_in_code_question(self) -> None:
        """Word substrings like 'priceList' should not trigger freshness gate."""
        state = make_state(
            [
                HumanMessage(content="How do I model a priceList type in TypeScript?"),
                AIMessage(content="All done."),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = []
            result = await self.guard.aafter_model(state, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_skips_when_only_non_code_writes(self) -> None:
        """Should pass through when only non-code files were modified."""
        state = make_state([AIMessage(content="Updated docs.")])
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [
                CallRecord(
                    tool_name="file_write_tool",
                    args_hash="abc",
                    args={"path": "/tmp/README.md"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self) -> None:
        """Should skip when enabled=False."""
        guard = CompletionGuard(enabled=False)
        state = make_state([AIMessage(content="Done.")])
        result = await guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_blocks_on_critical_errors(self) -> None:
        """Should block and increment rejection count when critical errors exist."""
        state = make_state([AIMessage(content="All done!")])
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [
                CallRecord(
                    tool_name="file_write_tool",
                    args_hash="abc",
                    args={"path": "/tmp/test.py"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            result = await self.guard.aafter_model(state, None)

        assert reasons_of(result).forced_finish is False
        assert _cg_state.current_run_state().rejections == 1

    @pytest.mark.asyncio
    async def test_max_rejections_graceful_degradation(self) -> None:
        """Should let the model finish with a warning once max rejections are reached."""
        self.guard._max_rejections = 2
        _cg_state.current_run_state().rejections = 2
        state = make_state([AIMessage(content="All done!")])
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [
                CallRecord(
                    tool_name="file_write_tool",
                    args_hash="abc",
                    args={"path": "/tmp/test.py"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            result = await self.guard.aafter_model(state, None)

        assert _cg_state.current_run_state().forced_finish is True
        assert reasons_of(result).forced_finish is True

    @pytest.mark.asyncio
    async def test_after_forced_finish_guard_releases(self) -> None:
        """After max-rejections force-finish, subsequent completions pass through."""
        self.guard._max_rejections = 2
        _cg_state.current_run_state().rejections = 2
        state = make_state(
            [
                HumanMessage(content="Change main.py and tell me when it is done."),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "tc_answer",
                            "name": "request_answer_user_tool",
                            "args": {"reason": "Task complete"},
                        }
                    ],
                ),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value.recorded_calls.return_value = [
                CallRecord(
                    tool_name="file_write_tool",
                    args_hash="abc",
                    args={"path": "/tmp/a.py"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            first = await self.guard.aafter_model(state, None)
        assert first is not None and _cg_state.current_run_state().forced_finish is True
        # Next completion attempt is released without further injections.
        released = await self.guard.aafter_model(state, None)
        assert released is None


class TestCompletionGuardReset:
    """Test reset_completion_guard resets rejection counter."""

    def test_reset_clears_rejection_count(self) -> None:
        _cg_state.current_run_state().rejections = 5
        _cg_state.current_run_state().forced_finish = True
        reset_completion_guard()
        assert _cg_state.current_run_state().rejections == 0
        assert _cg_state.current_run_state().forced_finish is False
