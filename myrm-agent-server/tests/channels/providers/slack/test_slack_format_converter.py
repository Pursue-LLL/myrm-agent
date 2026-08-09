"""Tests for Slack format converter — Markdown to mrkdwn."""

from __future__ import annotations

from app.channels.providers.slack.format_converter import (
    _convert_markdown_link,
    _escape_slack_content,
    _escape_slack_segment,
    _fix_cjk_formatting_boundaries,
    _is_allowed_slack_token,
    md_to_slack_mrkdwn,
)


class TestIsAllowedSlackToken:
    """Test Slack angle-bracket token validation."""

    def test_user_mention(self) -> None:
        assert _is_allowed_slack_token("<@U123456>") is True

    def test_channel_reference(self) -> None:
        assert _is_allowed_slack_token("<#C123456>") is True

    def test_special_mentions(self) -> None:
        assert _is_allowed_slack_token("<!here>") is True
        assert _is_allowed_slack_token("<!channel>") is True
        assert _is_allowed_slack_token("<!everyone>") is True

    def test_http_links(self) -> None:
        assert _is_allowed_slack_token("<http://example.com>") is True
        assert _is_allowed_slack_token("<https://example.com>") is True

    def test_protocol_links(self) -> None:
        assert _is_allowed_slack_token("<mailto:user@example.com>") is True
        assert _is_allowed_slack_token("<tel:+1234567890>") is True
        assert _is_allowed_slack_token("<slack://channel?id=C123>") is True

    def test_invalid_tokens(self) -> None:
        assert _is_allowed_slack_token("<invalid>") is False
        assert _is_allowed_slack_token("<script>") is False
        assert _is_allowed_slack_token("not a token") is False


class TestEscapeSlackSegment:
    """Test basic Slack mrkdwn escaping."""

    def test_escape_ampersand(self) -> None:
        assert _escape_slack_segment("A & B") == "A &amp; B"

    def test_escape_angle_brackets(self) -> None:
        assert _escape_slack_segment("x < y > z") == "x &lt; y &gt; z"

    def test_escape_all_special_chars(self) -> None:
        assert _escape_slack_segment("A & <B> & C") == "A &amp; &lt;B&gt; &amp; C"

    def test_no_special_chars(self) -> None:
        assert _escape_slack_segment("plain text") == "plain text"


class TestEscapeSlackContent:
    """Test intelligent escaping with token protection."""

    def test_preserve_user_mention(self) -> None:
        text = "Hello <@U123456> world"
        assert _escape_slack_content(text) == "Hello <@U123456> world"

    def test_preserve_channel_reference(self) -> None:
        text = "Check <#C123456>"
        assert _escape_slack_content(text) == "Check <#C123456>"

    def test_preserve_http_link(self) -> None:
        text = "Visit <http://example.com>"
        assert _escape_slack_content(text) == "Visit <http://example.com>"

    def test_escape_non_allowed_tokens(self) -> None:
        text = "<script>alert</script>"
        assert _escape_slack_content(text) == "&lt;script&gt;alert&lt;/script&gt;"

    def test_escape_mixed_content(self) -> None:
        text = "Hello <@U123> & <script>bad</script>"
        result = _escape_slack_content(text)
        assert "<@U123>" in result
        assert "&amp;" in result
        assert "&lt;script&gt;" in result

    def test_preserve_multiple_allowed_tokens(self) -> None:
        text = "<@U123> mentioned <#C456> with link <http://example.com>"
        result = _escape_slack_content(text)
        assert result == text

    def test_no_special_chars_fast_path(self) -> None:
        text = "plain text without special chars"
        assert _escape_slack_content(text) == text

    def test_empty_string(self) -> None:
        assert _escape_slack_content("") == ""


class TestMarkdownLinkConversion:
    """Test Markdown link to Slack link conversion."""

    def test_basic_link(self) -> None:
        import re

        match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", "[click here](http://example.com)")
        assert match is not None
        result = _convert_markdown_link(match)
        assert result == "<http://example.com|click here>"

    def test_link_with_text_same_as_url(self) -> None:
        import re

        match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", "[http://example.com](http://example.com)")
        assert match is not None
        result = _convert_markdown_link(match)
        assert result == "[http://example.com](http://example.com)"

    def test_mailto_link(self) -> None:
        import re

        match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", "[Email me](mailto:user@example.com)")
        assert match is not None
        result = _convert_markdown_link(match)
        assert result == "<mailto:user@example.com|Email me>"

    def test_mailto_with_text_same_as_email(self) -> None:
        import re

        match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", "[user@example.com](mailto:user@example.com)")
        assert match is not None
        result = _convert_markdown_link(match)
        assert result == "[user@example.com](mailto:user@example.com)"

    def test_empty_url(self) -> None:
        import re

        match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", "[text]()")
        if match:
            result = _convert_markdown_link(match)
            assert result == "[text]()"


class TestMdToSlackMrkdwn:
    """Test complete Markdown to Slack mrkdwn conversion."""

    def test_bold_conversion(self) -> None:
        assert md_to_slack_mrkdwn("**bold text**") == "*bold text*"

    def test_strike_conversion(self) -> None:
        assert md_to_slack_mrkdwn("~~strikethrough~~") == "~strikethrough~"

    def test_link_conversion(self) -> None:
        result = md_to_slack_mrkdwn("[click here](http://example.com)")
        assert result == "<http://example.com|click here>"

    def test_preserve_mentions(self) -> None:
        result = md_to_slack_mrkdwn("Hello <@U123456>!")
        assert result == "Hello <@U123456>!"

    def test_escape_special_chars(self) -> None:
        result = md_to_slack_mrkdwn("A & B < C > D")
        assert result == "A &amp; B &lt; C &gt; D"

    def test_complex_mixed_content(self) -> None:
        text = "**Bold** <@U123> [link](http://example.com) & ~~strike~~ <#C456>"
        result = md_to_slack_mrkdwn(text)

        assert "*Bold*" in result
        assert "<@U123>" in result
        assert "<http://example.com|link>" in result
        assert "&amp;" in result
        assert "~strike~" in result
        assert "<#C456>" in result

    def test_code_blocks_preserved(self) -> None:
        text = "```python\nprint('hello')\n```"
        result = md_to_slack_mrkdwn(text)
        assert "```" in result
        assert "print" in result

    def test_inline_code_preserved(self) -> None:
        text = "Use `print()` function"
        result = md_to_slack_mrkdwn(text)
        assert "`print()`" in result

    def test_empty_string(self) -> None:
        assert md_to_slack_mrkdwn("") == ""

    def test_no_formatting(self) -> None:
        text = "plain text"
        assert md_to_slack_mrkdwn(text) == text

    def test_unicode_content(self) -> None:
        text = "你好 **世界** "
        zws = "\u200b"
        result = md_to_slack_mrkdwn(text)
        assert f"*{zws}世界{zws}*" in result
        assert "你好" in result
        assert "" in result

    def test_multiple_links(self) -> None:
        text = "[link1](http://a.com) and [link2](http://b.com)"
        result = md_to_slack_mrkdwn(text)
        assert "<http://a.com|link1>" in result
        assert "<http://b.com|link2>" in result

    def test_italic_conversion(self) -> None:
        text = "*italic text*"
        result = md_to_slack_mrkdwn(text)
        assert result == "_italic text_"

    def test_italic_not_bold(self) -> None:
        text = "This is *italic* not **bold**"
        result = md_to_slack_mrkdwn(text)
        assert "_italic_" in result
        assert "*bold*" in result

    def test_italic_with_special_chars(self) -> None:
        text = "*A & B*"
        result = md_to_slack_mrkdwn(text)
        assert "_A &amp; B_" in result

    def test_mixed_bold_italic_strike(self) -> None:
        text = "**bold** *italic* ~~strike~~"
        result = md_to_slack_mrkdwn(text)
        assert "*bold*" in result
        assert "_italic_" in result
        assert "~strike~" in result

    def test_nested_formatting(self) -> None:
        text = "**bold with ~~strike~~**"
        result = md_to_slack_mrkdwn(text)
        assert "*bold with ~strike~*" in result

    def test_escape_inside_bold(self) -> None:
        text = "**A & B**"
        result = md_to_slack_mrkdwn(text)
        assert "*A &amp; B*" in result


class TestCjkFormattingBoundaries:
    """Test CJK character boundary zero-width space insertion."""

    ZWS = "\u200b"

    def test_cjk_before_bold_marker(self) -> None:
        result = _fix_cjk_formatting_boundaries("中文*bold*继续")
        assert result == f"中文{self.ZWS}*bold*{self.ZWS}继续"

    def test_cjk_before_underscore_marker(self) -> None:
        result = _fix_cjk_formatting_boundaries("中文_italic_继续")
        assert result == f"中文{self.ZWS}_italic_{self.ZWS}继续"

    def test_cjk_before_tilde_marker(self) -> None:
        result = _fix_cjk_formatting_boundaries("中文~strike~继续")
        assert result == f"中文{self.ZWS}~strike~{self.ZWS}继续"

    def test_no_cjk_no_insertion(self) -> None:
        text = "hello *bold* world"
        assert _fix_cjk_formatting_boundaries(text) == text

    def test_empty_string(self) -> None:
        assert _fix_cjk_formatting_boundaries("") == ""

    def test_cjk_only_no_markers(self) -> None:
        text = "中文纯文本"
        assert _fix_cjk_formatting_boundaries(text) == text

    def test_markers_only_no_cjk(self) -> None:
        text = "*bold* _italic_ ~strike~"
        assert _fix_cjk_formatting_boundaries(text) == text

    def test_full_pipeline_cjk_bold(self) -> None:
        """End-to-end: Markdown bold adjacent to CJK chars."""
        result = md_to_slack_mrkdwn("中文**加粗**文本")
        assert self.ZWS in result
        assert f"*{self.ZWS}加粗{self.ZWS}*" in result

    def test_full_pipeline_cjk_italic(self) -> None:
        """End-to-end: Markdown italic adjacent to CJK chars."""
        result = md_to_slack_mrkdwn("这是*斜体*文字")
        assert self.ZWS in result
        assert f"_{self.ZWS}斜体{self.ZWS}_" in result

    def test_full_pipeline_cjk_strike(self) -> None:
        """End-to-end: Markdown strikethrough adjacent to CJK chars."""
        result = md_to_slack_mrkdwn("删除~~这段~~文字")
        assert self.ZWS in result
        assert f"~{self.ZWS}这段{self.ZWS}~" in result

    def test_full_pipeline_mixed_cjk_ascii(self) -> None:
        """CJK + ASCII mixed: only CJK boundaries get ZWS."""
        result = md_to_slack_mrkdwn("Hello **世界** world")
        assert self.ZWS in result
        assert f"*{self.ZWS}世界{self.ZWS}*" in result

    def test_hangul_bold(self) -> None:
        """Hangul syllables (U+AC00-D7AF) also need ZWS."""
        result = _fix_cjk_formatting_boundaries("한글*bold*텍스트")
        assert result == f"한글{self.ZWS}*bold*{self.ZWS}텍스트"

    def test_full_pipeline_hangul_bold(self) -> None:
        """End-to-end: Hangul + bold."""
        result = md_to_slack_mrkdwn("한글**굵게**문자")
        assert self.ZWS in result
        assert f"*{self.ZWS}굵게{self.ZWS}*" in result

    def test_cjk_in_code_fence_no_insertion(self) -> None:
        """CJK inside code fences should NOT get ZWS."""
        text = "```\n中文*加粗*文本\n```"
        result = md_to_slack_mrkdwn(text)
        assert self.ZWS not in result


class TestCodeFenceAwareEscape:
    """Test code fence aware escape functionality."""

    def test_code_fence_no_escape(self) -> None:
        text = """```
const html = "<div>test</div>";
const amp = "A & B";
```"""
        result = md_to_slack_mrkdwn(text)
        assert "<div>" in result
        assert "</div>" in result
        assert "A & B" in result
        assert "&lt;" not in result
        assert "&amp;" not in result

    def test_code_fence_with_language_tag(self) -> None:
        text = """```python
def test():
    x = "<tag>" & "value"
    return x
```"""
        result = md_to_slack_mrkdwn(text)
        assert "<tag>" in result
        assert "& " in result  # Space after & to avoid matching &amp;
        assert "&lt;" not in result
        assert "&amp;" not in result

    def test_escape_outside_code_fence(self) -> None:
        text = """Normal text with <tags> & special chars
```
Inside fence: <no escape>
```
More text with <tags> outside"""
        result = md_to_slack_mrkdwn(text)
        # Outside fence: escaped
        lines = result.split("\n")
        assert "&lt;tags&gt;" in lines[0]
        assert "&amp;" in lines[0]
        assert "&lt;tags&gt;" in lines[4]  # Line 4 is "More text..."
        # Inside fence: not escaped
        assert "<no escape>" in result

    def test_multiple_code_fences(self) -> None:
        text = """First: <escape>
```
fence1: <no escape>
```
Middle: <escape>
```
fence2: <no escape>
```
End: <escape>"""
        result = md_to_slack_mrkdwn(text)
        lines = result.split("\n")
        assert "&lt;escape&gt;" in lines[0]
        assert "<no escape>" in lines[2]
        assert "&lt;escape&gt;" in lines[4]
        assert "<no escape>" in lines[6]
        assert "&lt;escape&gt;" in lines[8]

    def test_code_fence_with_formatting(self) -> None:
        text = """**Bold** outside
```
**not bold inside** but <preserved>
```
*Italic* outside"""
        result = md_to_slack_mrkdwn(text)
        assert "*Bold*" in result  # Bold converted outside
        assert "_Italic_" in result  # Italic converted outside
        assert "<preserved>" in result  # No escape inside fence
        # Inside fence: ** and * preserved as-is (no conversion)
        lines = result.split("\n")
        assert "**not bold inside** but <preserved>" in lines[2]

    def test_empty_code_fence(self) -> None:
        text = """```
```"""
        result = md_to_slack_mrkdwn(text)
        assert result == "```\n```"

    def test_inline_code_not_affected(self) -> None:
        text = "Use `<tag>` in code and <tag> outside"
        result = md_to_slack_mrkdwn(text)
        # Inline code (single backtick) is not affected by fence-aware escape
        # Both should be escaped as they're not in triple-backtick fences
        assert "&lt;tag&gt;" in result
