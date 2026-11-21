"""The one Markdown renderer for pages served to anonymous visitors of a share link.

[INPUT]
- markdown_it::MarkdownIt (POS: CommonMark parser; raw HTML is switched off so it renders as text)

[OUTPUT]
- build_share_markdown: a parser whose ``render`` output is safe to place in a script-free page

[POS]
Server business layer. A share page is served from the application's own origin to people who never logged in, and
the Markdown it shows was written by a model or by a user, so it must never turn into markup the page did not intend:
raw HTML is escaped, and the library's link policy refuses ``javascript:``, ``vbscript:`` and ``file:`` destinations (and
``data:`` ones that are not images). Wide tables are wrapped so they scroll inside the page instead of squeezing every
column. The conversation page (a line break in a message is a line break) and the Markdown artifact page (CommonMark line
handling) share this pipeline and differ only in ``breaks``.
"""

from __future__ import annotations

from collections.abc import Sequence

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict

_TABLE_OPEN = '<div class="table-wrap">'
_TABLE_CLOSE = "</div>"


def _open_table(renderer: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
    return _TABLE_OPEN + renderer.renderToken(tokens, idx, options, env)


def _close_table(renderer: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
    return renderer.renderToken(tokens, idx, options, env) + _TABLE_CLOSE


def build_share_markdown(*, breaks: bool) -> MarkdownIt:
    """A CommonMark parser with tables, raw HTML off, and wide tables wrapped in a scrolling box."""
    parser = MarkdownIt("commonmark", {"breaks": breaks, "html": False}).enable("table")
    parser.add_render_rule("table_open", _open_table)
    parser.add_render_rule("table_close", _close_table)
    return parser
