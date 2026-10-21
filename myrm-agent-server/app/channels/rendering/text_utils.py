"""Universal text processing utilities for channel formatting.

[INPUT]
- agent.streaming.reasoning_scrubber::THINKING_TAG_NAMES (POS: canonical thinking tag name set)

[OUTPUT]
- extract_safe_regions(): Extract pattern matches outside code blocks
- strip_thinking_tags(): Remove LLM thinking/reasoning tags from text
- strip_orphan_citations(): Remove orphan citation markers when sources absent
- downgrade_format(): Apply LaTeX/table/HTML downgrades based on RenderStyle
- md_to_plaintext(): Convert markdown to plain text based on RenderStyle

[POS]
Universal text utilities. Provides code-block-aware text processing,
format downgrade functions (LaTeX stripping, table conversion, HTML fence
replacement, plaintext conversion), and thinking tag removal for all
channel implementations.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from myrm_agent_harness.core.events import THINKING_TAG_NAMES

if TYPE_CHECKING:
    from re import Match

    from ..types import RenderStyle

_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BLOCKQUOTE_RE = re.compile(r"^>\s?", re.MULTILINE)

_CJK_CITATION_RE = re.compile(r"【\d+】")
_BARE_CITATION_RE = re.compile(r"(?<!\])\[(\d+)\](?!\()")

_HTML_FENCE_RE = re.compile(r"```(?:html|svg)\s*\n[\s\S]*?```", re.IGNORECASE)

_LATEX_BLOCK_RE = re.compile(r"\$\$\s*\n(.*?)\n\s*\$\$", re.DOTALL)
_LATEX_INLINE_RE = re.compile(r"\$\$(.+?)\$\$")
_LATEX_BRACKET_BLOCK_RE = re.compile(r"\\\[(.*?)\\\]", re.DOTALL)
_LATEX_PAREN_INLINE_RE = re.compile(r"\\\((.+?)\\\)")

_TABLE_RE = re.compile(
    r"^(\|[^\n]+\|)\n(\|[\s:|-]+\|)\n((?:\|[^\n]+\|\n?)+)",
    re.MULTILINE,
)

_THINK_TAGS = "|".join(THINKING_TAG_NAMES)
_THINK_PAIRED_RE = re.compile(
    rf"<({_THINK_TAGS})>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_THINK_ORPHAN_RE = re.compile(
    rf"</?(?:{_THINK_TAGS})>\s*",
    re.IGNORECASE,
)


def extract_safe_regions(
    text: str,
    pattern: str | re.Pattern[str],
    *,
    exclude_fenced_code: bool = True,
    exclude_inline_code: bool = True,
) -> list[Match[str]]:
    """Extract pattern matches from text, EXCLUDING code blocks.

    Useful for processing mentions, links, or other patterns while
    preserving code blocks intact (e.g., @user in code should NOT
    trigger mention conversion).

    Args:
        text: Input text to search
        pattern: Regex pattern (str or compiled Pattern)
        exclude_fenced_code: If True, exclude matches inside ```code```
        exclude_inline_code: If True, exclude matches inside `code`

    Returns:
        List of Match objects for matches OUTSIDE code blocks

    Example:
        >>> text = "Hi @alice, check ```@bob in code```"
        >>> matches = extract_safe_regions(text, r"@(\\w+)")
        >>> [m.group() for m in matches]
        ['@alice']  # @bob is excluded (inside code fence)
    """
    if isinstance(pattern, str):
        pattern = re.compile(pattern)

    code_ranges: list[tuple[int, int]] = []

    if exclude_fenced_code:
        code_ranges.extend((m.start(), m.end()) for m in _FENCED_CODE_RE.finditer(text))

    if exclude_inline_code:
        code_ranges.extend((m.start(), m.end()) for m in _INLINE_CODE_RE.finditer(text))

    code_ranges.sort()

    all_matches = list(pattern.finditer(text))

    def _is_inside_code(start: int, end: int) -> bool:
        """Check if range overlaps with any code block."""
        for code_start, code_end in code_ranges:
            if code_start <= start < code_end or code_start < end <= code_end:
                return True
            if start <= code_start < end:
                return True
        return False

    safe_matches = [m for m in all_matches if not _is_inside_code(m.start(), m.end())]

    return safe_matches


# ---------------------------------------------------------------------------
# Format downgrade utilities (moved from renderer.py for line-budget)
# ---------------------------------------------------------------------------

_CODE_BLOCK_PLACEHOLDER = "\x00CODEBLOCK_{}\x00"


def strip_thinking_tags(text: str) -> str:
    """Remove LLM thinking/reasoning tags and their content from text.

    Handles both paired blocks (``<think>…</think>``) and orphaned tags
    (``</think>``, ``<reasoning>``).  Pure function, safe for any channel.
    """
    if not text:
        return text
    result = _THINK_PAIRED_RE.sub("", text)
    result = _THINK_ORPHAN_RE.sub("", result)
    return result.strip()


def strip_orphan_citations(text: str) -> str:
    """Remove orphan citation markers (【N】 and [N]) when no sources are available."""
    if not text:
        return text
    result = _CJK_CITATION_RE.sub("", text)
    result = _BARE_CITATION_RE.sub("", result)
    return result


def with_protected_code_blocks(
    text: str,
    transform: Callable[[str], str],
) -> str:
    """Protect code blocks from transform, then restore them afterward."""
    blocks: list[str] = []

    def _save(m: re.Match[str]) -> str:
        blocks.append(m.group(0))
        return _CODE_BLOCK_PLACEHOLDER.format(len(blocks) - 1)

    protected = _CODE_FENCE_RE.sub(_save, text)
    transformed = transform(protected)
    for i, block in enumerate(blocks):
        transformed = transformed.replace(
            _CODE_BLOCK_PLACEHOLDER.format(i),
            block,
        )
    return transformed


def downgrade_html_fences(text: str, style: RenderStyle) -> str:
    """Replace HTML/SVG code fences with a short placeholder for IM channels."""
    if style.format == "markdown" and style.supports_code_fence:
        return text
    placeholder = (
        "\U0001f4ca [Interactive widget \u2014 view in app]" if style.use_emoji else "[Interactive widget \u2014 view in app]"
    )
    return _HTML_FENCE_RE.sub(placeholder, text)


def downgrade_content(text: str, style: RenderStyle) -> str:
    """Apply latex stripping and table downgrade on non-code-block text."""
    result = text
    if not style.supports_latex:
        result = _strip_latex(result)
    if not style.supports_tables:
        result = _downgrade_tables(result, style)
    return result


def _strip_latex(text: str) -> str:
    """Remove LaTeX delimiters ($$, \\[, \\(), keeping formula body as text."""
    result = _LATEX_BLOCK_RE.sub(r"\1", text)
    result = _LATEX_INLINE_RE.sub(r"\1", result)
    result = _LATEX_BRACKET_BLOCK_RE.sub(r"\1", result)
    result = _LATEX_PAREN_INLINE_RE.sub(r"\1", result)
    return result


def _downgrade_tables(text: str, style: RenderStyle) -> str:
    """Convert Markdown tables to a readable alternative for IM platforms."""

    def _table_to_replacement(m: re.Match[str]) -> str:
        header_line = m.group(1)
        data_block = m.group(3)
        headers = [c.strip() for c in header_line.strip("|").split("|")]
        rows_text = [r for r in data_block.strip().splitlines() if r.strip()]

        if style.supports_code_fence:
            original = f"{m.group(1)}\n{m.group(2)}\n{m.group(3).rstrip()}"
            return f"```\n{original}\n```"

        lines: list[str] = []
        for row_text in rows_text:
            cells = [c.strip() for c in row_text.strip("|").split("|")]
            parts = [f"{h}: {c}" for h, c in zip(headers, cells, strict=False) if c]
            lines.append("• " + " | ".join(parts))
        return "\n".join(lines)

    return _TABLE_RE.sub(_table_to_replacement, text)


def md_to_plaintext(text: str, style: RenderStyle) -> str:
    """Convert markdown to plain text, stripping formatting based on style."""
    result = text
    if not style.supports_code_fence:
        result = _CODE_FENCE_RE.sub(lambda m: m.group(0).strip("`").strip(), result)
    result = _BOLD_RE.sub(r"\1", result)
    result = _STRIKE_RE.sub(r"\1", result)
    result = _BLOCKQUOTE_RE.sub(" ", result)
    if not style.supports_links:
        result = _LINK_RE.sub(r"\1", result)
    return result
