"""Tests for channels/renderer: unified message rendering pipeline."""

import app.channels.providers.slack  # noqa: F401  # registers mrkdwn converter
from app.channels.rendering.renderer import render
from app.channels.types import OutboundMessage, RenderStyle


def _msg(content: str = "Hello **world**", metadata: dict | None = None) -> OutboundMessage:
    return OutboundMessage(channel="test", recipient_id="u1", content=content, user_id="u1", metadata=metadata)


class TestMarkdownFormat:
    def test_passthrough(self):
        style = RenderStyle(format="markdown", max_text_length=4096)
        result = render(_msg(), style)
        assert len(result) == 1
        assert "**world**" in result[0]

    def test_empty_fallback(self):
        style = RenderStyle(format="markdown", max_text_length=4096)
        result = render(_msg(content=""), style)
        assert result == ["Done."]


class TestPlaintextFormat:
    def test_strips_bold(self):
        style = RenderStyle(format="plaintext", max_text_length=4096)
        result = render(_msg(), style)
        assert "**" not in result[0]
        assert "world" in result[0]

    def test_strips_links_when_unsupported(self):
        style = RenderStyle(format="plaintext", supports_links=False, max_text_length=4096)
        msg = _msg(content="Check [this](https://example.com)")
        result = render(msg, style)
        assert "https://" not in result[0]
        assert "this" in result[0]

    def test_app_name_prefix(self):
        style = RenderStyle(format="plaintext", app_name_prefix="[Bot]", max_text_length=4096)
        result = render(_msg(), style)
        assert result[0].startswith("[Bot]")


class TestMrkdwnFormat:
    def test_converts_bold(self):
        style = RenderStyle(format="mrkdwn", max_text_length=4096)
        result = render(_msg(), style)
        assert "*world*" in result[0]
        assert "**" not in result[0]

    def test_converts_strike(self):
        style = RenderStyle(format="mrkdwn", max_text_length=4096)
        msg = _msg(content="~~deleted~~")
        result = render(msg, style)
        assert "~deleted~" in result[0]
        assert "~~" not in result[0]


class TestCronContext:
    def test_cron_header_markdown(self):
        style = RenderStyle(format="markdown", max_text_length=4096)
        msg = _msg(content="Report data", metadata={"job_name": "Daily Report", "success": True})
        result = render(msg, style)
        assert "" in result[0]
        assert "*" in result[0]  # markdown bold

    def test_cron_header_plaintext(self):
        style = RenderStyle(format="plaintext", max_text_length=4096)
        msg = _msg(content="Error", metadata={"job_name": "Backup", "success": False})
        result = render(msg, style)
        assert "" in result[0]
        assert "Backup" in result[0]


class TestSources:
    def test_markdown_links(self):
        style = RenderStyle(format="markdown", max_text_length=4096)
        msg = _msg(
            content="Here are results",
            metadata={"sources": [{"title": "Wikipedia", "url": "https://en.wikipedia.org"}]},
        )
        result = render(msg, style)
        assert "[Wikipedia](https://en.wikipedia.org)" in result[0]

    def test_plaintext_sources(self):
        style = RenderStyle(format="plaintext", supports_links=False, max_text_length=4096)
        msg = _msg(
            content="Results",
            metadata={"sources": [{"title": "Wiki", "url": "https://wiki.org"}]},
        )
        result = render(msg, style)
        assert "[1] Wiki: https://wiki.org" in result[0]


class TestAllChannelStyles:
    """Integration test: verify render() works with every real channel's RenderStyle."""

    _RICH_MSG = _msg(
        content="Here's a **bold** result with ~~strike~~.\n\n```python\nprint('hello')\n```\n\nSee [docs](https://docs.example.com).",
        metadata={
            "sources": [{"title": "Doc", "url": "https://docs.example.com"}],
            "job_name": "Nightly Report",
            "success": True,
        },
    )

    _CHANNEL_STYLES: list[tuple[str, RenderStyle]] = [
        ("telegram", RenderStyle(format="markdown", max_text_length=4096)),
        (
            "whatsapp",
            RenderStyle(
                format="plaintext",
                max_text_length=65536,
                supports_code_fence=False,
                supports_links=False,
                app_name_prefix="[Myrm AI]",
            ),
        ),
        ("slack", RenderStyle(format="mrkdwn", max_text_length=40000)),
        ("discord", RenderStyle(format="markdown", max_text_length=2000)),
        ("dingtalk", RenderStyle(format="markdown", max_text_length=20000)),
        ("wecom", RenderStyle(format="markdown", max_text_length=2048)),
        ("teams", RenderStyle(format="markdown", max_text_length=28000)),
        ("matrix", RenderStyle(format="markdown", max_text_length=65536)),
        ("googlechat", RenderStyle(format="plaintext", max_text_length=4096)),
        ("feishu", RenderStyle(format="markdown", max_text_length=30000)),
    ]

    def test_all_channels_produce_nonempty_output(self):
        for name, style in self._CHANNEL_STYLES:
            result = render(self._RICH_MSG, style)
            assert result, f"{name}: render returned empty list"
            assert all(chunk for chunk in result), f"{name}: render returned empty chunk"

    def test_plaintext_channels_strip_markdown(self):
        for name, style in self._CHANNEL_STYLES:
            if style.format != "plaintext":
                continue
            result = render(self._RICH_MSG, style)
            combined = "".join(result)
            assert "**" not in combined, f"{name}: bold markers not stripped"
            assert "~~" not in combined, f"{name}: strike markers not stripped"

    def test_mrkdwn_channels_convert_bold(self):
        for name, style in self._CHANNEL_STYLES:
            if style.format != "mrkdwn":
                continue
            result = render(self._RICH_MSG, style)
            combined = "".join(result)
            assert "*bold*" in combined, f"{name}: bold not converted to mrkdwn"
            assert "**" not in combined, f"{name}: md bold still present"

    def test_whatsapp_prefix(self):
        whatsapp_style = self._CHANNEL_STYLES[1][1]
        result = render(_msg(content="Test"), whatsapp_style)
        assert result[0].startswith("[Myrm AI]"), "WhatsApp prefix missing"

    def test_no_chunk_exceeds_max_length(self):
        long_content = "Paragraph.\n\n" * 200
        for name, style in self._CHANNEL_STYLES:
            result = render(_msg(content=long_content), style)
            for i, chunk in enumerate(result):
                assert len(chunk) <= style.max_text_length, (
                    f"{name}: chunk {i} ({len(chunk)} chars) exceeds max {style.max_text_length}"
                )


class TestLatexStripping:
    _INLINE = "The formula $$E = mc^2$$ is famous."
    _BLOCK = "Result:\n\n$$\nx = \\frac{-b}{2a}\n$$\n\nDone."

    def test_inline_stripped_when_unsupported(self):
        style = RenderStyle(format="markdown", max_text_length=4096)
        result = render(_msg(content=self._INLINE), style)
        assert "$$" not in result[0]
        assert "E = mc^2" in result[0]

    def test_block_stripped_when_unsupported(self):
        style = RenderStyle(format="markdown", max_text_length=4096)
        result = render(_msg(content=self._BLOCK), style)
        assert "$$" not in result[0]
        assert "\\frac{-b}{2a}" in result[0]

    def test_preserved_when_supported(self):
        style = RenderStyle(format="markdown", max_text_length=4096, supports_latex=True)
        result = render(_msg(content=self._INLINE), style)
        assert "$$E = mc^2$$" in result[0]

    def test_bracket_block_stripped(self):
        content = "Result:\n\\[x = \\frac{1}{2}\\]\nEnd."
        style = RenderStyle(format="markdown", max_text_length=4096)
        result = render(_msg(content=content), style)
        assert "\\[" not in result[0]
        assert "\\frac{1}{2}" in result[0]

    def test_paren_inline_stripped(self):
        content = "The value \\(\\alpha + \\beta\\) is positive."
        style = RenderStyle(format="markdown", max_text_length=4096)
        result = render(_msg(content=content), style)
        assert "\\(" not in result[0]
        assert "\\alpha + \\beta" in result[0]

    def test_latex_inside_code_block_preserved(self):
        content = "Here is code:\n\n```python\nx = '$$E=mc^2$$'\n```\n\nAnd $$F=ma$$ outside."
        style = RenderStyle(format="markdown", max_text_length=4096)
        result = render(_msg(content=content), style)
        combined = result[0]
        assert "$$E=mc^2$$" in combined  # inside code block: preserved
        assert "F=ma" in combined  # outside: formula body kept
        assert combined.count("$$F=ma$$") == 0  # delimiters stripped outside


class TestTableDowngrade:
    _TABLE = "Results:\n\n| Name | Score |\n|------|-------|\n| Alice | 95 |\n| Bob | 87 |\n"

    def test_table_to_code_block_when_code_fence_supported(self):
        style = RenderStyle(format="markdown", max_text_length=4096, supports_code_fence=True)
        result = render(_msg(content=self._TABLE), style)
        combined = result[0]
        assert "```" in combined
        assert "Alice" in combined
        assert "Bob" in combined

    def test_table_to_bullet_list_when_no_code_fence(self):
        style = RenderStyle(
            format="plaintext",
            max_text_length=4096,
            supports_code_fence=False,
            supports_tables=False,
        )
        result = render(_msg(content=self._TABLE), style)
        combined = result[0]
        assert "```" not in combined
        assert "Name: Alice" in combined
        assert "Score: 87" in combined

    def test_table_preserved_when_supported(self):
        style = RenderStyle(format="markdown", max_text_length=4096, supports_tables=True)
        result = render(_msg(content=self._TABLE), style)
        combined = result[0]
        assert "|------|" in combined

    def test_table_inside_code_block_preserved(self):
        content = "Table example:\n\n```\n| A | B |\n|---|---|\n| 1 | 2 |\n```\n\nEnd."
        style = RenderStyle(format="markdown", max_text_length=4096)
        result = render(_msg(content=content), style)
        combined = result[0]
        assert "|---|" in combined

    def test_combined_latex_and_table_downgrade(self):
        content = "$$E=mc^2$$ 的推导：\n\n| Variable | Meaning |\n|----------|--------|\n| E | Energy |\n| m | Mass |\n"
        style = RenderStyle(format="markdown", max_text_length=4096)
        result = render(_msg(content=content), style)
        combined = result[0]
        assert "$$" not in combined
        assert "E=mc^2" in combined
        assert "```" in combined
        assert "Energy" in combined


class TestSplitting:
    def test_no_split_short(self):
        style = RenderStyle(max_text_length=100)
        result = render(_msg(content="Short"), style)
        assert len(result) == 1

    def test_splits_long_text_with_sources(self):
        style = RenderStyle(format="markdown", max_text_length=120)
        msg = _msg(
            content="A" * 100,
            metadata={
                "sources": [
                    {"title": "S1", "url": "https://a.com"},
                    {"title": "S2", "url": "https://b.com"},
                ],
            },
        )
        result = render(msg, style)
        combined = "".join(result)
        assert "S1" in combined


class TestHtmlFenceDowngrade:
    """HTML/SVG code fences should be replaced with a placeholder in IM channels."""

    _HTML_WIDGET = 'Here is a chart:\n\n```html\n<div id="chart"><canvas></canvas></div>\n<script>new Chart(ctx, config)</script>\n```\n\nDone.'
    _SVG_WIDGET = 'Diagram:\n\n```svg\n<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>\n```\n\nEnd.'

    def test_html_fence_replaced_in_plaintext(self):
        style = RenderStyle(format="plaintext", max_text_length=4096, supports_code_fence=False)
        result = render(_msg(content=self._HTML_WIDGET), style)
        combined = "".join(result)
        assert "```html" not in combined
        assert "<canvas>" not in combined
        assert "Interactive widget" in combined
        assert "Done" in combined

    def test_svg_fence_replaced_in_plaintext(self):
        style = RenderStyle(format="plaintext", max_text_length=4096, supports_code_fence=False)
        result = render(_msg(content=self._SVG_WIDGET), style)
        combined = "".join(result)
        assert "```svg" not in combined
        assert "<svg" not in combined
        assert "Interactive widget" in combined

    def test_html_fence_preserved_in_markdown_with_code_fence(self):
        style = RenderStyle(format="markdown", max_text_length=4096, supports_code_fence=True)
        result = render(_msg(content=self._HTML_WIDGET), style)
        combined = "".join(result)
        assert "```html" in combined
        assert "<canvas>" in combined

    def test_html_fence_replaced_in_mrkdwn(self):
        style = RenderStyle(format="mrkdwn", max_text_length=4096)
        result = render(_msg(content=self._HTML_WIDGET), style)
        combined = "".join(result)
        assert "Interactive widget" in combined
        assert "<canvas>" not in combined

    def test_emoji_in_placeholder(self):
        style = RenderStyle(format="plaintext", max_text_length=4096, use_emoji=True, supports_code_fence=False)
        result = render(_msg(content=self._HTML_WIDGET), style)
        combined = "".join(result)
        assert "Interactive widget" in combined

    def test_no_emoji_in_placeholder(self):
        style = RenderStyle(format="plaintext", max_text_length=4096, use_emoji=False, supports_code_fence=False)
        result = render(_msg(content=self._HTML_WIDGET), style)
        combined = "".join(result)
        assert "Interactive widget" in combined

    def test_non_html_code_fence_preserved(self):
        content = "Code:\n\n```python\nprint('hello')\n```\n\nEnd."
        style = RenderStyle(format="plaintext", max_text_length=4096, supports_code_fence=False)
        result = render(_msg(content=content), style)
        combined = "".join(result)
        assert "print('hello')" in combined

    def test_multiple_html_fences_replaced(self):
        content = "Chart 1:\n\n```html\n<div>A</div>\n```\n\nChart 2:\n\n```html\n<div>B</div>\n```\n\nDone."
        style = RenderStyle(format="plaintext", max_text_length=4096, supports_code_fence=False)
        result = render(_msg(content=content), style)
        combined = "".join(result)
        assert combined.count("Interactive widget") == 2
        assert "<div>" not in combined
