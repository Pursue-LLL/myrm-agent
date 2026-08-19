#!/usr/bin/env python3
"""Convert Markdown to WeChat Official Account styled HTML (preview document + draft-ready body content)."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

_BLOCK_INLINE_STYLES: dict[str, str] = {
    "h1": (
        "font-size: 22px; font-weight: 700; line-height: 1.4; margin: 28px 0 16px; "
        "color: #1a1a1a; text-align: center;"
    ),
    "h2": (
        "font-size: 18px; font-weight: 700; line-height: 1.4; margin: 24px 0 12px; "
        "color: #1a1a1a; border-left: 4px solid #07c160; padding-left: 12px;"
    ),
    "h3": (
        "font-size: 16px; font-weight: 600; line-height: 1.4; margin: 18px 0 8px; "
        "color: #2a2a2a;"
    ),
    "p": "margin: 12px 0; text-align: justify;",
    "blockquote": (
        "margin: 16px 0; padding: 10px 14px; background: #f6f6f6; "
        "border-left: 4px solid #d9d9d9; color: #666;"
    ),
    "pre": (
        "background: #282c34; color: #abb2bf; padding: 14px; border-radius: 8px; "
        "overflow-x: auto; margin: 16px 0; line-height: 1.5;"
    ),
    "table": "width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 14px;",
    "th": (
        "border: 1px solid #e5e5e5; padding: 8px 12px; text-align: left; "
        "background: #f7f7f7; font-weight: 600; color: #1a1a1a;"
    ),
    "td": "border: 1px solid #e5e5e5; padding: 8px 12px; text-align: left;",
    "img": (
        "max-width: 100%; height: auto; display: block; margin: 16px auto; border-radius: 6px;"
    ),
}

_WECHAT_BASE_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-size: 16px;
  line-height: 1.75;
  color: #3f3f3f;
  word-wrap: break-word;
}
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 14px;
}
pre code { background: transparent; color: inherit; padding: 0; }
.highlight {
  margin: 16px 0;
  border-radius: 8px;
  overflow-x: auto;
  background: #282c34;
}
.highlight pre {
  margin: 0;
  padding: 14px;
  background: transparent;
}
.highlight .k { color: #c678dd; font-weight: 600; }
.highlight .kn { color: #c678dd; font-weight: 600; }
.highlight .nf { color: #61afef; }
.highlight .nc { color: #e5c07b; }
.highlight .s, .highlight .s1, .highlight .s2 { color: #98c379; }
.highlight .mi, .highlight .mf { color: #d19a66; }
.highlight .c, .highlight .c1, .highlight .cm { color: #5c6370; font-style: italic; }
.highlight .o { color: #abb2bf; }
.highlight .nb { color: #e06c75; }
ul, ol { margin: 12px 0; padding-left: 24px; }
li { margin: 6px 0; }
tr:nth-child(even) td { background: #fafafa; }
a { color: #576b95; text-decoration: none; border-bottom: 1px solid rgba(87, 107, 149, 0.35); }
hr { border: none; border-top: 1px solid #e5e5e5; margin: 24px 0; }
strong { font-weight: 700; color: #1a1a1a; }
em { font-style: italic; color: #555; }
""".strip()


def _css_rules_from_block_inline_styles() -> str:
    return "\n".join(f"{tag} {{ {style} }}" for tag, style in _BLOCK_INLINE_STYLES.items())


def _build_wechat_css() -> str:
    return f"{_WECHAT_BASE_CSS}\n{_css_rules_from_block_inline_styles()}"


_WECHAT_CSS = _build_wechat_css()


def _merge_style_attr(existing: str, block_style: str) -> str:
    trimmed = existing.strip().rstrip(";")
    if not trimmed:
        return block_style
    return f"{trimmed}; {block_style}"


def _inject_block_inline_styles(html: str) -> str:
    for tag, block_style in _BLOCK_INLINE_STYLES.items():
        pattern = re.compile(rf"<{tag}\b(?P<attrs>[^>]*)>", re.IGNORECASE)

        def repl(match: re.Match[str], *, style: str = block_style, tag_name: str = tag) -> str:
            attrs = match.group("attrs") or ""
            style_match = re.search(r'\bstyle=(["\'])(.*?)\1', attrs, re.IGNORECASE)
            if style_match:
                merged = _merge_style_attr(style_match.group(2), style)
                new_attrs = (
                    f'{attrs[: style_match.start()]}style="{merged}"{attrs[style_match.end() :]}'
                )
            else:
                if attrs:
                    new_attrs = f'{attrs} style="{style}"'
                else:
                    new_attrs = f' style="{style}"'
            return f"<{tag_name}{new_attrs}>"

        html = pattern.sub(repl, html)
    return html


def _ensure_markdown() -> bool:
    try:
        import markdown  # noqa: F401
        return True
    except ImportError:
        return False


def _convert_with_markdown(text: str) -> str:
    import markdown

    return markdown.markdown(
        text,
        extensions=["fenced_code", "codehilite", "tables", "nl2br", "sane_lists"],
        extension_configs={
            "codehilite": {
                "css_class": "highlight",
                "linenos": False,
                "guess_lang": True,
                "pygments_style": "monokai",
                "noclasses": True,
            }
        },
        output_format="html5",
    )


def _convert_basic(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_code = False
    code_lines: list[str] = []
    list_items: list[str] = []

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            body = html.escape("\n".join(code_lines))
            out.append(f"<pre><code>{body}</code></pre>")
            code_lines = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            items = "".join(f"<li>{html.escape(item)}</li>" for item in list_items)
            out.append(f"<ul>{items}</ul>")
            list_items = []

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            flush_list()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if line.startswith("- ") or line.startswith("* "):
            list_items.append(line[2:].strip())
            continue
        flush_list()
        if not line.strip():
            out.append("")
            continue
        if line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            out.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.startswith("> "):
            out.append(f"<blockquote><p>{html.escape(line[2:].strip())}</p></blockquote>")
        else:
            out.append(f"<p>{html.escape(line.strip())}</p>")

    flush_list()
    if in_code:
        flush_code()
    return "\n".join(out)


def _rewrite_relative_images(body_html: str, base_dir: Path) -> str:
    def repl(match: re.Match[str]) -> str:
        prefix, src, suffix = match.group(1), match.group(2), match.group(3)
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)
        resolved = (base_dir / src).resolve()
        return f"{prefix}{resolved.as_posix()}{suffix}"

    return re.sub(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'][^>]*>)', repl, body_html, flags=re.IGNORECASE)


def convert_markdown_to_wechat_html(source: Path, output: Path) -> None:
    text = source.read_text(encoding="utf-8")
    if _ensure_markdown():
        try:
            body = _convert_with_markdown(text)
        except Exception:
            body = _convert_basic(text)
    else:
        print(
            "WARNING: markdown/pygments not installed; using basic converter. "
            "Install: uv sync --extra wechat-formatter",
            file=sys.stderr,
        )
        body = _convert_basic(text)

    body = _inject_block_inline_styles(body)
    body = _rewrite_relative_images(body, source.parent)
    doc = (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        f"<style>{_WECHAT_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(doc, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Markdown to WeChat article HTML")
    parser.add_argument("input", type=Path, help="Source Markdown file")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output HTML file")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    convert_markdown_to_wechat_html(args.input, args.output)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
