"""ServerGoalManager & GoalRegistry unit tests.

Tests cover:
- evaluate_semantic: JSON parsing, markdown-fenced JSON, inline JSON,
  boolean normalization, fallback prefix matching, error handling
- _parse_judge_json helper: all extraction strategies
- GoalRegistry: singleton behavior, unregister
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.goal_registry import (
    GoalRegistry,
    ServerGoalManager,
    _normalize_done,
    _parse_judge_json,
)


@pytest.fixture
def mock_storage():
    return AsyncMock()


# ── _parse_judge_json ──


class TestParseJudgeJson:
    def test_direct_json(self):
        result = _parse_judge_json('{"done": true, "reason": "completed"}')
        assert result is not None
        assert result["done"] is True
        assert result["reason"] == "completed"

    def test_markdown_fenced(self):
        raw = 'Here is my verdict:\n```json\n{"done": false, "reason": "not yet"}\n```'
        result = _parse_judge_json(raw)
        assert result is not None
        assert result["done"] is False

    def test_inline_json(self):
        raw = 'Based on my analysis, {"done": true, "reason": "all tasks finished"} is my answer.'
        result = _parse_judge_json(raw)
        assert result is not None
        assert result["done"] is True

    def test_boolean_string_normalization(self):
        raw = '{"done": "True", "reason": "completed"}'
        result = _parse_judge_json(raw)
        assert result is not None
        assert result["done"] is True

    def test_boolean_string_false(self):
        raw = '{"done": "False", "reason": "incomplete"}'
        result = _parse_judge_json(raw)
        assert result is not None
        assert result["done"] is False

    def test_no_done_key(self):
        raw = '{"status": "ok"}'
        result = _parse_judge_json(raw)
        assert result is None

    def test_invalid_json(self):
        result = _parse_judge_json("This is not JSON at all")
        assert result is None

    def test_empty_string(self):
        result = _parse_judge_json("")
        assert result is None


# ── _normalize_done ──


class TestNormalizeDone:
    def test_bool_passthrough(self):
        assert _normalize_done({"done": True})["done"] is True
        assert _normalize_done({"done": False})["done"] is False

    def test_string_true_variants(self):
        for val in ("true", "True", "TRUE", "yes", "Yes", "1"):
            assert _normalize_done({"done": val})["done"] is True

    def test_string_false_variants(self):
        for val in ("false", "False", "no", "No", "0", "nope"):
            assert _normalize_done({"done": val})["done"] is False


# ── ServerGoalManager.evaluate_semantic ──

_MOCK_LLM_KWARGS = {"model": "test-model", "api_key": "test-key"}


class TestEvaluateSemantic:
    @pytest.fixture(autouse=True)
    def _patch_platform_config(self):
        with patch(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            new=AsyncMock(return_value=_MOCK_LLM_KWARGS),
        ):
            yield

    @pytest.mark.asyncio
    async def test_json_done_true(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch("litellm.acompletion") as mock:
            mock.return_value = AsyncMock(
                choices=[AsyncMock(message=AsyncMock(content='{"done": true, "reason": "goal achieved"}'))]
            )
            result = await manager.evaluate_semantic("criteria", "content")
            assert result.passed is True
            assert "goal achieved" in result.reason

    @pytest.mark.asyncio
    async def test_json_done_false(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch("litellm.acompletion") as mock:
            mock.return_value = AsyncMock(
                choices=[AsyncMock(message=AsyncMock(content='{"done": false, "reason": "still in progress"}'))]
            )
            result = await manager.evaluate_semantic("criteria", "content")
            assert result.passed is False
            assert "still in progress" in result.reason

    @pytest.mark.asyncio
    async def test_markdown_fenced_json(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        raw = '```json\n{"done": true, "reason": "all done"}\n```'
        with patch("litellm.acompletion") as mock:
            mock.return_value = AsyncMock(choices=[AsyncMock(message=AsyncMock(content=raw))])
            result = await manager.evaluate_semantic("criteria", "content")
            assert result.passed is True

    @pytest.mark.asyncio
    async def test_prefix_fallback_pass(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch("litellm.acompletion") as mock:
            mock.return_value = AsyncMock(choices=[AsyncMock(message=AsyncMock(content="PASS: looks good"))])
            result = await manager.evaluate_semantic("criteria", "content")
            assert result.passed is True

    @pytest.mark.asyncio
    async def test_prefix_fallback_fail(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch("litellm.acompletion") as mock:
            mock.return_value = AsyncMock(choices=[AsyncMock(message=AsyncMock(content="FAIL: Too short"))])
            result = await manager.evaluate_semantic("criteria", "content")
            assert result.passed is False
            assert "FAIL: Too short" in result.reason

    @pytest.mark.asyncio
    async def test_llm_error_failopen(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch("litellm.acompletion", side_effect=RuntimeError("API timeout")):
            result = await manager.evaluate_semantic("criteria", "content")
            assert result.passed is False
            assert "Server evaluation failed" in result.reason
            assert "API timeout" in (result.error_logs or "")

    @pytest.mark.asyncio
    async def test_system_user_prompt_separation(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch("litellm.acompletion") as mock:
            mock.return_value = AsyncMock(choices=[AsyncMock(message=AsyncMock(content='{"done": false, "reason": "x"}'))])
            await manager.evaluate_semantic("system criteria", "user content")

            kwargs = mock.call_args[1]
            messages = kwargs["messages"]
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "system criteria"
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "user content"

    @pytest.mark.asyncio
    async def test_max_tokens_and_timeout(self, mock_storage):
        manager = ServerGoalManager(mock_storage)
        with patch("litellm.acompletion") as mock:
            mock.return_value = AsyncMock(choices=[AsyncMock(message=AsyncMock(content='{"done": false, "reason": "x"}'))])
            await manager.evaluate_semantic("criteria", "content")

            kwargs = mock.call_args[1]
            assert kwargs["max_tokens"] == 1024
            assert kwargs["timeout"] == 10
            assert kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_reasoning_content_fallback(self, mock_storage):
        """When content is empty but reasoning_content has the answer."""
        manager = ServerGoalManager(mock_storage)
        with patch("litellm.acompletion") as mock:
            msg = AsyncMock()
            msg.content = ""
            msg.reasoning_content = '{"done": true, "reason": "found in reasoning"}'
            mock.return_value = AsyncMock(choices=[AsyncMock(message=msg)])

            result = await manager.evaluate_semantic("criteria", "content")
            assert result.passed is True
            assert "found in reasoning" in result.reason

    @pytest.mark.asyncio
    async def test_evaluate_semantic_with_vision_tool(self, mock_storage):
        """Test that vision tools trigger screenshot extraction."""
        manager = ServerGoalManager(mock_storage, session_id="test-session")

        from unittest.mock import MagicMock

        mock_gateway = MagicMock()
        mock_browser_session = AsyncMock()
        mock_browser_session.extract_screenshot.return_value = "fake_base64"
        mock_gateway.get_active_browser_session.return_value = mock_browser_session

        with (
            patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway),
            patch("litellm.acompletion") as mock,
        ):
            mock.return_value = AsyncMock(choices=[AsyncMock(message=AsyncMock(content='{"done": false, "reason": "x"}'))])

            class FakeToolMessage:
                type = "tool"
                name = "browser_interact_tool"

            await manager.evaluate_semantic("criteria", "content", context_messages=[FakeToolMessage()])

            kwargs = mock.call_args[1]
            messages = kwargs["messages"]
            assert len(messages) == 2
            user_msg = messages[1]["content"]
            assert isinstance(user_msg, list)
            assert user_msg[0]["type"] == "text"
            assert user_msg[1]["type"] == "image_url"
            assert "fake_base64" in user_msg[1]["image_url"]["url"]

            mock_browser_session.extract_screenshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_evaluate_semantic_without_vision_tool(self, mock_storage):
        """Test that non-vision tools skip screenshot extraction even if session exists."""
        manager = ServerGoalManager(mock_storage, session_id="test-session")

        from unittest.mock import MagicMock

        mock_gateway = MagicMock()
        mock_browser_session = AsyncMock()
        mock_gateway.get_active_browser_session.return_value = mock_browser_session

        with (
            patch("app.services.agent.gateway.get_agent_gateway", return_value=mock_gateway),
            patch("litellm.acompletion") as mock,
        ):
            mock.return_value = AsyncMock(choices=[AsyncMock(message=AsyncMock(content='{"done": false, "reason": "x"}'))])

            class FakeToolMessage:
                type = "tool"
                name = "calculator_tool"

            await manager.evaluate_semantic("criteria", "content", context_messages=[FakeToolMessage()])

            kwargs = mock.call_args[1]
            messages = kwargs["messages"]
            assert len(messages) == 2
            user_msg = messages[1]["content"]
            assert isinstance(user_msg, str)

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
