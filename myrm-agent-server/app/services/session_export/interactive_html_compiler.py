"""Interactive Standalone Single-File HTML Compiler for conversation session exports.

[INPUT] ExportTurnMessage, ExportHtmlOptions, secret_redactor
[OUTPUT] InteractiveHtmlCompiler: Generates zero-dependency offline self-contained HTML with inlined JS/CSS.
[POS] app/services/session_export/interactive_html_compiler.py
"""

import html
from markdown_it import MarkdownIt

from app.services.session_export.export_types import (
    ExportHtmlOptions,
    ExportTurnMessage,
    InteractiveHtmlExportResult,
    RedactionSummary,
)
from app.services.session_export.secret_redactor import secret_redactor

_md = MarkdownIt("commonmark", {"breaks": True, "html": False}).enable("table")


def _esc(val: str) -> str:
    return html.escape(val, quote=True)


class InteractiveHtmlCompiler:
    """Compiles multi-turn agent conversation into a standalone, offline interactive HTML document."""

    @classmethod
    def compile_session(
        cls,
        chat_id: str,
        title: str,
        agent_name: str,
        messages: list[ExportTurnMessage],
        options: ExportHtmlOptions,
    ) -> InteractiveHtmlExportResult:
        """Compile messages into self-contained HTML with search, toggle, and code-copy capabilities."""
        total_redacted = 0
        details_list = []
        rendered_messages: list[str] = []

        for idx, msg in enumerate(messages):
            content = msg.content
            thinking = msg.thinking
            tool_calls = msg.tool_calls

            # Apply credential redaction if enabled
            if options.enable_redaction:
                content, sum_content = secret_redactor.redact_text(content)
                total_redacted += sum_content.total_redacted
                details_list.extend(sum_content.details)

                if thinking:
                    thinking, sum_think = secret_redactor.redact_text(thinking)
                    total_redacted += sum_think.total_redacted
                    details_list.extend(sum_think.details)

            rendered_messages.append(
                cls._render_message(
                    idx=idx,
                    role=msg.role,
                    content=content,
                    created_at=msg.created_at,
                    thinking=thinking if options.include_thinking else None,
                    tool_calls=tool_calls if options.include_tool_calls else [],
                )
            )

        redaction_summary = RedactionSummary(
            total_redacted=total_redacted,
            has_secrets=total_redacted > 0,
            details=details_list,
        )

        html_body = "\n".join(rendered_messages)
        full_html = cls._build_document(
            chat_id=chat_id,
            title=title,
            agent_name=agent_name,
            body_html=html_body,
            message_count=len(messages),
            redaction_summary=redaction_summary,
            default_theme=options.theme,
        )

        safe_title = "".join(c for c in title if c.isalnum() or c in ("-", "_")).strip() or "session"
        file_name = f"myrm-session-{safe_title[:30]}-{chat_id[:8]}.html"

        return InteractiveHtmlExportResult(
            chat_id=chat_id,
            title=title,
            file_name=file_name,
            html_content=full_html,
            size_bytes=len(full_html.encode("utf-8")),
            total_messages=len(messages),
            redaction_summary=redaction_summary,
        )

    @classmethod
    def _render_message(
        cls,
        idx: int,
        role: str,
        content: str,
        created_at: str,
        thinking: str | None,
        tool_calls: list[dict[str, str]],
    ) -> str:
        role_class = "user" if role == "user" else "assistant"
        role_label = "User" if role == "user" else "Assistant"

        thinking_html = ""
        if thinking and thinking.strip():
            thinking_html = f"""<details class="thinking-drawer" open>
<summary><span class="drawer-icon">&#129504;</span> <span class="drawer-title">Reasoning & Thinking</span></summary>
<div class="thinking-content">{_esc(thinking.strip())}</div>
</details>"""

        tool_calls_html = ""
        if tool_calls:
            tc_items = []
            for tc in tool_calls:
                name = _esc(tc.get("tool_name", "tool"))
                args = _esc(tc.get("arguments", ""))
                out = _esc(tc.get("output", ""))
                tc_items.append(
                    f"""<div class="tool-call-item">
<div class="tool-call-head"><span class="tool-badge">&#9881; {name}</span></div>
<div class="tool-detail"><span class="label">Args:</span> <pre>{args}</pre></div>
<div class="tool-detail"><span class="label">Result:</span> <pre>{out}</pre></div>
</div>"""
                )
            tool_calls_html = f"""<details class="tools-drawer">
<summary><span class="drawer-icon">&#9874;</span> <span class="drawer-title">Tool Calls ({len(tool_calls)})</span></summary>
<div class="tools-container">{"".join(tc_items)}</div>
</details>"""

        body_html = _md.render(content) if role == "assistant" else f"<p>{_esc(content)}</p>"

        return f"""<div class="msg {role_class}" data-index="{idx}">
<div class="msg-header">
  <span class="role-badge {role_class}">{role_label}</span>
  <span class="timestamp">{_esc(created_at)}</span>
</div>
{thinking_html}
{tool_calls_html}
<div class="msg-content">{body_html}</div>
</div>"""

    @classmethod
    def _build_document(
        cls,
        chat_id: str,
        title: str,
        agent_name: str,
        body_html: str,
        message_count: int,
        redaction_summary: RedactionSummary,
        default_theme: str,
    ) -> str:
        esc_title = _esc(title)
        redact_badge = ""
        if redaction_summary.has_secrets:
            redact_badge = f"""<span class="badge badge-shield">&#128737; Sanitized ({redaction_summary.total_redacted} credentials scrubbed)</span>"""

        return f"""<!DOCTYPE html>
<html lang="en" data-theme="{default_theme}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc_title} - Myrm Agent Session Export</title>
<style>
:root {{
  --bg: #f8fafc;
  --card-bg: #ffffff;
  --text: #0f172a;
  --text-muted: #64748b;
  --border: #e2e8f0;
  --primary: #4f46e5;
  --primary-light: #eef2ff;
  --user-bg: #eff6ff;
  --user-border: #bfdbfe;
  --thinking-bg: #f1f5f9;
  --code-bg: #1e293b;
  --code-text: #f8fafc;
}}
[data-theme="dark"] {{
  --bg: #090d16;
  --card-bg: #111827;
  --text: #f1f5f9;
  --text-muted: #94a3b8;
  --border: #1f2937;
  --primary: #6366f1;
  --primary-light: #1e1e38;
  --user-bg: #1e293b;
  --user-border: #334155;
  --thinking-bg: #151d2f;
  --code-bg: #030712;
  --code-text: #f9fafb;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem 1rem; }}
.container {{ max-width: 860px; margin: 0 auto; }}
.top-nav {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 1rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--border); margin-bottom: 2rem; }}
.top-nav h1 {{ font-size: 1.25rem; font-weight: 700; }}
.top-controls {{ display: flex; align-items: center; gap: 0.5rem; }}
.search-input {{ padding: 0.4rem 0.75rem; border: 1px solid var(--border); border-radius: 8px; background: var(--card-bg); color: var(--text); font-size: 0.85rem; outline: none; }}
.btn {{ padding: 0.4rem 0.75rem; border-radius: 8px; border: 1px solid var(--border); background: var(--card-bg); color: var(--text); font-size: 0.82rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }}
.btn:hover {{ background: var(--primary-light); border-color: var(--primary); }}
.meta-bar {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 1.5rem; font-size: 0.8rem; color: var(--text-muted); }}
.badge {{ padding: 0.2rem 0.6rem; border-radius: 9999px; font-weight: 600; font-size: 0.75rem; }}
.badge-agent {{ background: var(--primary-light); color: var(--primary); }}
.badge-shield {{ background: #ecfdf5; color: #059669; border: 1px solid #a7f3d0; }}
[data-theme="dark"] .badge-shield {{ background: #064e3b; color: #6ee7b7; border-color: #047857; }}
.msg {{ margin-bottom: 1.5rem; padding: 1.25rem; border-radius: 12px; border: 1px solid var(--border); background: var(--card-bg); box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
.msg.user {{ background: var(--user-bg); border-color: var(--user-border); }}
.msg-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }}
.role-badge {{ font-weight: 700; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
.role-badge.user {{ color: #2563eb; }}
.role-badge.assistant {{ color: var(--primary); }}
.timestamp {{ font-size: 0.75rem; color: var(--text-muted); }}
.thinking-drawer, .tools-drawer {{ margin-bottom: 1rem; border-radius: 8px; background: var(--thinking-bg); border: 1px solid var(--border); padding: 0.5rem 0.75rem; font-size: 0.85rem; }}
.thinking-drawer summary, .tools-drawer summary {{ cursor: pointer; font-weight: 600; user-select: none; outline: none; }}
.thinking-content {{ margin-top: 0.5rem; font-style: italic; color: var(--text-muted); font-size: 0.85rem; white-space: pre-wrap; }}
.tools-container {{ margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.5rem; }}
.tool-call-item {{ background: var(--card-bg); padding: 0.5rem; border-radius: 6px; border: 1px solid var(--border); }}
.tool-badge {{ font-family: monospace; font-size: 0.8rem; font-weight: 700; color: #d97706; }}
.tool-detail {{ font-size: 0.8rem; margin-top: 0.25rem; }}
.tool-detail pre {{ background: var(--thinking-bg); padding: 0.4rem; border-radius: 4px; overflow-x: auto; font-family: monospace; }}
.msg-content {{ font-size: 0.95rem; word-break: break-word; }}
.msg-content pre {{ position: relative; background: var(--code-bg); color: var(--code-text); padding: 1rem; border-radius: 8px; overflow-x: auto; margin: 0.75rem 0; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.85rem; line-height: 1.5; }}
.copy-btn {{ position: absolute; top: 0.5rem; right: 0.5rem; background: rgba(255,255,255,0.15); color: #ffffff; border: 1px solid rgba(255,255,255,0.25); border-radius: 4px; padding: 0.2rem 0.5rem; font-size: 0.72rem; cursor: pointer; }}
.copy-btn:hover {{ background: rgba(255,255,255,0.3); }}
.msg-content code {{ background: var(--thinking-bg); padding: 0.2rem 0.4rem; border-radius: 4px; font-family: monospace; font-size: 0.88em; }}
.msg-content pre code {{ background: transparent; padding: 0; }}
.msg-content table {{ width: 100%; border-collapse: collapse; margin: 0.75rem 0; font-size: 0.88rem; }}
.msg-content th, .msg-content td {{ border: 1px solid var(--border); padding: 0.5rem; text-align: left; }}
.msg-content th {{ background: var(--thinking-bg); font-weight: 600; }}
.footer {{ text-align: center; margin-top: 3rem; font-size: 0.8rem; color: var(--text-muted); border-top: 1px solid var(--border); padding-top: 1.5rem; }}
/* 系统偏好减少动态效果时把过渡收到瞬时：导出的 HTML 是独立文档，宿主样式表的守卫到不了这里。 */
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }}
}}
</style>
</head>
<body>
<div class="container">
  <div class="top-nav">
    <div>
      <h1>{esc_title}</h1>
    </div>
    <div class="top-controls">
      <input type="text" id="searchInput" class="search-input" placeholder="Search conversation...">
      <button class="btn" id="toggleDetailsBtn">Toggle Thinking</button>
      <button class="btn" id="themeToggleBtn">&#9790; Theme</button>
    </div>
  </div>

  <div class="meta-bar">
    <span class="badge badge-agent">&#129302; {_esc(agent_name)}</span>
    <span>{message_count} messages</span>
    <span>Session ID: {_esc(chat_id[:12])}</span>
    {redact_badge}
  </div>

  <div id="messagesList">
    {body_html}
  </div>

  <div class="footer">
    <p>Exported with <strong>Myrm Agent</strong> &bull; Zero External Dependencies</p>
  </div>
</div>

<script>
(function() {{
  // Theme toggle
  const htmlEl = document.documentElement;
  const themeBtn = document.getElementById('themeToggleBtn');
  themeBtn.addEventListener('click', () => {{
    const current = htmlEl.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    htmlEl.setAttribute('data-theme', next);
  }});

  // Toggle details
  let detailsOpen = true;
  const toggleBtn = document.getElementById('toggleDetailsBtn');
  toggleBtn.addEventListener('click', () => {{
    detailsOpen = !detailsOpen;
    document.querySelectorAll('details').forEach(d => {{
      d.open = detailsOpen;
    }});
  }});

  // Search filter
  const searchInput = document.getElementById('searchInput');
  searchInput.addEventListener('input', (e) => {{
    const q = e.target.value.toLowerCase().trim();
    document.querySelectorAll('.msg').forEach(m => {{
      m.style.display = (!q || m.textContent.toLowerCase().includes(q)) ? 'block' : 'none';
    }});
  }});

  // Code block copy buttons
  document.querySelectorAll('pre').forEach(pre => {{
    const btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = 'Copy';
    btn.addEventListener('click', () => {{
      const code = pre.querySelector('code') ? pre.querySelector('code').innerText : pre.innerText;
      navigator.clipboard.writeText(code).then(() => {{
        btn.textContent = 'Copied!';
        setTimeout(() => {{ btn.textContent = 'Copy'; }}, 2000);
      }});
    }});
    pre.appendChild(btn);
  }});
}})();
</script>
</body>
</html>"""
