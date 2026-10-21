"""Comment content extraction and prompt construction utilities.

Pure functions for extracting text from Feishu comment reply structures,
timeline selection, document link resolution, and prompt building.

[INPUT]
- (none — pure functions operating on dict data)

[OUTPUT]
- _extract_reply_text, _extract_semantic_text, _get_reply_user_id: content extractors
- _extract_docs_links, _resolve_wiki_links, _format_referenced_docs: doc link helpers
- _select_local_timeline, _select_whole_timeline: timeline selectors
- build_local_comment_prompt, build_whole_comment_prompt: prompt builders

[POS]
Comment content extraction and prompt construction. Pure functions, zero I/O
(except wiki link resolution which requires FeishuClient).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.channels.providers.feishu.api import FeishuClient

_PROMPT_TEXT_LIMIT = 220
_LOCAL_TIMELINE_LIMIT = 20
_WHOLE_TIMELINE_LIMIT = 12

_TimelineEntry = tuple[str, str, bool]  # (user_id, text, is_self)

_FEISHU_DOC_URL_RE = re.compile(
    r"(?:feishu\.cn|larkoffice\.com|larksuite\.com|lark\.suite\.com)"
    r"/(?P<doc_type>wiki|doc|docx|sheet|sheets|slides|mindnote|bitable|base|file)"
    r"/(?P<token>[A-Za-z0-9_-]{10,40})"
)


# ── Comment content extraction ─────────────────────────────────


def _extract_reply_text(reply: dict[str, object]) -> str:
    """Extract plain text from a comment reply's content structure."""
    content = reply.get("content", {})
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return str(content)

    if not isinstance(content, dict):
        return ""
    elements = content.get("elements", [])
    if not isinstance(elements, list):
        return ""
    parts: list[str] = []
    for elem in elements:
        if not isinstance(elem, dict):
            continue
        elem_type = elem.get("type", "")
        if elem_type == "text_run":
            text_run = elem.get("text_run", {})
            if isinstance(text_run, dict):
                parts.append(str(text_run.get("text", "")))
        elif elem_type == "docs_link":
            docs_link = elem.get("docs_link", {})
            if isinstance(docs_link, dict):
                parts.append(str(docs_link.get("url", "")))
        elif elem_type == "person":
            person = elem.get("person", {})
            if isinstance(person, dict):
                parts.append(f"@{person.get('user_id', 'unknown')}")
    return "".join(parts)


def _extract_semantic_text(reply: dict[str, object], self_open_id: str = "") -> str:
    """Extract semantic text, stripping self @mentions and whitespace."""
    content = reply.get("content", {})
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return str(content)

    if not isinstance(content, dict):
        return ""
    elements = content.get("elements", [])
    if not isinstance(elements, list):
        return ""
    parts: list[str] = []
    for elem in elements:
        if not isinstance(elem, dict):
            continue
        elem_type = elem.get("type", "")
        if elem_type == "person":
            person = elem.get("person", {})
            uid = str(person.get("user_id", "")) if isinstance(person, dict) else ""
            if self_open_id and uid == self_open_id:
                continue
            parts.append(f"@{uid}")
        elif elem_type == "text_run":
            text_run = elem.get("text_run", {})
            if isinstance(text_run, dict):
                parts.append(str(text_run.get("text", "")))
        elif elem_type == "docs_link":
            docs_link = elem.get("docs_link", {})
            if isinstance(docs_link, dict):
                parts.append(str(docs_link.get("url", "")))
    return " ".join("".join(parts).split()).strip()


def _get_reply_user_id(reply: dict[str, object]) -> str:
    """Extract user_id from a reply dict."""
    user_id = reply.get("user_id", "")
    if isinstance(user_id, dict):
        return str(user_id.get("open_id", "") or user_id.get("user_id", ""))
    return str(user_id)


# ── Document link extraction ───────────────────────────────────


def _extract_docs_links(replies: list[dict[str, object]]) -> list[dict[str, str]]:
    """Extract unique document links from comment replies."""
    seen_tokens: set[str] = set()
    links: list[dict[str, str]] = []
    for reply in replies:
        content = reply.get("content", {})
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                continue
        if not isinstance(content, dict):
            continue
        elements = content.get("elements", [])
        if not isinstance(elements, list):
            continue
        for elem in elements:
            if not isinstance(elem, dict):
                continue
            if elem.get("type") not in {"docs_link", "link"}:
                continue
            link_data = elem.get("docs_link") or elem.get("link") or {}
            if not isinstance(link_data, dict):
                continue
            url = str(link_data.get("url", ""))
            if not url:
                continue
            m = _FEISHU_DOC_URL_RE.search(url)
            if not m:
                continue
            token = m.group("token")
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            links.append({"url": url, "doc_type": m.group("doc_type"), "token": token})
    return links


async def _resolve_wiki_links(
    client: FeishuClient,
    links: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Resolve wiki links to their underlying document type and token."""
    for link in links:
        if link["doc_type"] != "wiki":
            continue
        wiki_token = await client.get_wiki_node(link["token"])
        if not wiki_token:
            continue
        link["resolved_token"] = wiki_token
    return links


def _format_referenced_docs(
    links: list[dict[str, str]],
    current_file_token: str = "",
) -> str:
    """Format resolved document links for prompt embedding."""
    if not links:
        return ""
    lines = ["", "Referenced documents in comments:"]
    for link in links:
        rtype = link.get("resolved_type", link["doc_type"])
        rtoken = link.get("resolved_token", link["token"])
        suffix = " (same as current document)" if rtoken == current_file_token else ""
        url_preview = link["url"][:80]
        lines.append(f"- {rtype}:{rtoken}{suffix} ({url_preview})")
    return "\n".join(lines)


# ── Timeline selection ─────────────────────────────────────────


def _select_local_timeline(
    timeline: list[_TimelineEntry],
    target_index: int,
) -> list[_TimelineEntry]:
    """Select up to _LOCAL_TIMELINE_LIMIT entries centered on target_index."""
    if len(timeline) <= _LOCAL_TIMELINE_LIMIT:
        return timeline
    n = len(timeline)
    selected: set[int] = {0, n - 1}
    if 0 <= target_index < n:
        selected.add(target_index)
    budget = _LOCAL_TIMELINE_LIMIT - len(selected)
    lo, hi = target_index - 1, target_index + 1
    while budget > 0 and (lo >= 0 or hi < n):
        if lo >= 0 and lo not in selected:
            selected.add(lo)
            budget -= 1
        lo -= 1
        if budget > 0 and hi < n and hi not in selected:
            selected.add(hi)
            budget -= 1
        hi += 1
    return [timeline[i] for i in sorted(selected)]


def _select_whole_timeline(
    timeline: list[_TimelineEntry],
    current_index: int,
    nearest_self_index: int,
) -> list[_TimelineEntry]:
    """Select up to _WHOLE_TIMELINE_LIMIT entries for whole-doc comments."""
    if len(timeline) <= _WHOLE_TIMELINE_LIMIT:
        return timeline
    n = len(timeline)
    selected: set[int] = set()
    if 0 <= current_index < n:
        selected.add(current_index)
    if 0 <= nearest_self_index < n:
        selected.add(nearest_self_index)
    budget = _WHOLE_TIMELINE_LIMIT - len(selected)
    lo, hi = current_index - 1, current_index + 1
    while budget > 0 and (lo >= 0 or hi < n):
        if lo >= 0 and lo not in selected:
            selected.add(lo)
            budget -= 1
        lo -= 1
        if budget > 0 and hi < n and hi not in selected:
            selected.add(hi)
            budget -= 1
        hi += 1
    if not selected:
        return timeline[-_WHOLE_TIMELINE_LIMIT:]
    return [timeline[i] for i in sorted(selected)]


def _truncate(text: str, limit: int = _PROMPT_TEXT_LIMIT) -> str:
    return text[:limit] + "..." if len(text) > limit else text


# ── Prompt construction ────────────────────────────────────────

_COMMON_INSTRUCTIONS = """
This is a Feishu document comment thread, not an IM chat.
Your reply will be posted automatically. Just output the reply text.
Use the thread timeline above as the main context.
Reply in the same language as the user's comment unless they request otherwise.
Use plain text only. Do not use Markdown, headings, bullet lists, tables, or code blocks.
Do not show your reasoning process. Do not start with "I will", "Let me", or "I'll first".
Output only the final user-facing reply.
If no reply is needed, output exactly NO_REPLY.
""".strip()


def build_local_comment_prompt(
    *,
    doc_title: str,
    doc_url: str,
    file_token: str,
    file_type: str,
    comment_id: str,
    quote_text: str,
    root_comment_text: str,
    target_reply_text: str,
    timeline: list[_TimelineEntry],
    self_open_id: str,
    target_index: int = -1,
    referenced_docs: str = "",
) -> str:
    """Build the prompt for a local (quoted-text) comment."""
    selected = _select_local_timeline(timeline, target_index)
    lines = [
        f'The user added a reply in "{doc_title}".',
        f'Current user comment text: "{_truncate(target_reply_text)}"',
        f'Original comment text: "{_truncate(root_comment_text)}"',
        f'Quoted content: "{_truncate(quote_text, 500)}"',
        "This comment mentioned you (@mention is for routing, not task content).",
        f"Document link: {doc_url}",
        "Current commented document:",
        f"- file_type={file_type}",
        f"- file_token={file_token}",
        f"- comment_id={comment_id}",
        "",
        f"Current comment card timeline ({len(selected)}/{len(timeline)} entries):",
    ]
    for user_id, text, is_self in selected:
        marker = " <-- YOU" if is_self else ""
        lines.append(f"[{user_id}] {_truncate(text)}{marker}")
    if referenced_docs:
        lines.append(referenced_docs)
    lines.append("")
    lines.append(_COMMON_INSTRUCTIONS)
    return "\n".join(lines)


def build_whole_comment_prompt(
    *,
    doc_title: str,
    doc_url: str,
    file_token: str,
    file_type: str,
    comment_text: str,
    timeline: list[_TimelineEntry],
    self_open_id: str,
    current_index: int = -1,
    nearest_self_index: int = -1,
    referenced_docs: str = "",
) -> str:
    """Build the prompt for a whole-document comment."""
    selected = _select_whole_timeline(timeline, current_index, nearest_self_index)
    lines = [
        f'The user added a comment in "{doc_title}".',
        f'Current user comment text: "{_truncate(comment_text)}"',
        "This is a whole-document comment.",
        "This comment mentioned you (@mention is for routing, not task content).",
        f"Document link: {doc_url}",
        "Current commented document:",
        f"- file_type={file_type}",
        f"- file_token={file_token}",
        "",
        f"Whole-document comment timeline ({len(selected)}/{len(timeline)} entries):",
    ]
    for user_id, text, is_self in selected:
        marker = " <-- YOU" if is_self else ""
        lines.append(f"[{user_id}] {_truncate(text)}{marker}")
    if referenced_docs:
        lines.append(referenced_docs)
    lines.append("")
    lines.append(_COMMON_INSTRUCTIONS)
    return "\n".join(lines)
