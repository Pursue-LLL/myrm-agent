"""The latest human request and whether this run holds external evidence for it."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
)


class TestExtractLatestHumanText:
    """Tests for extract_latest_human_text covering multimodal content."""

    def test_string_content(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            extract_latest_human_text,
        )

        messages = [HumanMessage(content="What is the latest news?")]
        assert extract_latest_human_text(messages) == "What is the latest news?"

    def test_strips_bound_skills_catalog(self) -> None:
        """System-injected <bound_skills> catalog must not leak into freshness detection."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            extract_latest_human_text,
        )

        messages = [
            HumanMessage(
                content=(
                    '<bound_skills hash="abc">\n<skills>\n<row><name>live search</name></row>\n'
                    "</skills>\n</bound_skills>\n\n只回复 OK"
                )
            )
        ]
        assert extract_latest_human_text(messages) == "只回复 OK"

    def test_strips_bound_skills_from_multimodal(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            extract_latest_human_text,
        )

        messages = [
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": (
                            '<bound_skills hash="abc">\n<skills>\n<row><name>live stats</name></row>\n'
                            "</skills>\n</bound_skills>\n\n只回复 OK"
                        ),
                    }
                ]
            )
        ]
        assert extract_latest_human_text(messages) == "只回复 OK"

    def test_multimodal_list_content(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            extract_latest_human_text,
        )

        messages = [
            HumanMessage(
                content=[
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "http://example.com/img.png"},
                    },
                ]
            )
        ]
        assert extract_latest_human_text(messages) == "Describe this image"

    def test_multimodal_list_multiple_text_parts(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            extract_latest_human_text,
        )

        messages = [
            HumanMessage(
                content=[
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "world"},
                ]
            )
        ]
        assert extract_latest_human_text(messages) == "Hello world"

    def test_empty_string_content_skipped(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            extract_latest_human_text,
        )

        messages = [
            HumanMessage(content="   "),
            HumanMessage(content="Actual question"),
        ]
        assert extract_latest_human_text(messages) == "Actual question"

    def test_empty_list_returns_none(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            extract_latest_human_text,
        )

        assert extract_latest_human_text([]) is None

    def test_no_human_messages(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            extract_latest_human_text,
        )

        messages = [AIMessage(content="I am AI")]
        assert extract_latest_human_text(messages) is None


class TestHasExternalEvidence:
    """Tests for has_external_evidence helper."""

    def test_returns_true_for_successful_evidence_tool(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="web_search_tool",
            args_hash="s1",
            args={"query": "test"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        assert has_external_evidence([record]) is True

    def test_returns_false_for_failed_evidence_tool(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="web_search_tool",
            args_hash="s1",
            args={"query": "test"},
            success_level=SuccessLevel.FAILURE,
        )
        assert has_external_evidence([record]) is False

    def test_returns_false_for_non_evidence_tool(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="file_read_tool",
            args_hash="r1",
            args={"path": "/tmp/x"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        assert has_external_evidence([record]) is False

    def test_returns_false_for_empty_records(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        assert has_external_evidence([]) is False

    def test_returns_true_for_successful_mcp_ptc_bash(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="bash_code_execute_tool",
            args_hash="mcp1",
            args={
                "command": ('python3 -c "from skills.mcp_12306_skill import get_tickets; print(\\"ok\\")"'),
            },
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        assert has_external_evidence([record]) is True

    def test_returns_false_for_failed_mcp_ptc_bash(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="bash_code_execute_tool",
            args_hash="mcp2",
            args={"command": "from skills.mcp_12306_skill import get_tickets"},
            success_level=SuccessLevel.FAILURE,
        )
        assert has_external_evidence([record]) is False

    def test_returns_false_for_plain_bash_without_mcp_marker(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="bash_code_execute_tool",
            args_hash="bash1",
            args={"command": "pytest -q"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        assert has_external_evidence([record]) is False

    def test_returns_false_when_bash_args_are_not_a_dict(self) -> None:
        """Bash args that are empty or lack command/code must not count as MCP PTC evidence."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        empty_args = CallRecord(
            tool_name="bash_code_execute_tool",
            args_hash="b0",
            args={},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        assert has_external_evidence([empty_args]) is False

        non_command_args = CallRecord(
            tool_name="bash_code_execute_tool",
            args_hash="b1",
            args={"timeout": 120},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        assert has_external_evidence([non_command_args]) is False

    def test_requires_evidence_for_citation_and_web_hint_combination(self) -> None:
        """A request with citation+web hints but no freshness word still requires evidence."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="Please summarize with sources from the web."),
            AIMessage(content="All done."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is not None
        assert "external/freshness need" in reason

    def test_no_evidence_required_without_freshness_or_citation_web_hint(self) -> None:
        """Plain questions must not require external evidence."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="Explain how merge sort works."),
            AIMessage(content="Merge sort is a divide-and-conquer algorithm."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is None

    def test_citation_alone_without_web_hint_requires_no_evidence(self) -> None:
        """A citation keyword alone (no web hint) must not trigger the gate."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="Which sources describe this algorithm?"),
            AIMessage(content="All done."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is None

    def test_no_evidence_required_for_internal_code_task_with_latest(self) -> None:
        """A local code task phrased with 'latest' must NOT require external
        evidence — the agent would otherwise be pushed into a meaningless web
        search for its own repository's recent changes."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="帮我分析一下项目里最新改动的代码逻辑"),
            AIMessage(content="All done."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is None

    def test_internal_code_task_english_variant_no_evidence(self) -> None:
        """English equivalent of an internal code task is also exempted."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="What are the latest code changes in the auth module?"),
            AIMessage(content="All done."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is None

    def test_evidence_still_required_for_genuine_freshness(self) -> None:
        """A real freshness request without local-work context still requires
        external evidence — the exemption must not weaken the anti-hallucination gate.
        """
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="今天最新的 AI 新闻是什么？"),
            AIMessage(content="All done."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is not None

    def test_internal_task_with_external_hint_still_requires_evidence(self) -> None:
        """An explicit external hint (links/search) suppresses the local-work
        exemption — the user clearly wants outside material."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="分析最新代码改动，并搜索网上的最佳实践"),
            AIMessage(content="All done."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is not None

    def test_no_evidence_required_for_local_test_result_zh(self) -> None:
        """A local test-result query phrased with 'latest' must NOT require external
        evidence — test runs live in the user's own repository, not on the web."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="帮我看看最新的测试结果"),
            AIMessage(content="All done."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is None

    def test_no_evidence_required_for_local_test_result_en(self) -> None:
        """English equivalent of a local test-result query is also exempted."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="What are the latest test results?"),
            AIMessage(content="All done."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is None

    def test_no_evidence_required_for_local_logs_and_scripts(self) -> None:
        """Local log/script queries are exempted — logs and scripts are workspace
        artifacts, not external material."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="最新日志和脚本的改动情况"),
            AIMessage(content="All done."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is None

    def test_evidence_still_required_for_external_price_query(self) -> None:
        """A genuine freshness query about market data must NOT be exempted —
        '金价/price' carries no local-work signal, so the anti-hallucination
        gate must keep forcing external evidence."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            build_external_evidence_reason,
        )

        messages = [
            HumanMessage(content="今天最新金价是多少"),
            AIMessage(content="All done."),
        ]
        reason = build_external_evidence_reason(messages=messages, records=[])
        assert reason is not None

    def test_returns_true_for_successful_mcp_direct_fc_tool(self) -> None:
        """A successful Direct FC MCP tool call (mcp__{server}__{tool}) is external evidence."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="mcp__12306__get_current_date",
            args_hash="d1",
            args={},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        assert has_external_evidence([record]) is True

    def test_returns_false_for_failed_mcp_direct_fc_tool(self) -> None:
        """A failed Direct FC MCP tool call must not count as external evidence."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="mcp__12306__get_current_date",
            args_hash="d1",
            args={},
            success_level=SuccessLevel.FAILURE,
        )
        assert has_external_evidence([record]) is False

    def test_returns_false_for_plain_tool_matching_mcp_prefix_only(self) -> None:
        """A non-MCP tool that merely starts with 'mcp' (no __delimiter) is not evidence."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="mcp_config_tool",
            args_hash="m1",
            args={},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
        assert has_external_evidence([record]) is False

    def test_returns_false_for_intercepted_mcp_direct_fc_tool(self) -> None:
        """An intercepted Direct FC MCP call (success_level=None) is NOT evidence —
        an unexecuted tool provides no external data."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="mcp__12306__query_tickets",
            args_hash="d1",
            args={},
            success_level=None,
        )
        assert has_external_evidence([record]) is False

    def test_returns_false_for_intercepted_mcp_ptc_bash(self) -> None:
        """An intercepted MCP PTC bash call (success_level=None) is NOT evidence."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="bash_code_execute_tool",
            args_hash="mcp1",
            args={"command": "from skills.mcp_12306_skill import get_tickets"},
            success_level=None,
        )
        assert has_external_evidence([record]) is False

    def test_returns_false_for_intercepted_builtin_evidence_tool(self) -> None:
        """An intercepted built-in evidence tool (success_level=None) is NOT evidence."""
        from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
            has_external_evidence,
        )

        record = CallRecord(
            tool_name="web_search_tool",
            args_hash="s1",
            args={"query": "today's news"},
            success_level=None,
        )
        assert has_external_evidence([record]) is False
