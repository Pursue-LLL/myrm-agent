"""Unit tests for step_to_label and _extract_input_summary."""

from __future__ import annotations

import pytest

from app.core.channel_bridge.executor_helpers import step_to_label


class TestStepToLabelRegistered:
    """Tests for registered tools (in _STEP_LABELS)."""

    def test_web_search_with_query(self) -> None:
        event: dict[str, object] = {
            "tool_name": "web_search_tool",
            "data": [{"query": "AI coding tools 2025"}],
        }
        result = step_to_label("web_search_tool", event)
        assert result == "🔍 Searching the web: AI coding tools 2025"

    def test_file_read_with_path(self) -> None:
        event: dict[str, object] = {
            "tool_name": "file_read_tool",
            "data": [{"file_path": "config/settings.yaml", "action_type": "read"}],
        }
        result = step_to_label("file_read_tool", event)
        assert result == "📄 Reading file: config/settings.yaml"

    def test_code_interpreter_with_code(self) -> None:
        event: dict[str, object] = {
            "tool_name": "code_interpreter_tool",
            "data": [{"code": "df.describe()"}],
        }
        result = step_to_label("code_interpreter_tool", event)
        assert result == "💻 Running code: df.describe()"

    def test_registered_tool_no_data_fallback(self) -> None:
        event: dict[str, object] = {"tool_name": "web_search_tool", "data": []}
        result = step_to_label("web_search_tool", event)
        assert result == "🔍 Searching the web..."

    def test_registered_tool_missing_data_key(self) -> None:
        event: dict[str, object] = {"tool_name": "file_read_tool"}
        result = step_to_label("file_read_tool", event)
        assert result == "📄 Reading file..."


class TestStepToLabelReviewingSources:
    """Tests for the reviewing_sources special branch."""

    def test_with_count(self) -> None:
        event: dict[str, object] = {"tool_name": None, "count": 5, "data": []}
        result = step_to_label("reviewing_sources", event)
        assert result == "📖 Reviewing 5 sources..."

    def test_without_count(self) -> None:
        event: dict[str, object] = {"tool_name": None, "count": 0, "data": []}
        result = step_to_label("reviewing_sources", event)
        assert result == "📖 Reviewing sources..."


class TestStepToLabelUnregistered:
    """Tests for unregistered tools (fallback path)."""

    def test_with_query_summary(self) -> None:
        event: dict[str, object] = {
            "tool_name": "memory_recall",
            "data": [{"query": "last meeting notes"}],
        }
        result = step_to_label("memory_search_tool", event)
        assert result == "⏳ **memory_recall** — last meeting notes"

    def test_with_url_summary(self) -> None:
        event: dict[str, object] = {
            "tool_name": "web_fetch",
            "data": [{"url": "https://docs.python.org/3/"}],
        }
        result = step_to_label("web_fetch_tool", event)
        assert result == "⏳ **web_fetch** — https://docs.python.org/3/"

    def test_bare_fallback_no_data(self) -> None:
        event: dict[str, object] = {"tool_name": "custom_tool", "data": []}
        result = step_to_label("custom_tool_tool", event)
        assert result == "⏳ **custom_tool**"

    def test_tool_name_none_uses_step_key(self) -> None:
        event: dict[str, object] = {"tool_name": None, "data": []}
        result = step_to_label("my_custom_tool", event)
        assert result == "⏳ **my_custom**"

    def test_tool_name_missing_uses_step_key(self) -> None:
        event: dict[str, object] = {"data": []}
        result = step_to_label("another_tool", event)
        assert result == "⏳ **another**"


class TestStepToLabelError:
    """Tests for tool error handling."""

    def test_tool_error_suffix(self) -> None:
        result = step_to_label("web_search_tool_tool_error", {})
        assert result == "⚠️ Tool error, retrying..."

    def test_any_error_suffix(self) -> None:
        result = step_to_label("custom_thing_tool_error", {"tool_name": "custom"})
        assert result == "⚠️ Tool error, retrying..."


class TestExtractInputSummaryTruncation:
    """Tests for summary truncation at 80 chars."""

    def test_long_query_truncated(self) -> None:
        long_query = "A" * 200
        event: dict[str, object] = {
            "tool_name": "search",
            "data": [{"query": long_query}],
        }
        result = step_to_label("search_tool", event)
        assert "…" in result
        assert len(result) < 200

    def test_multiline_code_flattened(self) -> None:
        event: dict[str, object] = {
            "tool_name": "code_interpreter_tool",
            "data": [{"code": "line1\nline2\nline3"}],
        }
        result = step_to_label("code_interpreter_tool", event)
        assert "\n" not in result
        assert "line1 line2 line3" in result


class TestExtractInputSummaryEdgeCases:
    """Tests for edge cases in _extract_input_summary."""

    def test_data_not_list(self) -> None:
        event: dict[str, object] = {"tool_name": "x", "data": "not_a_list"}
        result = step_to_label("x_tool", event)
        assert result == "⏳ **x**"

    def test_data_first_not_dict(self) -> None:
        event: dict[str, object] = {"tool_name": "x", "data": ["string_item"]}
        result = step_to_label("x_tool", event)
        assert result == "⏳ **x**"

    def test_data_dict_no_known_keys(self) -> None:
        event: dict[str, object] = {"tool_name": "x", "data": [{"unknown_key": "val"}]}
        result = step_to_label("x_tool", event)
        assert result == "⏳ **x**"

    @pytest.mark.parametrize("value", [None, 123, True, []])
    def test_non_string_values_ignored(self, value: object) -> None:
        event: dict[str, object] = {"tool_name": "x", "data": [{"query": value}]}
        result = step_to_label("x_tool", event)
        assert result == "⏳ **x**"
