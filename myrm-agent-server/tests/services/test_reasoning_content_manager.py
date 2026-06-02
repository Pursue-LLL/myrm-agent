"""Tests for ReasoningContentManager."""

import pytest

from app.services.reasoning_content_manager import ReasoningContentManager


@pytest.fixture
def manager():
    return ReasoningContentManager()


class TestReasoningContentManager:
    """Test reasoning content lifecycle management."""

    def test_ensure_reasoning_content_non_assistant(self, manager):
        """Non-assistant messages are returned unchanged."""
        message = {"role": "user", "content": "hello"}
        result = manager.ensure_reasoning_content(message, "deepseek", "deepseek-v4-flash")
        assert result == message

    def test_ensure_reasoning_content_no_echo_needed(self, manager):
        """Messages for models that don't require echo are returned unchanged."""
        message = {"role": "assistant", "content": "answer", "tool_calls": []}
        result = manager.ensure_reasoning_content(message, "openai", "gpt-4o")
        assert result == message

    def test_ensure_reasoning_content_already_present(self, manager):
        """Messages with existing reasoning_content are returned unchanged."""
        message = {
            "role": "assistant",
            "content": "answer",
            "tool_calls": [],
            "reasoning_content": "I think...",
        }
        result = manager.ensure_reasoning_content(message, "deepseek", "deepseek-v4-flash")
        assert result["reasoning_content"] == "I think..."

    def test_ensure_reasoning_content_from_reasoning(self, manager):
        """Messages with reasoning field are promoted to reasoning_content."""
        message = {
            "role": "assistant",
            "content": "answer",
            "tool_calls": [],
            "reasoning": "I think...",
        }
        result = manager.ensure_reasoning_content(message, "deepseek", "deepseek-v4-flash")
        assert result["reasoning_content"] == "I think..."

    def test_ensure_reasoning_content_placeholder_for_tool_calls(self, manager):
        """Messages with tool_calls get placeholder if reasoning_content missing."""
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "function": {"name": "test"}}],
        }
        result = manager.ensure_reasoning_content(message, "deepseek", "deepseek-v4-flash")
        assert result["reasoning_content"] == " "

    def test_ensure_reasoning_content_no_placeholder_without_tool_calls(self, manager):
        """Messages without tool_calls don't get placeholder."""
        message = {"role": "assistant", "content": "answer"}
        result = manager.ensure_reasoning_content(message, "deepseek", "deepseek-v4-flash")
        assert "reasoning_content" not in result

    def test_validate_reasoning_content_pass(self, manager):
        """Validation passes when all assistant tool-call messages have reasoning_content."""
        messages = [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1"}],
                "reasoning_content": "I think...",
            },
        ]
        assert manager.validate_reasoning_content(messages, "deepseek", "deepseek-v4-flash")

    def test_validate_reasoning_content_fail(self, manager):
        """Validation fails when assistant tool-call message missing reasoning_content."""
        messages = [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1"}],
            },
        ]
        assert not manager.validate_reasoning_content(messages, "deepseek", "deepseek-v4-flash")

    def test_validate_reasoning_content_no_echo_needed(self, manager):
        """Validation passes for models that don't require echo."""
        messages = [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1"}],
            },
        ]
        assert manager.validate_reasoning_content(messages, "openai", "gpt-4o")

    def test_copy_reasoning_content_for_api_preserves_existing(self, manager):
        """Existing reasoning_content is preserved verbatim."""
        source = {
            "role": "assistant",
            "content": "",
            "reasoning_content": "I think...",
        }
        api_msg = {}
        result = manager.copy_reasoning_content_for_api(
            source, api_msg, "deepseek", "deepseek-v4-flash"
        )
        assert result["reasoning_content"] == "I think..."

    def test_copy_reasoning_content_for_api_upgrades_empty(self, manager):
        """Empty reasoning_content is upgraded to placeholder for models that require echo."""
        source = {
            "role": "assistant",
            "content": "",
            "reasoning_content": "",
        }
        api_msg = {}
        result = manager.copy_reasoning_content_for_api(
            source, api_msg, "deepseek", "deepseek-v4-flash"
        )
        assert result["reasoning_content"] == " "

    def test_copy_reasoning_content_for_api_promotes_reasoning(self, manager):
        """Reasoning field is promoted to reasoning_content."""
        source = {
            "role": "assistant",
            "content": "",
            "reasoning": "I think...",
        }
        api_msg = {}
        result = manager.copy_reasoning_content_for_api(
            source, api_msg, "deepseek", "deepseek-v4-flash"
        )
        assert result["reasoning_content"] == "I think..."

    def test_copy_reasoning_content_for_api_injects_placeholder(self, manager):
        """Placeholder is injected for models that require echo when reasoning_content missing."""
        source = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1"}],
        }
        api_msg = {}
        result = manager.copy_reasoning_content_for_api(
            source, api_msg, "deepseek", "deepseek-v4-flash"
        )
        assert result["reasoning_content"] == " "

    def test_copy_reasoning_content_for_api_no_echo_needed(self, manager):
        """No reasoning_content is added for models that don't require echo."""
        source = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1"}],
        }
        api_msg = {}
        result = manager.copy_reasoning_content_for_api(
            source, api_msg, "openai", "gpt-4o"
        )
        assert "reasoning_content" not in result

    def test_process_message_for_storage(self, manager):
        """Messages are processed for storage with reasoning_content ensured."""
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1"}],
        }
        result = manager.process_message_for_storage(
            message, "deepseek", "deepseek-v4-flash"
        )
        assert result["reasoning_content"] == " "
