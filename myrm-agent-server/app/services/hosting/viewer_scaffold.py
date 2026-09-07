"""Standalone viewer scaffolding for static hosting platforms.

[INPUT]
- app.services.hosting.packager::PublishFile (POS: deployable file representation)
- app.services.hosting.packager::ensure_index_html_alias (POS: single HTML entry point aliasing)

[OUTPUT]
- STANDALONE_VIEWER_EXTENSIONS: set of file extensions eligible for viewer wrapper
- can_scaffold_viewer: check if payload can be wrapped into a standalone web viewer
- render_standalone_viewer_html: generate responsive standalone viewer HTML
- ensure_viewer_wrapper_for_payload: inject index.html viewer wrapper into payload

[POS]
Hosting business service — generates high-fidelity standalone web viewer wrappers for non-HTML artifacts on static hosts.
"""

from __future__ import annotations

import html
from pathlib import Path

from app.services.hosting.packager import PublishFile, ensure_index_html_alias

STANDALONE_VIEWER_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".md",
        ".markdown",
        ".txt",
        ".csv",
        ".json",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
        ".xlsx",
        ".xls",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
    }
)

EMBEDDABLE_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".md",
        ".markdown",
        ".txt",
        ".csv",
        ".json",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
    }
)


def can_scaffold_viewer(files: dict[str, PublishFile]) -> bool:
    """Return whether a non-HTML payload qualifies for static viewer wrapping."""
    if not files:
        return False
    if "index.html" in files:
        return False

    root_entries = [name for name in files if "/" not in name]
    if len(root_entries) == 1:
        return Path(root_entries[0]).suffix.lower() in STANDALONE_VIEWER_EXTENSIONS
    doc_entries = [name for name in root_entries if Path(name).suffix.lower() in STANDALONE_VIEWER_EXTENSIONS]
    return len(doc_entries) == 1


def render_standalone_viewer_html(primary_file: str, title: str | None = None) -> str:
    """Render a clean, responsive standalone viewer index.html for static hosting platforms."""
    safe_title = html.escape(title or primary_file)
    safe_file = html.escape(primary_file)
    ext = Path(primary_file).suffix.lower()
    is_embeddable = ext in EMBEDDABLE_EXTENSIONS

    if is_embeddable:
        content_view = (
            f'<iframe src="./{safe_file}" title="{safe_title}" class="viewer-frame"></iframe>'
        )
    else:
        content_view = (
            '<div class="card-wrapper">'
            '  <div class="doc-card">'
            '    <div class="doc-badge">DOCUMENT ARTIFACT</div>'
            f'   <h2 class="doc-title">{safe_title}</h2>'
            f'   <p class="doc-filename">File: <code>{safe_file}</code></p>'
            '    <div class="doc-meta">This format is optimized for download or native desktop viewing.</div>'
            f'   <a href="./{safe_file}" download class="btn-primary">Download {ext.upper().lstrip(".")} File</a>'
            '  </div>'
            '</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{safe_title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
      background: #090d16;
      color: #f1f5f9;
      overflow: hidden;
    }}
    header {{
      height: 48px;
      background: #111827;
      border-bottom: 1px solid #1f2937;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 1.25rem;
      flex-shrink: 0;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.875rem;
      font-weight: 600;
      color: #e2e8f0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .brand-tag {{
      background: rgba(59, 130, 246, 0.15);
      color: #60a5fa;
      font-size: 0.75rem;
      padding: 0.125rem 0.375rem;
      border-radius: 4px;
      font-weight: 500;
    }}
    .actions {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}
    .actions a {{
      display: inline-flex;
      align-items: center;
      padding: 0.3125rem 0.75rem;
      font-size: 0.8125rem;
      font-weight: 500;
      border-radius: 0.375rem;
      text-decoration: none;
      transition: all 0.15s ease-in-out;
    }}
    .btn-dl {{
      background: #1f2937;
      color: #e2e8f0;
      border: 1px solid #374151;
    }}
    .btn-dl:hover {{
      background: #374151;
      color: #ffffff;
    }}
    .btn-raw {{
      background: #2563eb;
      color: #ffffff;
    }}
    .btn-raw:hover {{
      background: #1d4ed8;
    }}
    .viewer-frame {{
      flex: 1;
      width: 100%;
      height: calc(100vh - 48px);
      border: none;
      background: #0d1117;
    }}
    .card-wrapper {{
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
      background: radial-gradient(circle at 50% 30%, #1e293b 0%, #090d16 80%);
    }}
    .doc-card {{
      background: #111827;
      border: 1px solid #1f2937;
      border-radius: 0.75rem;
      padding: 2.5rem 2rem;
      max-width: 480px;
      width: 100%;
      text-align: center;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
    }}
    .doc-badge {{
      display: inline-block;
      font-size: 0.6875rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: #38bdf8;
      background: rgba(56, 189, 248, 0.1);
      padding: 0.25rem 0.625rem;
      border-radius: 9999px;
      margin-bottom: 1rem;
    }}
    .doc-title {{
      font-size: 1.25rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
      color: #f8fafc;
    }}
    .doc-filename {{
      font-size: 0.875rem;
      color: #94a3b8;
      margin-bottom: 1rem;
    }}
    .doc-filename code {{
      background: #1f2937;
      padding: 0.125rem 0.375rem;
      border-radius: 4px;
      color: #e2e8f0;
    }}
    .doc-meta {{
      font-size: 0.8125rem;
      color: #64748b;
      margin-bottom: 1.5rem;
    }}
    .btn-primary {{
      display: inline-block;
      width: 100%;
      padding: 0.625rem 1rem;
      background: #2563eb;
      color: #ffffff;
      font-size: 0.875rem;
      font-weight: 500;
      border-radius: 0.5rem;
      text-decoration: none;
      transition: background-color 0.15s;
    }}
    .btn-primary:hover {{
      background: #1d4ed8;
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="brand-tag">ARTIFACT</span>
      <span>{safe_title}</span>
    </div>
    <div class="actions">
      <a href="./{safe_file}" download class="btn-dl">Download</a>
      <a href="./{safe_file}" target="_blank" rel="noopener noreferrer" class="btn-raw">Open Raw</a>
    </div>
  </header>
  {content_view}
</body>
</html>"""


def ensure_viewer_wrapper_for_payload(
    files: dict[str, PublishFile],
    title: str | None = None,
) -> dict[str, PublishFile]:
    """Ensure deployable files contain an index.html, wrapping standalone documents if needed."""
    if not files or "index.html" in files:
        return files

    root_html_entries = [name for name in files if "/" not in name and name.lower().endswith((".html", ".htm"))]
    if len(root_html_entries) == 1:
        return ensure_index_html_alias(files)

    if not can_scaffold_viewer(files):
        return files

    root_entries = [name for name in files if "/" not in name]
    doc_entries = [name for name in root_entries if Path(name).suffix.lower() in STANDALONE_VIEWER_EXTENSIONS]
    primary_name = doc_entries[0] if doc_entries else root_entries[0]

    viewer_html = render_standalone_viewer_html(primary_name, title=title)
    res = dict(files)
    res["index.html"] = PublishFile(
        path="index.html",
        content=viewer_html,
        encoding="utf-8",
    )
    return res
