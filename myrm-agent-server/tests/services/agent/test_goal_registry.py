"""ServerGoalManager & GoalRegistry unit tests.

Tests cover:
- evaluate_semantic: JSON parsing, markdown-fenced JSON, inline JSON,
  boolean normalization, fallback prefix matching, error handling
- _parse_judge_json helper: all extraction strategies
- GoalRegistry: singleton behavior, unregister
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.utils.chat_utils import parse_judge_json
from app.services.agent.goals.goal_registry import (
    GoalRegistry,
    ServerGoalManager,
)


@pytest.fixture
def mock_storage():
    return AsyncMock()


# ── parse_judge_json ──


class TestParseJudgeJson:
    def test_direct_json(self):
        result = parse_judge_json('{"done": true, "reason": "completed"}')
        assert result is not None
        assert result["done"] is True
        assert result["reason"] == "completed"

    def test_markdown_fenced(self):
        raw = 'Here is my verdict:\n```json\n{"done": false, "reason": "not yet"}\n```'
        result = parse_judge_json(raw)
        assert result is not None
        assert result["done"] is False

    def test_inline_json(self):
        raw = 'Based on my analysis, {"done": true, "reason": "all tasks finished"} is my answer.'
        result = parse_judge_json(raw)
        assert result is not None
        assert result["done"] is True

    def test_boolean_string_normalization(self):
        raw = '{"done": "True", "reason": "completed"}'
        result = parse_judge_json(raw)
        assert result is not None
        assert result["done"] is True

    def test_boolean_string_false(self):
        raw = '{"done": "False", "reason": "incomplete"}'
        result = parse_judge_json(raw)
        assert result is not None
        assert result["done"] is False

    def test_no_done_key(self):
        raw = '{"status": "ok"}'
        result = parse_judge_json(raw)
        assert result is None

    def test_invalid_json(self):
        result = parse_judge_json("This is not JSON at all")
        assert result is None

    def test_empty_string(self):
        result = parse_judge_json("")
        assert result is None

    def test_unescaped_newline_in_reason(self):
        raw = '{"done": false, "reason": "still\\nrunning"}'
        result = parse_judge_json(raw)
        assert result is not None
        assert result["done"] is False


# ── done 布尔归一化（经 parse_judge_json）──


class TestNormalizeDone:
    def test_bool_passthrough(self):
        assert parse_judge_json('{"done": true}')["done"] is True
        assert parse_judge_json('{"done": false}')["done"] is False

    def test_string_true_variants(self):
        for val in ("true", "True", "TRUE", "yes", "Yes", "1"):
            assert parse_judge_json(f'{{"done": "{val}"}}')["done"] is True

    def test_string_false_variants(self):
        for val in ("false", "False", "no", "No", "0", "nope"):
            assert parse_judge_json(f'{{"done": "{val}"}}')["done"] is False


# ── ServerGoalManager.evaluate_semantic ──


def _mock_platform_llm(content: str) -> MagicMock:
    llm = MagicMock()
    response = MagicMock()
    response.content = content
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


class TestEvaluateSemantic:
    @pytest.fixture(autouse=True)
    def _patch_platform_config(self):
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(return_value=_mock_platform_llm('{"done": false, "reason": "x"}')),
        ):
            yield

    @pytest.mark.asyncio
    async def test_json_done_true(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(return_value=_mock_platform_llm('{"done": true, "reason": "goal achieved"}')),
        ):
            result = await manager.evaluate_semantic("criteria", "content")
        assert result.passed is True
        assert "goal achieved" in result.reason

    @pytest.mark.asyncio
    async def test_json_done_false(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(return_value=_mock_platform_llm('{"done": false, "reason": "still in progress"}')),
        ):
            result = await manager.evaluate_semantic("criteria", "content")
        assert result.passed is False
        assert "still in progress" in result.reason

    @pytest.mark.asyncio
    async def test_markdown_fenced_json(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        raw = '```json\n{"done": true, "reason": "all done"}\n```'
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(return_value=_mock_platform_llm(raw)),
        ):
            result = await manager.evaluate_semantic("criteria", "content")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_prefix_fallback_pass(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(return_value=_mock_platform_llm("PASS: looks good")),
        ):
            result = await manager.evaluate_semantic("criteria", "content")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_prefix_fallback_fail(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(return_value=_mock_platform_llm("FAIL: Too short")),
        ):
            result = await manager.evaluate_semantic("criteria", "content")
        assert result.passed is False
        assert "FAIL: Too short" in result.reason

    @pytest.mark.asyncio
    async def test_unparseable_output_sets_parse_failed(self, mock_storage):
        """Completely unparseable judge output signals parse_failed for circuit breaker."""
        manager = ServerGoalManager(mock_storage)
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(
                return_value=_mock_platform_llm("I cannot evaluate this in JSON format sorry"),
            ),
        ):
            result = await manager.evaluate_semantic("criteria", "content")
        assert result.passed is False
        assert result.parse_failed is True
        assert "I cannot evaluate" in result.reason

    @pytest.mark.asyncio
    async def test_prefix_fallback_pass_no_parse_failed(self, mock_storage):
        """PASS-prefix fallback is a valid signal, not a parse failure."""
        manager = ServerGoalManager(mock_storage)
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(return_value=_mock_platform_llm("PASS: all good")),
        ):
            result = await manager.evaluate_semantic("criteria", "content")
        assert result.passed is True
        assert result.parse_failed is False

    @pytest.mark.asyncio
    async def test_llm_error_failopen(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        failing_llm = MagicMock()
        failing_llm.ainvoke = AsyncMock(side_effect=RuntimeError("API timeout"))
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(return_value=failing_llm),
        ):
            result = await manager.evaluate_semantic("criteria", "content")
        assert result.passed is False
        assert "Server evaluation failed" in result.reason
        assert "API timeout" in (result.error_logs or "")
        assert result.parse_failed is False

    @pytest.mark.asyncio
    async def test_system_user_prompt_separation(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        captured_messages: list[object] = []

        async def mock_ainvoke(messages: list[object], **kwargs: object) -> MagicMock:
            captured_messages.extend(messages)
            response = MagicMock()
            response.content = '{"done": false, "reason": "x"}'
            return response

        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_ainvoke
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(return_value=mock_llm),
        ):
            await manager.evaluate_semantic("system criteria", "user content")

        from langchain_core.messages import HumanMessage, SystemMessage

        assert len(captured_messages) == 2
        assert isinstance(captured_messages[0], SystemMessage)
        assert captured_messages[0].content == "system criteria"
        assert isinstance(captured_messages[1], HumanMessage)
        assert captured_messages[1].content == "user content"

    @pytest.mark.asyncio
    async def test_load_platform_llm_uses_zero_temperature(self, mock_storage):
        """Platform judge path requests deterministic temperature via load_platform_llm."""
        manager = ServerGoalManager(mock_storage)
        load_mock = AsyncMock(return_value=_mock_platform_llm('{"done": false, "reason": "x"}'))
        with patch("app.services.agent.platform_config.load_platform_llm", new=load_mock):
            await manager.evaluate_semantic("criteria", "content")

        load_mock.assert_awaited_once_with(streaming=False, temperature=0.0)

    @pytest.mark.asyncio
    async def test_reasoning_content_fallback(self, mock_storage):
        """Reasoning models may leave content empty; extract_answer_text reads additional_kwargs."""
        manager = ServerGoalManager(mock_storage)
        llm = MagicMock()
        response = MagicMock()
        response.content = ""
        response.additional_kwargs = {
            "reasoning_content": '{"done": true, "reason": "found in reasoning"}',
        }
        llm.ainvoke = AsyncMock(return_value=response)
        with patch(
            "app.services.agent.platform_config.load_platform_llm",
            new=AsyncMock(return_value=llm),
        ):
            result = await manager.evaluate_semantic("criteria", "content")
        assert result.passed is True
        assert "found in reasoning" in (result.reason or "")

    @pytest.mark.asyncio
    async def test_evaluate_semantic_with_vision_tool(self, mock_storage):
        """Test that vision tools trigger screenshot extraction."""
        manager = ServerGoalManager(mock_storage, session_id="test-session")

        mock_gateway = MagicMock()
        mock_browser_session = AsyncMock()
        mock_browser_session.extract_screenshot.return_value = "fake_base64"
        mock_gateway.get_active_browser_session.return_value = mock_browser_session

        captured_messages: list[object] = []

        async def mock_ainvoke(messages: list[object], **kwargs: object) -> MagicMock:
            captured_messages.extend(messages)
            response = MagicMock()
            response.content = '{"done": false, "reason": "x"}'
            return response

        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_ainvoke

        class FakeToolMessage:
            type = "tool"
            name = "browser_interact_tool"

        with (
            patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway),
            patch(
                "app.services.agent.platform_config.load_platform_llm",
                new=AsyncMock(return_value=mock_llm),
            ),
        ):
            await manager.evaluate_semantic("criteria", "content", context_messages=[FakeToolMessage()])

        from langchain_core.messages import HumanMessage

        user_msg = next(m for m in captured_messages if isinstance(m, HumanMessage))
        assert isinstance(user_msg.content, list)
        assert user_msg.content[0]["type"] == "text"
        assert user_msg.content[1]["type"] == "image_url"
        assert "fake_base64" in user_msg.content[1]["image_url"]["url"]

        mock_browser_session.extract_screenshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_evaluate_semantic_without_vision_tool(self, mock_storage):
        """Test that non-vision tools skip screenshot extraction even if session exists."""
        manager = ServerGoalManager(mock_storage, session_id="test-session")

        mock_gateway = MagicMock()
        mock_browser_session = AsyncMock()
        mock_gateway.get_active_browser_session.return_value = mock_browser_session

        captured_messages: list[object] = []

        async def mock_ainvoke(messages: list[object], **kwargs: object) -> MagicMock:
            captured_messages.extend(messages)
            response = MagicMock()
            response.content = '{"done": false, "reason": "x"}'
            return response

        mock_llm = MagicMock()
        mock_llm.ainvoke = mock_ainvoke

        class FakeToolMessage:
            type = "tool"
            name = "calculator_tool"

        with (
            patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway),
            patch(
                "app.services.agent.platform_config.load_platform_llm",
                new=AsyncMock(return_value=mock_llm),
            ),
        ):
            await manager.evaluate_semantic("criteria", "content", context_messages=[FakeToolMessage()])

        from langchain_core.messages import HumanMessage

        user_msg = next(m for m in captured_messages if isinstance(m, HumanMessage))
        assert user_msg.content == "content"

        mock_browser_session.extract_screenshot.assert_not_awaited()


# ── GoalRegistry ──


class TestGoalRegistry:
    def test_singleton_per_session(self):
        session_id = "test-registry-singleton"
        with patch("app.platform_utils.get_storage_provider", return_value=AsyncMock()):
            provider1 = GoalRegistry.get_or_create_provider(session_id)
            assert isinstance(provider1, ServerGoalManager)

            provider2 = GoalRegistry.get_or_create_provider(session_id)
            assert provider1 is provider2

            GoalRegistry.unregister(session_id)

    def test_get_provider_returns_none(self):
        assert GoalRegistry.get_provider("nonexistent-session") is None

    def test_unregister(self):
        session_id = "test-registry-unregister"
        with patch("app.platform_utils.get_storage_provider", return_value=AsyncMock()):
            GoalRegistry.get_or_create_provider(session_id)
            assert GoalRegistry.get_provider(session_id) is not None

            GoalRegistry.unregister(session_id)
            assert GoalRegistry.get_provider(session_id) is None
