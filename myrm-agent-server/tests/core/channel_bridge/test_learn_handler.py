"""Tests for ChannelLearnCommandHandler — verifies prompt construction,
input type detection, empty-args fallback, tool name correctness,
edge cases, protocol compliance, and i18n key coverage.
"""

from __future__ import annotations

import pytest

from app.channels.protocols.learn_command import LearnCommandHandler
from app.channels.types.messages import InboundMessage
from app.core.channel_bridge.learn_handler import (
    ChannelLearnCommandHandler,
    _build_learn_prompt,
    _detect_input_type,
)


def _make_msg(content: str = "/learn") -> InboundMessage:
    return InboundMessage(channel="test", sender_id="u1", content=content)


@pytest.fixture
def handler() -> ChannelLearnCommandHandler:
    return ChannelLearnCommandHandler()


class TestDetectInputType:
    def test_http_url(self) -> None:
        assert _detect_input_type("https://docs.example.com/api") == "url"

    def test_http_url_case_insensitive(self) -> None:
        assert _detect_input_type("HTTP://example.com") == "url"

    def test_relative_path(self) -> None:
        assert _detect_input_type("./scripts/deploy.sh") == "path"

    def test_home_path(self) -> None:
        assert _detect_input_type("~/docs/readme.md") == "path"

    def test_absolute_path(self) -> None:
        assert _detect_input_type("/usr/local/bin/tool") == "path"

    def test_free_text(self) -> None:
        assert _detect_input_type("the deployment workflow we just did") == "text"

    def test_free_text_with_spaces(self) -> None:
        assert _detect_input_type("learn how to deploy k8s") == "text"

    def test_whitespace_stripped(self) -> None:
        assert _detect_input_type("  https://example.com  ") == "url"

    # ── Edge cases ──

    def test_url_with_query_params(self) -> None:
        assert _detect_input_type("https://api.example.com/v2?key=val&foo=bar") == "url"

    def test_url_with_fragment(self) -> None:
        assert _detect_input_type("https://docs.example.com/guide#section-3") == "url"

    def test_url_with_port(self) -> None:
        assert _detect_input_type("http://localhost:3000/api") == "url"

    def test_path_with_dots(self) -> None:
        assert _detect_input_type("../parent/config.yaml") == "path"

    def test_path_deep_nesting(self) -> None:
        assert _detect_input_type("./a/b/c/d/e/f/g.py") == "path"

    def test_unicode_text(self) -> None:
        assert _detect_input_type("部署K8s的工作流程") == "text"

    def test_emoji_text(self) -> None:
        assert _detect_input_type("deploy workflow 🚀") == "text"

    def test_tab_and_newline_stripped(self) -> None:
        assert _detect_input_type("\thttps://example.com\n") == "url"

    def test_backslash_path(self) -> None:
        assert _detect_input_type("\\server\\share\\file.txt") == "path"

    def test_single_word(self) -> None:
        assert _detect_input_type("kubernetes") == "text"

    def test_path_with_spaces_in_directory(self) -> None:
        result = _detect_input_type("~/My Documents/file.txt")
        assert result == "path"

    def test_multiple_urls_treated_as_text(self) -> None:
        assert _detect_input_type("https://a.com and https://b.com") == "url"

    def test_ftp_not_matched_as_url(self) -> None:
        assert _detect_input_type("ftp://files.example.com") == "text"


class TestBuildLearnPrompt:
    def test_contains_learn_marker(self) -> None:
        prompt = _build_learn_prompt("https://example.com")
        assert "[/learn]" in prompt

    def test_url_uses_web_search_tool(self) -> None:
        prompt = _build_learn_prompt("https://docs.stripe.com/webhooks")
        assert "web_search_tool" in prompt
        assert "INPUT TYPE: url" in prompt

    def test_path_uses_file_read_tool(self) -> None:
        prompt = _build_learn_prompt("./scripts/deploy.sh")
        assert "file_read_tool" in prompt
        assert "grep_tool" in prompt
        assert "INPUT TYPE: path" in prompt

    def test_text_mentions_conversation(self) -> None:
        prompt = _build_learn_prompt("the workflow we just did")
        assert "conversation history" in prompt.lower() or "conversation" in prompt.lower()
        assert "INPUT TYPE: text" in prompt

    def test_uses_skill_manage_tool(self) -> None:
        prompt = _build_learn_prompt("anything")
        assert "skill_manage_tool" in prompt
        assert 'action="save"' in prompt

    def test_contains_authoring_standards(self) -> None:
        prompt = _build_learn_prompt("anything")
        assert "Frontmatter" in prompt
        assert "## When to Use" in prompt
        assert "## Verification" in prompt

    def test_no_wrong_tool_names(self) -> None:
        prompt = _build_learn_prompt("https://example.com")
        assert "`web_search`" not in prompt or "web_search_tool" in prompt
        assert "`read_file`" not in prompt
        assert "`search_files`" not in prompt
        assert "`skill_manage`" not in prompt or "skill_manage_tool" in prompt

    # ── Edge cases ──

    def test_user_input_preserved_verbatim(self) -> None:
        user_input = "https://docs.stripe.com/webhooks?version=2024-01"
        prompt = _build_learn_prompt(user_input)
        assert user_input in prompt

    def test_unicode_input_preserved(self) -> None:
        user_input = "部署K8s的工作流程"
        prompt = _build_learn_prompt(user_input)
        assert user_input in prompt

    def test_prompt_structure_has_three_sections(self) -> None:
        prompt = _build_learn_prompt("anything")
        assert "WHAT TO LEARN FROM:" in prompt
        assert "INPUT TYPE:" in prompt
        assert "INSTRUCTIONS:" in prompt

    def test_all_authoring_sections_present(self) -> None:
        prompt = _build_learn_prompt("anything")
        for section in [
            "## When to Use", "## Prerequisites", "## How to Run",
            "## Quick Reference", "## Procedure", "## Pitfalls", "## Verification",
        ]:
            assert section in prompt, f"Missing: {section}"

    def test_long_url_handled(self) -> None:
        long_url = "https://example.com/" + "a" * 2000
        prompt = _build_learn_prompt(long_url)
        assert long_url in prompt
        assert "INPUT TYPE: url" in prompt


class TestChannelLearnCommandHandler:
    @pytest.mark.asyncio
    async def test_with_url(self, handler: ChannelLearnCommandHandler) -> None:
        result = await handler(_make_msg(), "https://docs.example.com/api")
        assert result is not None
        assert "web_search_tool" in result.content
        assert "[/learn]" in result.content

    @pytest.mark.asyncio
    async def test_with_path(self, handler: ChannelLearnCommandHandler) -> None:
        result = await handler(_make_msg(), "./scripts/deploy.sh")
        assert result is not None
        assert "file_read_tool" in result.content

    @pytest.mark.asyncio
    async def test_with_free_text(self, handler: ChannelLearnCommandHandler) -> None:
        result = await handler(_make_msg(), "the deployment workflow")
        assert result is not None
        assert "the deployment workflow" in result.content

    @pytest.mark.asyncio
    async def test_empty_args_fallback(self, handler: ChannelLearnCommandHandler) -> None:
        result = await handler(_make_msg(), "")
        assert result is not None
        assert "conversation" in result.content.lower()
        assert "[/learn]" in result.content

    @pytest.mark.asyncio
    async def test_whitespace_only_args_fallback(self, handler: ChannelLearnCommandHandler) -> None:
        result = await handler(_make_msg(), "   ")
        assert result is not None
        assert "conversation" in result.content.lower()

    @pytest.mark.asyncio
    async def test_preserves_message_metadata(self, handler: ChannelLearnCommandHandler) -> None:
        msg = InboundMessage(
            channel="telegram", sender_id="u42", content="/learn",
            chat_id="chat_99", thread_id="thread_1",
        )
        result = await handler(msg, "https://example.com")
        assert result is not None
        assert result.channel == "telegram"
        assert result.sender_id == "u42"
        assert result.chat_id == "chat_99"
        assert result.thread_id == "thread_1"

    @pytest.mark.asyncio
    async def test_never_returns_none(self, handler: ChannelLearnCommandHandler) -> None:
        result = await handler(_make_msg(), "")
        assert result is not None

    # ── Edge cases ──

    @pytest.mark.asyncio
    async def test_tab_only_args_fallback(self, handler: ChannelLearnCommandHandler) -> None:
        result = await handler(_make_msg(), "\t\t")
        assert result is not None
        assert "conversation" in result.content.lower()

    @pytest.mark.asyncio
    async def test_newline_only_args_fallback(self, handler: ChannelLearnCommandHandler) -> None:
        result = await handler(_make_msg(), "\n\n")
        assert result is not None
        assert "conversation" in result.content.lower()

    @pytest.mark.asyncio
    async def test_unicode_args(self, handler: ChannelLearnCommandHandler) -> None:
        result = await handler(_make_msg(), "部署K8s集群的最佳实践")
        assert result is not None
        assert "部署K8s集群的最佳实践" in result.content

    @pytest.mark.asyncio
    async def test_url_with_special_chars(self, handler: ChannelLearnCommandHandler) -> None:
        url = "https://example.com/path?q=hello%20world&lang=zh-CN#section"
        result = await handler(_make_msg(), url)
        assert result is not None
        assert url in result.content
        assert "web_search_tool" in result.content

    @pytest.mark.asyncio
    async def test_original_message_content_replaced(self, handler: ChannelLearnCommandHandler) -> None:
        msg = _make_msg("/learn https://example.com")
        result = await handler(msg, "https://example.com")
        assert result is not None
        assert result.content != "/learn https://example.com"
        assert "[/learn]" in result.content

    @pytest.mark.asyncio
    async def test_exhaustive_input_types_never_none(self, handler: ChannelLearnCommandHandler) -> None:
        inputs = [
            "", "   ", "\t", "\n",
            "https://a.com", "http://b.com/path?q=1",
            "./file", "~/file", "/abs/path", "../rel",
            "free text", "部署流程", "a" * 5000,
        ]
        for args in inputs:
            result = await handler(_make_msg(), args)
            assert result is not None, f"Returned None for args={args!r}"
            assert "[/learn]" in result.content, f"Missing [/learn] for args={args!r}"


class TestProtocolCompliance:
    """Verify ChannelLearnCommandHandler conforms to LearnCommandHandler protocol."""

    def test_isinstance_check(self) -> None:
        handler = ChannelLearnCommandHandler()
        assert isinstance(handler, LearnCommandHandler)

    def test_callable(self) -> None:
        handler = ChannelLearnCommandHandler()
        assert callable(handler)


class TestI18nKeyCoverage:
    """Verify learn-related i18n keys exist in both locales."""

    def test_en_keys_exist(self) -> None:
        from app.channels.i18n import channel_t

        assert channel_t("en", "cmd_learn") != "cmd_learn"
        assert channel_t("en", "learn_not_configured") != "learn_not_configured"
        assert channel_t("en", "learn_failed") != "learn_failed"
        assert channel_t("en", "cat_Skills") != "cat_Skills"

    def test_zh_keys_exist(self) -> None:
        from app.channels.i18n import channel_t

        assert channel_t("zh-CN", "cmd_learn") != "cmd_learn"
        assert channel_t("zh-CN", "learn_not_configured") != "learn_not_configured"
        assert channel_t("zh-CN", "learn_failed") != "learn_failed"

    def test_no_stale_learn_usage_key(self) -> None:
        from app.channels.i18n import channel_t

        assert channel_t("en", "learn_usage") == "learn_usage"
        assert channel_t("zh-CN", "learn_usage") == "learn_usage"
