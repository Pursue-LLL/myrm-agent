"""Markdown artifact share page: the artifact's text rendered as a styled, script-free document.

[INPUT]
- app.core.security.share.share_markdown::build_share_markdown (POS: the Markdown renderer every share page uses, raw HTML off)
- app.core.security.share.share_locale (POS: page language and the brand line every share page shares)

[OUTPUT]
- is_markdown_media_type: whether a bundle file is Markdown
- render_markdown_share_page: the document page of a Markdown bundle file, or ``None`` when the file is too large to render

[POS]
Server business layer. A Markdown artifact opened through a share link is shown as a readable page: headings, lists,
code, tables and quotes styled for the light and the dark theme, with the page chrome in the visitor's language. The page
runs no script (its policy is ``MARKDOWN_SHARE_CSP``). Rendering happens in a worker thread on every visit. markdown-it-py takes about 0.5 s of CPU
for 256 KB of ordinary Markdown and up to 2.5 s for the slowest input measured (256 KB of bare ``[``), so a file above
``_MAX_RENDERED_BYTES`` is not rendered and the caller serves it as it is.
"""

from __future__ import annotations

import asyncio
import html
from pathlib import Path

from app.core.security.share.share_locale import HTML_LANG, SHARE_BRAND, ShareLang
from app.core.security.share.share_markdown import build_share_markdown

_MAX_RENDERED_BYTES = 256 * 1024

# A document keeps CommonMark line handling: a single newline inside a paragraph is not a line break.
_markdown = build_share_markdown(breaks=False)

_STYLE = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;color:#1f2937;line-height:1.7;padding:1rem}
.doc{max-width:800px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;padding:2rem;word-break:break-word}
.doc h1,.doc h2,.doc h3,.doc h4,.doc h5,.doc h6{font-weight:600;line-height:1.3;margin:1.75rem 0 0.6rem}
.doc>:first-child{margin-top:0}
.doc h1{font-size:1.75rem}
.doc h2{font-size:1.4rem;padding-bottom:0.3rem;border-bottom:1px solid #e5e7eb}
.doc h3{font-size:1.15rem}
.doc h4,.doc h5,.doc h6{font-size:1rem}
.doc p,.doc ul,.doc ol,.doc pre,.doc blockquote,.doc .table-wrap{margin:0 0 1rem}
.doc ul,.doc ol{padding-left:1.6rem}
.doc li+li{margin-top:0.25rem}
.doc pre{background:#1e293b;color:#e2e8f0;padding:0.9rem 1.1rem;border-radius:8px;overflow-x:auto;word-break:normal;font-family:'SF Mono',Menlo,Monaco,monospace;font-size:0.85rem;line-height:1.55}
.doc code{background:#f1f5f9;color:#1f2937;padding:1px 5px;border-radius:4px;font-family:'SF Mono',Menlo,Monaco,monospace;font-size:0.88em}
.doc pre code{background:transparent;color:inherit;padding:0;font-size:inherit}
.doc .table-wrap{overflow-x:auto}
.doc table{border-collapse:collapse;width:100%;font-size:0.92rem}
.doc th,.doc td{border:1px solid #e5e7eb;padding:0.45rem 0.7rem;text-align:left;word-break:normal}
.doc th{background:#f3f4f6;font-weight:600}
.doc blockquote{border-left:3px solid #d1d5db;padding-left:1rem;color:#4b5563}
.doc a{color:#4f46e5}
.doc img{max-width:100%;height:auto}
.doc hr{border:0;border-top:1px solid #e5e7eb;margin:1.75rem 0}
.footer{max-width:800px;margin:1rem auto 0;text-align:center;color:#6b7280;font-size:0.8rem}
@media(max-width:600px){.doc{padding:1.25rem}}
@media(prefers-color-scheme:dark){
body{background:#111827;color:#e5e7eb}
.doc{background:#1f2937;border-color:#374151}
.doc h2{border-color:#374151}
.doc code{background:#374151;color:#e2e8f0}
.doc pre{background:#0f172a}
.doc th{background:#374151}
.doc th,.doc td{border-color:#374151}
.doc blockquote{border-color:#4b5563;color:#9ca3af}
.doc a{color:#a5b4fc}
.doc hr{border-color:#374151}
.footer{color:#9ca3af}
}
"""


def is_markdown_media_type(media_type: str) -> bool:
    """Whether *media_type* (with or without parameters) names Markdown."""
    return media_type.split(";", 1)[0].strip().lower() == "text/markdown"


def _render_page(path: Path, filename: str, lang: ShareLang) -> str | None:
    if path.stat().st_size > _MAX_RENDERED_BYTES:
        return None
    body = _markdown.render(path.read_text(encoding="utf-8", errors="replace"))
    title = html.escape(Path(filename).stem or filename, quote=True)
    return f"""<!DOCTYPE html>
<html lang="{HTML_LANG[lang]}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="robots" content="noindex, nofollow">
<style>{_STYLE}</style>
</head>
<body>
<main class="doc">
{body}</main>
<p class="footer">{SHARE_BRAND[lang]}</p>
</body>
</html>"""


async def render_markdown_share_page(path: Path, filename: str, lang: ShareLang) -> str | None:
    """The document page of the Markdown file at *path* in *lang*, or ``None`` when the file is too large to render."""
    return await asyncio.to_thread(_render_page, path, filename, lang)
