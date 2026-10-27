"""The Mixed Message Guard: a finished answer next to read-only tool calls ends the turn, an effectful or unverified one does not."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.directive import (
    BlockReasons,
)
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
)
from myrm_agent_harness.core.security.tool_registry import (
    SafetyMetadata,
    register_ptc_safety_metadata,
)
from tests.support.completion_guard_harness import (
    LOOP_GUARD_PATCH,
    make_state,
    pending,
    reasons_of,
)


class TestMixedMessageGuard:
    """Test the Mixed Message Guard feature in CompletionGuard.

    This guard strips read-only tool_calls when the AIMessage already contains
    a substantive final response, avoiding unnecessary tool execution rounds.
    """

    def setup_method(self) -> None:
        self.guard = CompletionGuard()
        reset_completion_guard()

    def _long_answer(self) -> str:
        """Generate a >500 char content with markdown structure."""
        return (
            "# Analysis of Router Structure\n\n"
            "The router is organized into the following modules:\n\n"
            "- **api/users.py**: Handles user CRUD operations\n"
            "- **api/auth.py**: Authentication and session management\n"
            "- **api/projects.py**: Project lifecycle management\n\n"
            "## Key Observations\n\n"
            "1. All routes follow RESTful conventions\n"
            "2. Authentication middleware is applied globally\n"
            "3. Rate limiting is configured per-endpoint\n\n"
            "```python\n"
            "router = APIRouter(prefix='/api/v1')\n"
            "```\n\n"
            "The architecture follows a clean separation of concerns "
            "with dependency injection for database sessions and proper "
            "error handling at each layer boundary."
        )

    @pytest.mark.asyncio
    async def test_strips_readonly_tools_with_substantive_content(self) -> None:
        """Core case: content is final answer + read-only tools -> strip."""
        state = make_state(
            [
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "file_read_tool",
                            "args": {"path": "/src/router.py"},
                        },
                        {
                            "id": "tc2",
                            "name": "grep_tool",
                            "args": {"pattern": "route"},
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)

        assert result is not None
        ai_msg = result["messages"][0]
        assert isinstance(ai_msg, AIMessage)
        assert ai_msg.tool_calls == []
        assert "Analysis of Router Structure" in ai_msg.content

    @pytest.mark.asyncio
    async def test_preserves_mutation_tools(self) -> None:
        """Safety: content + mutation tool (write_file) -> do NOT strip."""
        state = make_state(
            [
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "write_file",
                            "args": {"path": "/out.py", "content": "x"},
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_preserves_background_process_mutation(self) -> None:
        """Safety: content + bash_process_tool(kill) must NOT be stripped — the
        kill/stdin actions mutate process state and stripping would silently
        drop the cleanup side effect."""
        state = make_state(
            [
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "bash_process_tool",
                            "args": {"action": "kill", "pid": 123, "force": False},
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool_name", "args"),
        [
            ("ask_question_tool", {"question": "Which quarter?"}),
            ("browser_ask_human_tool", {"reason": "Enter SMS code"}),
        ],
    )
    async def test_preserves_interaction_ui_carriers(self, tool_name: str, args: dict[str, object]) -> None:
        """Safety: content + interaction/UI carrier must NOT be stripped — these
        are registry read-only but carry user-visible functionality (question,
        grant, render); dropping them breaks the interaction/UI chain."""
        state = make_state(
            [
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[{"id": "tc1", "name": tool_name, "args": args}],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_preserves_skill_market_mutation(self) -> None:
        """Safety: content + skill_market_tool(install) must NOT be stripped —
        the install/uninstall actions write the skill library; registry marks it
        read-only but the actions are effectful, so stripping would silently
        drop the install."""
        state = make_state(
            [
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "skill_market_tool",
                            "args": {
                                "action": "install",
                                "skill_id": "web-search",
                                "source": "market",
                            },
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_preserves_mixed_mutation_and_readonly(self) -> None:
        """Safety: content + mix of mutation and read-only tools -> do NOT strip."""
        state = make_state(
            [
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "file_read_tool",
                            "args": {"path": "/src/router.py"},
                        },
                        {
                            "id": "tc2",
                            "name": "execute_command",
                            "args": {"command": "echo hi"},
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_short_content_not_stripped(self) -> None:
        """Content < 500 chars is likely in-progress narration -> do NOT strip."""
        state = make_state(
            [
                AIMessage(
                    content="Let me check the file for you.",
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "file_read_tool",
                            "args": {"path": "/src/router.py"},
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_unfinished_content_not_stripped(self) -> None:
        """Content with 'unfinished' trailing marker -> do NOT strip."""
        content = self._long_answer() + "\n\nI'll now check the tests..."
        state = make_state(
            [
                AIMessage(
                    content=content,
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "file_read_tool",
                            "args": {"path": "/tests/"},
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_structure_not_stripped(self) -> None:
        """Long content without markdown structure -> do NOT strip."""
        content = "x " * 300  # >500 chars but no markdown structure
        state = make_state(
            [
                AIMessage(
                    content=content,
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "file_read_tool",
                            "args": {"path": "/file"},
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_finish_tools_bypass_mixed_guard(self) -> None:
        """When tool_calls include finish tool, take completion path not mixed guard."""
        state = make_state(
            [
                HumanMessage(content="Change main.py and tell me when it is done."),
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "request_answer_user_tool",
                            "args": {"reason": "done"},
                        },
                    ],
                ),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value._window = [
                CallRecord(
                    tool_name="file_write_tool",
                    args_hash="abc",
                    args={"path": "/src/app.py"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            result = await self.guard.aafter_model(state, None)

        assert reasons_of(result) == BlockReasons(verification=True)
        assert pending(result).text

    @pytest.mark.asyncio
    async def test_bash_tool_is_mutation(self) -> None:
        """bash_tool is classified as mutation -> do NOT strip."""
        state = make_state(
            [
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "bash_code_execute_tool",
                            "args": {"command": "ls"},
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_bash_code_execute_tool_is_mutation(self) -> None:
        """bash_code_execute_tool is classified as mutation -> do NOT strip."""
        state = make_state(
            [
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "bash_code_execute_tool",
                            "args": {"command": "pytest"},
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_content_no_trigger(self) -> None:
        """AIMessage with tool_calls but empty content -> do NOT trigger mixed guard."""
        state = make_state(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "file_read_tool",
                            "args": {"path": "/file"},
                        },
                    ],
                ),
            ]
        )
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_keeps_tool_calls_when_external_evidence_missing(self) -> None:
        """Freshness query + substantive content + read-only tools + NO evidence:
        must NOT strip — the agent needs to gather real data (anti-hallucination)."""
        state = make_state(
            [
                HumanMessage(content="今天最新的 AI 新闻是什么？"),
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "web_search_tool",
                            "args": {"query": "AI news today"},
                        },
                    ],
                ),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value._window = []
            result = await self.guard.aafter_model(state, None)

        assert result is None

    @pytest.mark.asyncio
    async def test_strips_when_external_evidence_exists(self) -> None:
        """Freshness query + substantive content + read-only tools WITH evidence:
        still strips to save tokens."""
        state = make_state(
            [
                HumanMessage(content="今天最新的 AI 新闻是什么？"),
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "web_search_tool",
                            "args": {"query": "AI news today"},
                        },
                    ],
                ),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value._window = [
                CallRecord(
                    tool_name="web_search_tool",
                    args_hash="evidence1",
                    args={"query": "AI news"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            result = await self.guard.aafter_model(state, None)

        assert result is not None
        ai_msg = result["messages"][0]
        assert ai_msg.tool_calls == []

    @pytest.mark.asyncio
    async def test_keeps_unannotated_mcp_tool_calls(self) -> None:
        """MCP tool without readOnlyHint (fail-closed non-read-only) must NOT be
        stripped — stripping could silently drop a side-effecting call such as
        booking/payment while the content claims completion."""
        state = make_state(
            [
                HumanMessage(content="帮我订一张明天去北京的火车票"),
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[
                        {
                            "id": "tc1",
                            "name": "mcp__payments__charge_card",
                            "args": {"amount": 553},
                        },
                    ],
                ),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value._window = []
            result = await self.guard.aafter_model(state, None)

        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("question", "stripped"),
        [
            pytest.param("用一段话介绍北京的气候特点", True, id="timeless-question-strips"),
            pytest.param("北京现在多少度？", False, id="live-question-keeps-the-lookup"),
        ],
    )
    async def test_annotated_readonly_mcp_tool_calls_strip_only_when_no_live_data_is_owed(
        self, question: str, stripped: bool
    ) -> None:
        """MCP tool with explicit readOnlyHint=True is safe to strip — keeps the token-saving optimization for
        genuinely read-only MCP servers — unless the question asks for the moment's data and no evidence exists yet:
        then the lookup must run."""
        tool_name = "mcp__meteo__get_temperature"
        register_ptc_safety_metadata(
            "mcp_meteo_skill",
            tool_name,
            SafetyMetadata(is_read_only=True, is_concurrent_safe=True),
            {"readOnlyHint": True},
        )
        state = make_state(
            [
                HumanMessage(content=question),
                AIMessage(
                    content=self._long_answer(),
                    tool_calls=[{"id": "tc1", "name": tool_name, "args": {"city": "Beijing"}}],
                ),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value._window = []
            result = await self.guard.aafter_model(state, None)

        if stripped:
            assert result is not None
            assert result["messages"][0].tool_calls == []
        else:
            assert result is None
