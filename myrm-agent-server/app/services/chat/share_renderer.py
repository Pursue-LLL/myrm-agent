"""Server-side HTML renderer for read-only conversation share pages.

[INPUT]
- app.services.chat.chat_service::ChatService (POS: chat metadata + messages)
- app.database.models.agent::Agent (POS: agent identity)

[OUTPUT]
- render_share_html: generate self-contained HTML for a shared conversation

[POS]
Generates responsive, secure HTML pages for public conversation share links.
Includes Agent identity card, message history, tool/usage summary, and OG metadata.
"""

from __future__ import annotations

import html
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import ChatDTO, MessageDTO
from app.database.models.agent import Agent
from app.services.chat.chat_service import ChatService

_OG_DESC_MAX = 200


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _format_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _truncate(text: str, max_len: int = _OG_DESC_MAX) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


async def _get_agent_info(db: AsyncSession, agent_id: str | None) -> dict[str, str]:
    if not agent_id:
        return {"name": "Default Agent", "model": "", "description": ""}
    stmt = select(Agent).where(Agent.id == agent_id)
    agent = (await db.execute(stmt)).scalars().first()
    if not agent:
        return {"name": "Agent", "model": "", "description": ""}
    return {
        "name": agent.name or "Agent",
        "model": agent.model or "",
        "description": (agent.description or "")[:200],
    }


def _render_message(role: str, content: str, ts: datetime) -> str:
    role_label = "You" if role == "user" else "Assistant"
    role_class = "user" if role == "user" else "assistant"
    escaped = _esc(content)
    time_str = _format_ts(ts)
    return f"""<div class="msg {role_class}">
<div class="msg-header"><span class="role">{role_label}</span><span class="time">{time_str}</span></div>
<div class="msg-body"><pre>{escaped}</pre></div>
</div>"""


def _build_html(
    chat: ChatDTO,
    messages: list[MessageDTO],
    agent_info: dict[str, str],
) -> str:
    title = _esc(chat.title or "Shared Conversation")
    og_desc = _esc(_truncate(chat.first_message or chat.title or ""))

    msg_html_parts: list[str] = []
    visible_roles = {"user", "assistant"}
    for msg in messages[-200:]:
        if msg.role not in visible_roles:
            continue
        msg_html_parts.append(_render_message(msg.role, msg.content, msg.created_at))

    messages_html = "\n".join(msg_html_parts)
    agent_card = ""
    if agent_info["name"]:
        model_line = f'<span class="model">{_esc(agent_info["model"])}</span>' if agent_info["model"] else ""
        agent_card = f"""<div class="agent-card">
<div class="agent-name">{_esc(agent_info["name"])}</div>
{model_line}
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
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
.model{{font-size:0.8rem;color:#6b7280;background:#e5e7eb;padding:2px 8px;border-radius:4px}}
.msg{{margin-bottom:1rem;padding:1rem;border-radius:8px}}
.msg.user{{background:#eff6ff}}
.msg.assistant{{background:#ffffff;border:1px solid #e5e7eb}}
.msg-header{{display:flex;justify-content:space-between;margin-bottom:0.5rem}}
.role{{font-weight:600;font-size:0.85rem;color:#374151}}
.time{{font-size:0.75rem;color:#9ca3af}}
.msg-body pre{{white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:0.9rem}}
.footer{{text-align:center;padding:1.5rem 0;border-top:1px solid #e5e7eb;margin-top:1.5rem;color:#9ca3af;font-size:0.8rem}}
.stats{{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-bottom:0.5rem}}
.stat{{font-size:0.75rem;color:#6b7280}}
</style>
</head>
<body>
<div class="container">
<div class="header"><h1>{title}</h1></div>
{agent_card}
{messages_html}
<div class="footer">
<div class="stats">
<span class="stat">{len(msg_html_parts)} messages</span>
<span class="stat">{_format_ts(chat.created_at)}</span>
</div>
<p>Shared via Myrm Agent</p>
</div>
</div>
</body>
</html>"""


async def render_share_html(
    chat_id: str,
    db: AsyncSession,
) -> str | None:
    """Generate HTML for a shared conversation. Returns None if chat not found."""
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        return None

    messages = await ChatService.get_all_messages(chat_id)
    agent_info = await _get_agent_info(db, chat.agent_id)

    return _build_html(chat, messages, agent_info)
