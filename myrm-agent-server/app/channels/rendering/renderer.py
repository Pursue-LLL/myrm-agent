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
- channels.rendering.text_utils (POS: format downgrade pure functions)

[OUTPUT]
- render(): OutboundMessage → list[str] (rendered text chunk list)

[POS]
Outbound message formatting pipeline. Converts structured OutboundMessage to platform-sendable
plain text/Markdown, performing format downgrade (LaTeX, tables, etc.) based on Channel's
RenderStyle capability declarations. Format downgrade utilities live in text_utils.py.
"""

from __future__ import annotations

from dataclasses import dataclass

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
from .text_utils import (
    downgrade_content,
    downgrade_html_fences,
    md_to_plaintext,
    strip_orphan_citations,
    strip_thinking_tags,
    with_protected_code_blocks,
)

_EMPTY_FALLBACK = "Done."


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
        body = strip_orphan_citations(body)

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

    raw = downgrade_html_fences(raw, style)

    if not style.supports_latex or not style.supports_tables:
        raw = with_protected_code_blocks(raw, lambda t: downgrade_content(t, style))

    if style.format == "plaintext":
        return md_to_plaintext(raw, style)
    if style.format == "mrkdwn":
        return FormatConverterRegistry.convert(raw, "markdown", "mrkdwn")
    if style.format == "whatsapp":
        return FormatConverterRegistry.convert(raw, "markdown", "whatsapp")
    return raw
