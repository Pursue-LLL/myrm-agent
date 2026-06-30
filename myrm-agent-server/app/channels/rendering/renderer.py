"""Unified message rendering pipeline.

Renders OutboundMessage into a list of sendable text chunks for channels.
Three-stage pipeline: _prepare → _format → split_message, all pure functions, 100% unit-testable.

Format layer performs format downgrade based on RenderStyle capability declarations:
- supports_latex=False  → LaTeX formulas ``$$…$$`` stripped to plain text
- supports_tables=False → Markdown tables downgraded to lists or code blocks

Sources block with numbered footnotes ([N]), corresponding to citation numbers in LLM body text.
When no sources are present, orphan citation markers in body text (【N】/[N]) are auto-cleaned.

[INPUT]
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.rendering.splitter::split_message (POS: smart long-message splitting)
- agent.streaming.reasoning_scrubber::THINKING_TAG_NAMES (POS: canonical thinking tag name set)

[OUTPUT]
- render(): OutboundMessage → list[str] (rendered text chunk list)
- strip_thinking_tags(): str → str (strip LLM thinking tags)

[POS]
Outbound message formatting pipeline. Converts structured OutboundMessage to platform-sendable
plain text/Markdown, performing format downgrade (LaTeX, tables, etc.) based on Channel's
RenderStyle capability declarations.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from myrm_agent_harness.core.events import THINKING_TAG_NAMES

from ..types import (
    OutboundMessage,
    ReasoningDisplay,
    RenderStyle,
    ToolStep,
    ToolSummaryDisplay,
    extract_cron_context,
)
from .converter_registry import FormatConverterRegistry
from .splitter import split_message

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BLOCKQUOTE_RE = re.compile(r"^>\s?", re.MULTILINE)
_EMPTY_FALLBACK = "Done."

# Orphan citation markers: 【N】 (CJK) and [N] (non-link) left by LLM when sources are absent
_CJK_CITATION_RE = re.compile(r"【\d+】")
_BARE_CITATION_RE = re.compile(r"(?<!\])\[(\d+)\](?!\()")

# HTML/SVG code fences — replaced with a short placeholder in IM channels
_HTML_FENCE_RE = re.compile(r"```(?:html|svg)\s*\n[\s\S]*?```", re.IGNORECASE)

# LaTeX: multiple delimiter styles
_LATEX_BLOCK_RE = re.compile(r"\$\$\s*\n(.*?)\n\s*\$\$", re.DOTALL)
_LATEX_INLINE_RE = re.compile(r"\$\$(.+?)\$\$")
_LATEX_BRACKET_BLOCK_RE = re.compile(r"\\\[(.*?)\\\]", re.DOTALL)
_LATEX_PAREN_INLINE_RE = re.compile(r"\\\((.+?)\\\)")

# Markdown table: header row + separator row + data rows
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


def _strip_orphan_citations(text: str) -> str:
    """Remove orphan citation markers (【N】 and [N]) when no sources are available."""
    if not text:
        return text
    result = _CJK_CITATION_RE.sub("", text)
    result = _BARE_CITATION_RE.sub("", result)
    return result


@dataclass(frozen=True, slots=True)
class _PreparedContent:
    """prepare 层output 结构化 in 间产物"""

    reasoning_block: str
    header: str
    body: str
    sources_block: str
    tool_summary_block: str
    cost_footer: str


def render(msg: OutboundMessage, style: RenderStyle) -> list[str]:
    """OutboundMessage → channel 可Send text块List

    纯Function， no  I/O。Channel provider 只需Call此FunctionGet chunks 并逐个Send。
    """
    prepared = _prepare(msg, style)
    text = _format(prepared, style)
    return split_message(text, style.max_text_length)


# ---------------------------------------------------------------------------
# Layer 1: Prepare — Extract结构化Content（All channel 共享）
# ---------------------------------------------------------------------------


def _prepare(msg: OutboundMessage, style: RenderStyle) -> _PreparedContent:
    header = ""
    cron = extract_cron_context(msg)
    if cron:
        icon = ("\u2705" if cron.success else "\u274c") if style.use_emoji else ""
        label = f"{icon} {cron.job_name}" if icon else cron.job_name
        if style.format == "markdown":
            header = f"*{label}*\n"
        else:
            header = f"{label}\n"

    reasoning_block = _build_reasoning_block(msg.reasoning, style)
    sources_block = _build_sources_block(msg, style)
    tool_summary_block = _build_tool_summary_block(msg.tool_steps, style)
    cost_footer = _build_cost_footer(msg, style)

    reserve = len(header) + len(sources_block) + len(reasoning_block) + len(tool_summary_block) + len(cost_footer)
    body = (msg.content or "")[: max(style.max_text_length - reserve, 0)]
    body = strip_thinking_tags(body)

    if not sources_block:
        body = _strip_orphan_citations(body)

    return _PreparedContent(
        reasoning_block=reasoning_block,
        header=header,
        body=body,
        sources_block=sources_block,
        tool_summary_block=tool_summary_block,
        cost_footer=cost_footer,
    )


_REASONING_MAX_LEN = 2000


def _build_reasoning_block(reasoning: str | None, style: RenderStyle) -> str:
    if not reasoning or style.reasoning_display == ReasoningDisplay.OFF:
        return ""

    trimmed = reasoning.strip()
    if not trimmed:
        return ""

    if len(trimmed) > _REASONING_MAX_LEN:
        trimmed = trimmed[:_REASONING_MAX_LEN] + "…"

    if style.reasoning_display == ReasoningDisplay.COLLAPSED:
        emoji = "\U0001f9e0 " if style.use_emoji else ""
        if style.supports_latex:
            quoted = "\n".join(f"> {line}" for line in trimmed.split("\n"))
            return f"> {emoji}**Thinking**\n>\n{quoted}\n\n"
        return f"<blockquote expandable>{emoji}Thinking\n\n{trimmed}\n</blockquote>\n\n"

    emoji = "\U0001f4ad " if style.use_emoji else ""
    return f"{emoji}*Thinking:*\n{trimmed}\n\n---\n\n"


def _build_tool_summary_block(
    tool_steps: tuple[ToolStep, ...],
    style: RenderStyle,
) -> str:
    if not tool_steps or style.tool_summary_display == ToolSummaryDisplay.OFF:
        return ""

    if style.tool_summary_display == ToolSummaryDisplay.COMPACT:
        labels = [step.label for step in tool_steps]
        return "\n\n" + " → ".join(labels)

    lines: list[str] = []
    for step in tool_steps:
        line = step.label
        if step.detail:
            line += f": {step.detail}"
        lines.append(line)
    return "\n\n" + "\n".join(lines)


def _build_sources_block(msg: OutboundMessage, style: RenderStyle) -> str:
    if not msg.metadata:
        return ""
    sources = msg.metadata.get("sources")
    if not isinstance(sources, list) or not sources:
        return ""

    lines: list[str] = []
    for i, s in enumerate(sources[:10], start=1):
        url = s.get("url") if isinstance(s, dict) else None
        title = s.get("title", "Source") if isinstance(s, dict) else "Source"
        if not url:
            continue
        idx = s.get("index", i) if isinstance(s, dict) else i
        if style.supports_links and style.format in ("markdown", "mrkdwn"):
            lines.append(f"[{idx}] [{title}]({url})")
        else:
            lines.append(f"[{idx}] {title}: {url}")

    if not lines:
        return ""

    clip = "\U0001f4ce " if style.use_emoji else ""
    prefix = f"{clip}*Sources:*" if style.format == "markdown" else f"{clip}Sources:"
    return f"\n\n{prefix}\n" + "\n".join(lines)


def _build_cost_footer(msg: OutboundMessage, style: RenderStyle) -> str:
    """Build a one-line cost summary from message metadata, if available."""
    if not msg.metadata:
        return ""
    cost_meta = msg.metadata.get("cost_metadata")
    if not isinstance(cost_meta, dict):
        return ""

    cost_usd = cost_meta.get("cost_usd")
    if not isinstance(cost_usd, (int, float)) or cost_usd <= 0:
        return ""

    parts: list[str] = []
    model_name = cost_meta.get("model_name")
    if isinstance(model_name, str) and model_name:
        parts.append(model_name)

    total_tokens = cost_meta.get("total_tokens")
    if isinstance(total_tokens, int) and total_tokens > 0:
        parts.append(f"{_format_tokens(total_tokens)} tokens")

    parts.append(f"~${cost_usd:.4f}")

    sep = " · "
    line = sep.join(parts)
    if style.use_emoji:
        line = f"💰 {line}"
    return f"\n\n{line}"


def _format_tokens(n: int) -> str:
    """Format token count: 1234 → 1.2k, 12345 → 12.3k."""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


# ---------------------------------------------------------------------------
# Layer 2: Format —  based on  RenderStyle ConvertFormat
# ---------------------------------------------------------------------------


def _format(prepared: _PreparedContent, style: RenderStyle) -> str:
    parts = [
        prepared.reasoning_block,
        prepared.header,
        prepared.body,
        prepared.sources_block,
        prepared.tool_summary_block,
        prepared.cost_footer,
    ]
    raw = "".join(p for p in parts if p)

    if not raw.strip():
        raw = _EMPTY_FALLBACK

    if style.app_name_prefix:
        raw = f"{style.app_name_prefix} {raw}"

    # HTML/SVG code fences are meaningless in IM channels — replace with placeholder
    raw = _downgrade_html_fences(raw, style)

    if not style.supports_latex or not style.supports_tables:
        raw = _with_protected_code_blocks(raw, lambda t: _downgrade_content(t, style))

    if style.format == "plaintext":
        return _md_to_plaintext(raw, style)
    if style.format == "mrkdwn":
        return FormatConverterRegistry.convert(raw, "markdown", "mrkdwn")
    if style.format == "whatsapp":
        return FormatConverterRegistry.convert(raw, "markdown", "whatsapp")
    return raw


_CODE_BLOCK_PLACEHOLDER = "\x00CODEBLOCK_{}\x00"


def _with_protected_code_blocks(
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


def _downgrade_html_fences(text: str, style: RenderStyle) -> str:
    """Replace HTML/SVG code fences with a short placeholder for IM channels.

    HTML widgets are rendered visually in the web UI but are meaningless
    raw markup in text-based IM channels. This replaces them with a
    concise "[Interactive widget — view in app]" note.
    """
    if style.format == "markdown" and style.supports_code_fence:
        # Web UI or rich-markdown channel — keep original
        return text
    placeholder = (
        "\U0001f4ca [Interactive widget \u2014 view in app]" if style.use_emoji else "[Interactive widget \u2014 view in app]"
    )
    return _HTML_FENCE_RE.sub(placeholder, text)


def _downgrade_content(text: str, style: RenderStyle) -> str:
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
    """Convert Markdown tables to a readable alternative for IM platforms.

    When the channel supports code fences the table is wrapped in a plain
    code block (monospace font keeps columns aligned).  Otherwise each row
    is converted to a bullet list.
    """

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


def _md_to_plaintext(text: str, style: RenderStyle) -> str:
    result = text
    if not style.supports_code_fence:
        result = _CODE_FENCE_RE.sub(lambda m: m.group(0).strip("`").strip(), result)
    result = _BOLD_RE.sub(r"\1", result)
    result = _STRIKE_RE.sub(r"\1", result)
    result = _BLOCKQUOTE_RE.sub(" ", result)
    if not style.supports_links:
        result = _LINK_RE.sub(r"\1", result)
    return result
