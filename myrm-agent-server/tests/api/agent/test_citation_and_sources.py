"""Unit tests for citation pipeline: StreamContentCollector sources + CitationRulesMiddleware.

Validates:
1. StreamContentCollector correctly collects, deduplicates, and merges sources
2. CitationRulesMiddleware injection logic (final_answer detection, UNTRUSTED_DATA scanning)
3. Source model structure integrity for frontend consumption
"""

import pytest

from app.services.agent.streaming_support.stream_collector import StreamContentCollector


@pytest.fixture
def collector() -> StreamContentCollector:
    return StreamContentCollector(
        chat_id="test_citation", sibling_group_id="sib_cite_1"
    )


class TestSourcesCollection:
    """Tests for sources event collection in StreamContentCollector."""

    def test_collects_single_source(self, collector: StreamContentCollector) -> None:
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {
                        "url": "https://example.com",
                        "title": "Example",
                        "snippet": "test snippet",
                    }
                ],
            }
        )

        extra = collector.extra_data
        assert extra is not None
        assert "sources" in extra
        assert len(extra["sources"]) == 1
        assert extra["sources"][0]["url"] == "https://example.com"
        assert extra["sources"][0]["title"] == "Example"

    def test_collects_multiple_sources(self, collector: StreamContentCollector) -> None:
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {"url": "https://a.com", "title": "A"},
                    {"url": "https://b.com", "title": "B"},
                    {"url": "https://c.com", "title": "C"},
                ],
            }
        )

        extra = collector.extra_data
        assert extra is not None
        assert len(extra["sources"]) == 3

    def test_accumulates_sources_across_events(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event(
            {
                "type": "sources",
                "data": [{"url": "https://first.com", "title": "First"}],
            }
        )
        collector.feed_event(
            {
                "type": "sources",
                "data": [{"url": "https://second.com", "title": "Second"}],
            }
        )

        extra = collector.extra_data
        assert extra is not None
        assert len(extra["sources"]) == 2
        urls = [s["url"] for s in extra["sources"]]
        assert "https://first.com" in urls
        assert "https://second.com" in urls

    def test_snapshot_deduplicates_sources_by_url(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {
                        "url": "https://dup.com",
                        "title": "First Version",
                        "snippet": "v1",
                    },
                ],
            }
        )
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {
                        "url": "https://dup.com",
                        "title": "Updated Version",
                        "snippet": "v2",
                    },
                ],
            }
        )

        snapshot = collector.get_snapshot()
        assert len(snapshot["sources"]) == 1
        assert snapshot["sources"][0]["title"] == "Updated Version"

    def test_sources_preserve_citation_redirect_url(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {
                        "url": "https://real.example/article",
                        "redirect_url": "https://redirect.example/r",
                        "title": "Resolved",
                    },
                ],
            }
        )

        extra = collector.extra_data
        assert extra is not None
        assert extra["sources"][0]["url"] == "https://real.example/article"
        assert extra["sources"][0]["redirect_url"] == "https://redirect.example/r"

    def test_sources_without_url_are_preserved(
        self, collector: StreamContentCollector
    ) -> None:
        """KB sources may lack URL but should still be collected."""
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {"kb_name": "docs", "filename": "readme.md", "snippet": "content"},
                ],
            }
        )

        extra = collector.extra_data
        assert extra is not None
        assert len(extra["sources"]) == 1
        assert extra["sources"][0]["kb_name"] == "docs"

    def test_mixed_source_types(self, collector: StreamContentCollector) -> None:
        """Web, KB, and MCP sources coexist correctly."""
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {"url": "https://web.com", "title": "Web", "type": "web_search"},
                    {"kb_name": "knowledge", "filename": "doc.pdf", "type": "kb"},
                    {"url": "https://mcp.com", "title": "MCP Tool", "type": "mcp"},
                ],
            }
        )

        extra = collector.extra_data
        assert extra is not None
        assert len(extra["sources"]) == 3
        types = {s.get("type") for s in extra["sources"]}
        assert types == {"web_search", "kb", "mcp"}

    def test_invalid_sources_data_ignored(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event(
            {
                "type": "sources",
                "data": "not_a_list",
            }
        )
        assert collector.extra_data is None

    def test_sources_with_non_dict_items_filtered(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {"url": "https://valid.com", "title": "Valid"},
                    "invalid_item",
                    42,
                    None,
                ],
            }
        )

        extra = collector.extra_data
        assert extra is not None
        assert len(extra["sources"]) == 1
        assert extra["sources"][0]["url"] == "https://valid.com"

    def test_empty_sources_list_no_extra_data(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event(
            {
                "type": "sources",
                "data": [],
            }
        )
        assert collector.extra_data is None


class TestSourcesInSnapshot:
    """Tests for sources deduplication in get_snapshot()."""

    def test_snapshot_preserves_source_order(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {"url": "https://third.com", "title": "Third"},
                    {"url": "https://first.com", "title": "First"},
                    {"url": "https://second.com", "title": "Second"},
                ],
            }
        )

        snapshot = collector.get_snapshot()
        urls = [s["url"] for s in snapshot["sources"]]
        assert urls == ["https://third.com", "https://first.com", "https://second.com"]

    def test_snapshot_merge_updates_existing_source(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {"url": "https://update.com", "title": "Old", "snippet": "old"}
                ],
            }
        )
        collector.feed_event(
            {
                "type": "sources",
                "data": [
                    {
                        "url": "https://update.com",
                        "snippet": "new",
                        "extra_field": "added",
                    }
                ],
            }
        )

        snapshot = collector.get_snapshot()
        source = snapshot["sources"][0]
        assert source["snippet"] == "new"
        assert source["extra_field"] == "added"
        assert source["title"] == "Old"


class TestCitationRulesMiddlewareLogic:
    """Tests for citation_rules_middleware internal helpers."""

    def test_is_final_answer_phase_with_tool_message(self) -> None:
        from langchain_core.messages import HumanMessage, ToolMessage

        from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
            _is_final_answer_phase,
        )

        messages = [
            HumanMessage(content="hello"),
            ToolMessage(
                content="result", name="request_answer_user_tool", tool_call_id="tc1"
            ),
        ]
        assert _is_final_answer_phase(messages) is True

    def test_is_final_answer_phase_without_tool_message(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
            _is_final_answer_phase,
        )

        messages = [
            HumanMessage(content="hello"),
            AIMessage(content="world"),
        ]
        assert _is_final_answer_phase(messages) is False

    def test_is_final_answer_phase_wrong_tool_name(self) -> None:
        from langchain_core.messages import ToolMessage

        from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
            _is_final_answer_phase,
        )

        messages = [
            ToolMessage(content="result", name="other_tool", tool_call_id="tc1"),
        ]
        assert _is_final_answer_phase(messages) is False

    def test_is_final_answer_phase_empty(self) -> None:
        from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
            _is_final_answer_phase,
        )

        assert _is_final_answer_phase([]) is False

    def test_has_external_sources_with_untrusted_data(self) -> None:
        from langchain_core.messages import HumanMessage, ToolMessage

        from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
            _has_external_sources_in_current_turn,
        )

        messages = [
            HumanMessage(content="search for python"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA web_search>>>\nPython is a language\n<<<END_UNTRUSTED_DATA>>>",
                name="web_search",
                tool_call_id="tc1",
            ),
        ]
        assert _has_external_sources_in_current_turn(messages) is True

    def test_has_external_sources_without_untrusted_data(self) -> None:
        from langchain_core.messages import HumanMessage, ToolMessage

        from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
            _has_external_sources_in_current_turn,
        )

        messages = [
            HumanMessage(content="hello"),
            ToolMessage(
                content="regular tool output", name="calculator", tool_call_id="tc1"
            ),
        ]
        assert _has_external_sources_in_current_turn(messages) is False

    def test_has_external_sources_only_scans_current_turn(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
            _has_external_sources_in_current_turn,
        )

        messages = [
            HumanMessage(content="search web"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA web>>>\nold data\n<<<END>>>",
                name="web_search",
                tool_call_id="tc0",
            ),
            AIMessage(content="previous answer"),
            HumanMessage(content="now calculate 2+2"),
            ToolMessage(content="4", name="calculator", tool_call_id="tc1"),
        ]
        assert _has_external_sources_in_current_turn(messages) is False

    def test_has_external_sources_no_human_message(self) -> None:
        from langchain_core.messages import ToolMessage

        from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
            _has_external_sources_in_current_turn,
        )

        messages = [
            ToolMessage(
                content="<<<UNTRUSTED_DATA>>>data<<<END>>>",
                name="web_search",
                tool_call_id="tc1",
            ),
        ]
        assert _has_external_sources_in_current_turn(messages) is False


class TestCitationRulesContent:
    """Tests for citation rules prompt content."""

    def test_citation_rules_returned_when_needed(self) -> None:
        from app.ai_agents.prompts.general_agent_prompt import (
            get_citation_rules_if_needed,
        )

        result = get_citation_rules_if_needed(has_external_sources=True)
        assert result is not None
        assert "citation_rules" in result
        assert "【数字】" in result

    def test_citation_rules_none_when_not_needed(self) -> None:
        from app.ai_agents.prompts.general_agent_prompt import (
            get_citation_rules_if_needed,
        )

        result = get_citation_rules_if_needed(has_external_sources=False)
        assert result is None

    def test_citation_rules_contain_sourcing_rules(self) -> None:
        from app.ai_agents.prompts.general_agent_prompt import (
            get_citation_rules_if_needed,
        )

        result = get_citation_rules_if_needed(has_external_sources=True)
        assert result is not None
        assert "sourcing_rules" in result

    def test_citation_rules_contain_time_awareness(self) -> None:
        from app.ai_agents.prompts.general_agent_prompt import (
            get_citation_rules_if_needed,
        )

        result = get_citation_rules_if_needed(has_external_sources=True)
        assert result is not None
        assert "time_awareness" in result
