"""Inline element rendering for Feishu Docx blocks (pure functions, no I/O).

[INPUT]
- (none)

[OUTPUT]
- _render_elements / _render_element: element array → Markdown inline text
- _apply_inline_style / _escape_md / _wrap_inline_code: text style helpers
- _decode_url / _render_reminder / _plain_text / _as_elements: element utils

[POS]
Pure inline-rendering helpers for feishu_render.py. Kept separate so the block
renderer stays within the 400-line module budget.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import unquote

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-!|>~$])")


def _escape_md(text: str) -> str:
    """Escape Markdown special characters in plain text."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def _wrap_inline_code(text: str) -> str:
    """Wrap text in inline code, handling nested backticks."""
    max_run = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * (max_run + 1)
    needs_padding = text.startswith("`") or text.endswith("`")
    body = f" {text} " if needs_padding else text
    return f"{fence}{body}{fence}"


def _render_elements(elements: object) -> str:
    parts: list[str] = []
    for element in _as_elements(elements):
        rendered = _render_element(element)
        if rendered:
            parts.append(rendered)
    return "".join(parts).strip()


def _render_element(element: dict[str, object]) -> str:
    text_run = element.get("text_run")
    if isinstance(text_run, dict):
        raw = text_run.get("content")
        content = raw if isinstance(raw, str) else ""
        style = text_run.get("text_element_style")
        style_dict = style if isinstance(style, dict) else {}
        link = style_dict.get("link")
        if isinstance(link, dict):
            url = _decode_url(link.get("url"))
            if url:
                return f"[{_apply_inline_style(content, style_dict)}](<{url}>)"
        return _apply_inline_style(content, style_dict)

    # @用户: Feishu only returns the OpenID, which is meaningless in rendered
    # docs; keep a semantic placeholder so the mention is not silently dropped.
    if isinstance(element.get("mention_user"), dict):
        return "@用户"

    mention_doc = element.get("mention_doc")
    if isinstance(mention_doc, dict):
        doc_url = _decode_url(mention_doc.get("url"))
        return f"[@文档](<{doc_url}>)" if doc_url else "@文档"

    reminder = element.get("reminder")
    if isinstance(reminder, dict):
        return _render_reminder(reminder)

    # Inline formula: Feishu stores KaTeX-compatible source, which MarkdownContent
    # renders via rehype-katex.
    equation = element.get("equation")
    if isinstance(equation, dict):
        eq_content = equation.get("content")
        if isinstance(eq_content, str) and eq_content:
            return f"${eq_content}$"

    return ""


def _render_reminder(reminder: dict[str, object]) -> str:
    """Render a Feishu date reminder (millisecond epoch) as a readable date."""
    raw = reminder.get("expire_time")
    if not isinstance(raw, int) or raw <= 0:
        return "@日期"
    try:
        date = datetime.fromtimestamp(raw / 1000).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return "@日期"
    return f"@{date}"


def _decode_url(raw: object) -> str:
    """Decode percent-encoded Feishu link URLs (e.g. https%3A%2F%2F...)."""
    url = raw if isinstance(raw, str) else ""
    url = unquote(url).strip()
    if url.startswith("<") and url.endswith(">"):
        return url[1:-1]
    return url


def _apply_inline_style(text: str, style: dict[str, object]) -> str:
    """Apply Feishu inline text styles to Markdown (syntax aligned with parser.py)."""
    if style.get("inline_code"):
        return _wrap_inline_code(text)

    rendered = _escape_md(text)
    if not rendered:
        return ""
    if style.get("bold"):
        rendered = f"**{rendered}**"
    if style.get("italic"):
        rendered = f"*{rendered}*"
    if style.get("underline"):
        rendered = f"<u>{rendered}</u>"
    if style.get("strikethrough"):
        rendered = f"~~{rendered}~~"
    return rendered


def _plain_text(element: dict[str, object]) -> str:
    text_run = element.get("text_run")
    if isinstance(text_run, dict):
        content = text_run.get("content")
        if isinstance(content, str):
            return content
    return ""


def _as_elements(elements: object) -> list[dict[str, object]]:
    if not isinstance(elements, list):
        return []
    return [element for element in elements if isinstance(element, dict)]


__all__ = [
    "_apply_inline_style",
    "_as_elements",
    "_decode_url",
    "_escape_md",
    "_plain_text",
    "_render_elements",
    "_render_element",
    "_render_reminder",
    "_wrap_inline_code",
]
