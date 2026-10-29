"""Server-side HTML renderer for read-only conversation share pages.

[INPUT]
- app.services.chat.chat_service::ChatService (POS: chat metadata + messages)
- app.database.models.agent::Agent (POS: agent identity)
- app.database.dto::ChatDTO, MessageDTO (POS: data transfer object definitions)
- app.services.chat.chat_helpers (POS: what a message reads as outside the app, and which rows are the system's notes)
- app.core.security.share.share_locale (POS: page language and the language tables every share page shares)
- myrm_agent_harness.api::redact_sensitive_text (POS: the credential masker the chat export already applies)

[OUTPUT]
- render_share_html: generate self-contained HTML for a shared conversation in the visitor's language

[POS]
Generates responsive, script-free HTML pages for public conversation share links: markdown-it-py Markdown messages (code blocks
and tables that scroll inside their bubble), an Agent identity card, OG metadata, dark mode and XSS protection.
The page chrome is written in the visitor's language while the conversation is shown as written, except that credentials in the
messages, the title and the link preview are masked (best effort: the page is public). A very long conversation shows its latest
messages with the total count, and message times are printed in UTC because the page cannot know the visitor's zone.
"""

from __future__ import annotations

import asyncio
import html
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from myrm_agent_harness.api import redact_sensitive_text
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.share.share_locale import HTML_LANG, SHARE_BRAND, ShareLang
from app.database.dto import ChatDTO, MessageDTO
from app.database.models.agent import Agent
from app.services.chat.chat_helpers import exported_user_text, is_wakeup_notice
from app.services.chat.chat_service import ChatService

_TABLE_OPEN = '<div class="table-wrap">'
_TABLE_CLOSE = "</div>"


def _open_table(renderer: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
    return _TABLE_OPEN + renderer.renderToken(tokens, idx, options, env)


def _close_table(renderer: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
    return renderer.renderToken(tokens, idx, options, env) + _TABLE_CLOSE


_md = MarkdownIt("commonmark", {"breaks": True, "html": False}).enable("table")
# A wide table scrolls inside its message bubble; left alone the browser squeezes every column down to a few characters.
_md.add_render_rule("table_open", _open_table)
_md.add_render_rule("table_close", _close_table)

_OG_DESC_MAX = 200

# The page is rendered on every visit (in a worker thread, so masking credentials never stalls the event loop), nothing is
# cached, and the cost grows linearly with the message count, so a very long conversation shows its latest messages and says
# how many there are.
_MAX_SHARED_MESSAGES = 200
_VISIBLE_ROLES = frozenset({"user", "assistant"})


@dataclass(frozen=True, slots=True)
class _Chrome:
    """The page wording that is not conversation content."""

    untitled: str
    default_agent: str
    agent: str
    you: str
    assistant: str
    one_message: str
    many_messages: str
    truncated: str

    def message_count(self, count: int) -> str:
        return self.one_message if count == 1 else self.many_messages.format(count=count)

    def truncation_notice(self, shown: int, total: int) -> str:
        return self.truncated.format(shown=shown, total=total)


_CHROME: dict[ShareLang, _Chrome] = {
    "en": _Chrome(
        untitled="Shared Conversation",
        default_agent="Default Agent",
        agent="Agent",
        you="You",
        assistant="Assistant",
        one_message="1 message",
        many_messages="{count} messages",
        truncated="Showing the latest {shown} of {total} messages",
    ),
    "zh": _Chrome(
        untitled="分享的对话",
        default_agent="默认智能体",
        agent="智能体",
        you="你",
        assistant="助手",
        one_message="1 条消息",
        many_messages="{count} 条消息",
        truncated="仅显示最近 {shown} 条，共 {total} 条消息",
    ),
}


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _format_ts(dt: datetime) -> str:
    """Stored times are UTC (naive ones too) and the page runs no script, so it cannot show the visitor's own zone."""
    utc = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return utc.strftime("%Y-%m-%d %H:%M UTC")


def _truncate(text: str, max_len: int = _OG_DESC_MAX) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


async def _get_agent_info(db: AsyncSession, agent_id: str | None, chrome: _Chrome) -> dict[str, str]:
    if not agent_id:
        return {"name": chrome.default_agent, "model": "", "description": ""}
    stmt = select(Agent).where(Agent.id == agent_id)
    agent = (await db.execute(stmt)).scalars().first()
    if not agent:
        return {"name": chrome.agent, "model": "", "description": ""}
    model_name = ""
    if agent.model_selection and isinstance(agent.model_selection, dict):
        model_name = str(agent.model_selection.get("model", ""))
    return {
        "name": agent.name or chrome.agent,
        "model": model_name,
        "description": (agent.description or "")[:200],
    }


def _shared_text(msg: MessageDTO) -> str:
    """What a visitor reads of *msg*: the text as it reads outside the app, with credentials masked."""
    return redact_sensitive_text(exported_user_text(msg) if msg.role == "user" else msg.content)


def _render_message(role: str, content: str, ts: datetime, chrome: _Chrome) -> str:
    role_label = chrome.you if role == "user" else chrome.assistant
    role_class = "user" if role == "user" else "assistant"
    time_str = _format_ts(ts)
    body_html = _md.render(content) if role == "assistant" else f"<p>{_esc(content)}</p>"
    return f"""<div class="msg {role_class}">
<div class="msg-header"><span class="role">{role_label}</span><span class="time">{time_str}</span></div>
<div class="msg-body">{body_html}</div>
</div>"""


def _build_html(
    chat: ChatDTO,
    messages: list[MessageDTO],
    agent_info: dict[str, str],
    lang: ShareLang,
) -> str:
    chrome = _CHROME[lang]
    title = _esc(redact_sensitive_text(chat.title or chrome.untitled))
    # Masked before it is cut: a credential cut in half no longer matches a pattern and would be left in the preview.
    og_desc = _esc(_truncate(redact_sensitive_text(chat.first_message or chat.title or "")))

    visible = [msg for msg in messages if msg.role in _VISIBLE_ROLES and not is_wakeup_notice(msg)]
    shown = visible[-_MAX_SHARED_MESSAGES:]
    messages_html = "\n".join(_render_message(msg.role, _shared_text(msg), msg.created_at, chrome) for msg in shown)
    notice = ""
    if len(visible) > len(shown):
        notice = f'<div class="notice" role="note">{_esc(chrome.truncation_notice(len(shown), len(visible)))}</div>'
    agent_card = ""
    if agent_info["name"]:
        model_line = f'<span class="model">{_esc(agent_info["model"])}</span>' if agent_info["model"] else ""
        agent_card = f"""<div class="agent-card">
<div class="agent-name">{_esc(agent_info["name"])}</div>
{model_line}
</div>"""

    return f"""<!DOCTYPE html>
<html lang="{HTML_LANG[lang]}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta property="og:title" content="{title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:type" content="article">
<meta name="robots" content="noindex, nofollow">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;color:#1f2937;line-height:1.6;padding:1rem}}
.container{{max-width:800px;margin:0 auto}}
.header{{text-align:center;padding:1.5rem 0;border-bottom:1px solid #e5e7eb;margin-bottom:1.5rem}}
.header h1{{font-size:1.25rem;font-weight:600;color:#111827}}
.agent-card{{background:#f3f4f6;border-radius:8px;padding:0.75rem 1rem;margin-bottom:1.5rem;display:flex;align-items:center;gap:0.75rem}}
.agent-name{{font-weight:600;color:#374151}}
.model{{font-size:0.8rem;color:#4b5563;background:#e5e7eb;padding:2px 8px;border-radius:4px}}
.notice{{margin-bottom:1rem;padding:0.5rem 0.75rem;border-radius:8px;background:#f3f4f6;color:#4b5563;font-size:0.8rem;text-align:center}}
.msg{{margin-bottom:1rem;padding:1rem;border-radius:8px}}
.msg.user{{background:#eff6ff}}
.msg.assistant{{background:#ffffff;border:1px solid #e5e7eb}}
.msg-header{{display:flex;justify-content:space-between;margin-bottom:0.5rem}}
.role{{font-weight:600;font-size:0.85rem;color:#374151}}
.time{{font-size:0.75rem;color:#4b5563}}
.msg-body{{font-size:0.9rem;word-break:break-word}}
.msg-body p{{margin-bottom:0.5rem}}
.msg-body ul,.msg-body ol{{margin:0.5rem 0;padding-left:1.5rem}}
.msg-body pre{{background:#1e293b;color:#e2e8f0;padding:0.75rem 1rem;border-radius:6px;overflow-x:auto;margin:0.5rem 0;font-family:'SF Mono',Menlo,Monaco,monospace;font-size:0.82rem;line-height:1.5}}
.msg-body code{{background:#f1f5f9;padding:1px 4px;border-radius:3px;font-family:'SF Mono',Menlo,Monaco,monospace;font-size:0.85em}}
.msg-body pre code{{background:transparent;padding:0;font-size:inherit}}
.msg-body .table-wrap{{overflow-x:auto;margin:0.5rem 0}}
.msg-body table{{border-collapse:collapse;width:100%;font-size:0.85rem}}
.msg-body th,.msg-body td{{border:1px solid #e5e7eb;padding:0.4rem 0.6rem;text-align:left;word-break:normal}}
.msg-body th{{background:#f3f4f6;font-weight:600}}
.msg-body blockquote{{border-left:3px solid #d1d5db;padding-left:0.75rem;margin:0.5rem 0;color:#6b7280}}
.msg-body a{{color:#4f46e5}}
.msg-body strong{{font-weight:600}}
.msg-body h1,.msg-body h2,.msg-body h3{{margin:0.75rem 0 0.25rem;font-weight:600}}
.footer{{text-align:center;padding:1.5rem 0;border-top:1px solid #e5e7eb;margin-top:1.5rem;color:#6b7280;font-size:0.8rem}}
.stats{{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-bottom:0.5rem}}
.stat{{font-size:0.75rem;color:#6b7280}}
@media(prefers-color-scheme:dark){{
body{{background:#111827;color:#e5e7eb}}
.header h1{{color:#f9fafb}}
.header{{border-color:#374151}}
.agent-card{{background:#1f2937}}
.agent-name{{color:#e5e7eb}}
.model{{background:#374151;color:#d1d5db}}
.notice{{background:#1f2937;color:#9ca3af}}
.msg.user{{background:#1e3a5f}}
.msg.assistant{{background:#1f2937;border-color:#374151}}
.role{{color:#e5e7eb}}
.time{{color:#9ca3af}}
.msg-body code{{background:#374151;color:#e2e8f0}}
.msg-body pre{{background:#0f172a}}
.msg-body th{{background:#374151}}
.msg-body th,.msg-body td{{border-color:#374151}}
.msg-body blockquote{{border-color:#4b5563;color:#9ca3af}}
.msg-body a{{color:#a5b4fc}}
.footer{{border-color:#374151;color:#9ca3af}}
.stat{{color:#9ca3af}}
}}
</style>
</head>
<body>
<div class="container">
<div class="header"><h1>{title}</h1></div>
{agent_card}
{notice}
{messages_html}
<div class="footer">
<div class="stats">
<span class="stat">{chrome.message_count(len(visible))}</span>
<span class="stat">{_format_ts(chat.created_at)}</span>
</div>
<p>{SHARE_BRAND[lang]}</p>
</div>
</div>
</body>
</html>"""


async def render_share_html(
    chat_id: str,
    db: AsyncSession,
    *,
    lang: ShareLang,
) -> str | None:
    """Generate HTML for a shared conversation in *lang*. Returns None if chat not found."""
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        return None

    messages = await ChatService.get_all_messages(chat_id)
    agent_info = await _get_agent_info(db, chat.agent_id, _CHROME[lang])

    return await asyncio.to_thread(_build_html, chat, messages, agent_info, lang)
