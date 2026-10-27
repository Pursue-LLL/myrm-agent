"""Tests for the CLI event parser's less common branches."""

from __future__ import annotations

from myrm_agent_harness.toolkits.acp.types import RuntimeEventType


class TestParserMissingBranches:
    """Tests for parser branches the main parser tests do not reach."""

    def test_parse_codex_item_reasoning_empty(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime.cli.parser import (
            parse_codex_item_event,
        )

        event = parse_codex_item_event(
            {"type": "item.completed", "item": {"type": "reasoning", "text": ""}},
            "s1",
        )
        assert event is None

    def test_parse_codex_item_unknown_type(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime.cli.parser import (
            parse_codex_item_event,
        )

        event = parse_codex_item_event(
            {"type": "item.completed", "item": {"type": "annotation", "text": "foo"}},
            "s1",
        )
        assert event is None

    def test_parse_thinking_empty(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime.cli.parser import parse_thinking

        event = parse_thinking({"thinking": ""}, "s1")
        assert event is None

    def test_parse_thinking_with_text_field(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime.cli.parser import parse_thinking

        event = parse_thinking({"text": "reasoning content"}, "s1")
        assert event is not None
        assert event.type == RuntimeEventType.REASONING_DELTA
        assert event.data["content"] == "reasoning content"

    def test_extract_text_empty_content_list(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime.cli.parser import (
            extract_text_from_event,
        )

        result = extract_text_from_event({"content": []})
        assert result is None

    def test_extract_text_non_text_blocks(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime.cli.parser import (
            extract_text_from_event,
        )

        result = extract_text_from_event({"content": [{"type": "image", "url": "http://example.com"}]})
        assert result is None
