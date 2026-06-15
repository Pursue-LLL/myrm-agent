"""Tests for rendering/renderer.py — render pipeline, format downgrade, LaTeX/table handling."""

from __future__ import annotations

from app.channels.rendering.renderer import render, strip_thinking_tags
from app.channels.types import (
    OutboundMessage,
    ReasoningDisplay,
    RenderStyle,
    ToolStep,
    ToolSummaryDisplay,
)


def _style(**overrides: object) -> RenderStyle:
    defaults: dict[str, object] = {
        "format": "markdown",
        "max_text_length": 4096,
        "supports_links": True,
        "supports_code_fence": True,
        "supports_latex": True,
        "supports_tables": True,
        "use_emoji": True,
        "reasoning_display": ReasoningDisplay.OFF,
        "tool_summary_display": ToolSummaryDisplay.OFF,
    }
    defaults.update(overrides)
    return RenderStyle(**defaults)  # type: ignore[arg-type]


def _msg(**overrides: object) -> OutboundMessage:
    defaults: dict[str, object] = {
        "channel": "test",
        "recipient_id": "user1",
        "content": "Hello world",
        "user_id": "U1",
    }
    defaults.update(overrides)
    return OutboundMessage(**defaults)  # type: ignore[arg-type]


class TestRenderBasic:
    def test_simple_text(self) -> None:
        result = render(_msg(), _style())
        assert result == ["Hello world"]

    def test_empty_content_fallback(self) -> None:
        result = render(_msg(content=""), _style())
        assert result == ["Done."]

    def test_whitespace_content_fallback(self) -> None:
        result = render(_msg(content="   "), _style())
        assert result == ["Done."]

    def test_app_name_prefix(self) -> None:
        result = render(_msg(), _style(app_name_prefix="[Bot]"))
        assert result[0].startswith("[Bot]")


class TestReasoningBlock:
    def test_reasoning_off(self) -> None:
        result = render(
            _msg(reasoning="I think..."),
            _style(reasoning_display=ReasoningDisplay.OFF),
        )
        assert "think" not in result[0].lower()

    def test_reasoning_inline(self) -> None:
        result = render(
            _msg(reasoning="I think about this"),
            _style(reasoning_display=ReasoningDisplay.INLINE),
        )
        assert "Thinking" in result[0]
        assert "I think about this" in result[0]

    def test_reasoning_collapsed_markdown(self) -> None:
        result = render(
            _msg(reasoning="Deep thought"),
            _style(reasoning_display=ReasoningDisplay.COLLAPSED, supports_latex=True),
        )
        assert "> " in result[0]
        assert "Thinking" in result[0]
        assert "Deep thought" in result[0]

    def test_reasoning_collapsed_html(self) -> None:
        result = render(
            _msg(reasoning="Deep thought"),
            _style(reasoning_display=ReasoningDisplay.COLLAPSED, supports_latex=False),
        )
        assert "<blockquote expandable>" in result[0]
        assert "Deep thought" in result[0]

    def test_reasoning_truncated(self) -> None:
        long_reasoning = "x" * 3000
        result = render(
            _msg(reasoning=long_reasoning),
            _style(reasoning_display=ReasoningDisplay.INLINE),
        )
        full_text = "".join(result)
        assert "…" in full_text


class TestToolSummary:
    def test_tool_summary_off(self) -> None:
        steps = (ToolStep(name="search_tool", label="search", detail="query"),)
        result = render(_msg(tool_steps=steps), _style(tool_summary_display=ToolSummaryDisplay.OFF))
        assert "search" not in result[0]

    def test_tool_summary_compact(self) -> None:
        steps = (ToolStep(name="s", label="search"), ToolStep(name="r", label="read"))
        result = render(
            _msg(tool_steps=steps),
            _style(tool_summary_display=ToolSummaryDisplay.COMPACT),
        )
        full = "".join(result)
        assert "search" in full
        assert "→" in full

    def test_tool_summary_detailed(self) -> None:
        steps = (ToolStep(name="search_tool", label="search", detail="web query"),)
        result = render(
            _msg(tool_steps=steps),
            _style(tool_summary_display=ToolSummaryDisplay.DETAILED),
        )
        full = "".join(result)
        assert "search: web query" in full


class TestFormatDowngrade:
    def test_latex_stripped(self) -> None:
        result = render(
            _msg(content="Formula: $$E=mc^2$$"),
            _style(supports_latex=False),
        )
        assert "$$" not in result[0]
        assert "E=mc^2" in result[0]

    def test_latex_bracket_stripped(self) -> None:
        result = render(
            _msg(content=r"Block: \[x^2\]"),
            _style(supports_latex=False),
        )
        assert r"\[" not in result[0]

    def test_latex_paren_stripped(self) -> None:
        result = render(
            _msg(content=r"Inline: \(x+1\)"),
            _style(supports_latex=False),
        )
        assert r"\(" not in result[0]

    def test_table_downgrade_to_code(self) -> None:
        table = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        result = render(
            _msg(content=table),
            _style(supports_tables=False, supports_code_fence=True),
        )
        full = "".join(result)
        assert "```" in full

    def test_table_downgrade_to_list(self) -> None:
        table = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        result = render(
            _msg(content=table),
            _style(supports_tables=False, supports_code_fence=False),
        )
        full = "".join(result)
        assert "•" in full


class TestPlaintext:
    def test_bold_stripped(self) -> None:
        result = render(_msg(content="**bold** text"), _style(format="plaintext"))
        assert result[0] == "bold text"

    def test_strikethrough_stripped(self) -> None:
        result = render(_msg(content="~~strike~~ text"), _style(format="plaintext"))
        assert result[0] == "strike text"

    def test_links_stripped_when_unsupported(self) -> None:
        result = render(
            _msg(content="[click](http://example.com)"),
            _style(format="plaintext", supports_links=False),
        )
        assert "click" in result[0]
        assert "http" not in result[0]


class TestMrkdwn:
    def test_bold_converted(self) -> None:
        result = render(_msg(content="**bold** text"), _style(format="mrkdwn"))
        assert "*bold*" in result[0]

    def test_strikethrough_converted(self) -> None:
        result = render(_msg(content="~~strike~~ text"), _style(format="mrkdwn"))
        assert "~strike~" in result[0]


class TestSourcesBlock:
    def test_sources_with_links(self) -> None:
        metadata = {"sources": [{"url": "http://example.com", "title": "Example"}]}
        result = render(
            _msg(metadata=metadata),
            _style(supports_links=True),
        )
        full = "".join(result)
        assert "Sources" in full
        assert "[Example]" in full

    def test_sources_without_links(self) -> None:
        metadata = {"sources": [{"url": "http://example.com", "title": "Example"}]}
        result = render(
            _msg(metadata=metadata),
            _style(supports_links=False, format="plaintext"),
        )
        full = "".join(result)
        assert "http://example.com" in full

    def test_no_sources(self) -> None:
        result = render(_msg(metadata={}), _style())
        full = "".join(result)
        assert "Sources" not in full


class TestStripThinkingTags:
    """Tests for strip_thinking_tags — removes LLM reasoning tags from content."""

    def test_empty_string(self) -> None:
        assert strip_thinking_tags("") == ""

    def test_none_passthrough(self) -> None:
        assert strip_thinking_tags("") == ""

    def test_no_tags(self) -> None:
        assert strip_thinking_tags("Hello world") == "Hello world"

    def test_paired_think_block(self) -> None:
        text = "Before<think>internal reasoning</think>After"
        assert strip_thinking_tags(text) == "BeforeAfter"

    def test_paired_thinking_block(self) -> None:
        text = "A<thinking>deep thought</thinking>B"
        assert strip_thinking_tags(text) == "AB"

    def test_paired_reasoning_block(self) -> None:
        text = "Start<reasoning>step-by-step</reasoning>End"
        assert strip_thinking_tags(text) == "StartEnd"

    def test_paired_scratchpad_block(self) -> None:
        text = "X<REASONING_SCRATCHPAD>notes</REASONING_SCRATCHPAD>Y"
        assert strip_thinking_tags(text) == "XY"

    def test_multiline_thinking(self) -> None:
        text = "Answer:\n<think>\nLine 1\nLine 2\n</think>\nVisible content"
        assert strip_thinking_tags(text) == "Answer:\n\nVisible content"

    def test_orphan_closing_tag(self) -> None:
        text = "Some content</think>\nMore text"
        result = strip_thinking_tags(text)
        assert "</think>" not in result
        assert "Some content" in result
        assert "More text" in result

    def test_orphan_opening_tag(self) -> None:
        text = "Start<thinking>\nTrailing content"
        result = strip_thinking_tags(text)
        assert "<thinking>" not in result
        assert "Trailing content" in result

    def test_case_insensitive(self) -> None:
        text = "A<THINK>hidden</THINK>B"
        assert strip_thinking_tags(text) == "AB"

    def test_mixed_case(self) -> None:
        text = "A<Thinking>hidden</Thinking>B"
        assert strip_thinking_tags(text) == "AB"

    def test_paired_thought_block(self) -> None:
        text = "A<thought>hmm</thought>B"
        assert strip_thinking_tags(text) == "AB"

    def test_paired_antthinking_block(self) -> None:
        text = "A<antthinking>internal</antthinking>B"
        assert strip_thinking_tags(text) == "AB"

    def test_multiple_blocks(self) -> None:
        text = "<think>a</think>Real<reasoning>b</reasoning>Content"
        assert strip_thinking_tags(text) == "RealContent"

    def test_integration_via_render(self) -> None:
        """Verify strip_thinking_tags is applied during rendering."""
        msg = _msg(content="Answer<think>internal</think> is 42")
        result = render(msg, _style())
        full = "".join(result)
        assert "internal" not in full
        assert "42" in full
        assert "<think>" not in full

    def test_integration_orphan_via_render(self) -> None:
        """Verify orphaned tags cleaned during rendering."""
        msg = _msg(content="Result</think> is done")
        result = render(msg, _style())
        full = "".join(result)
        assert "</think>" not in full
        assert "done" in full
