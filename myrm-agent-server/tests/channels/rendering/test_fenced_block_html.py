"""A fenced block becomes one ``<pre>`` in Telegram and in Matrix, and what was set aside as code never leaks.

The info string after the opening backticks is free text (``c++``, ``python title=demo``); only its first word names the
language. A block fenced by four backticks or more shows the three-backtick blocks it documents. A block that was not
recognised came out as an inline code span with stray backticks and the language as its first line, and a protected block
inside a span, a link target or a table cell left its placeholder in the message.
"""

from __future__ import annotations

import itertools
import random
import time
from collections.abc import Callable

import pytest

from app.channels.providers.matrix.html import md_to_matrix_html
from app.channels.providers.telegram.html_converter import md_to_telegram_html


def _matrix(text: str) -> str:
    """What a Matrix client shows: the formatted body, or the text itself when nothing in it needs formatting."""
    return md_to_matrix_html(text) or text


@pytest.fixture(params=[md_to_telegram_html, _matrix], ids=["telegram", "matrix"])
def convert(request: pytest.FixtureRequest) -> Callable[[str], str]:
    converter: Callable[[str], str] = request.param
    return converter


def _block(language: str, code: str) -> str:
    return f'<pre><code class="language-{language}">{code}</code></pre>' if language else f"<pre>{code}</pre>"


class TestInfoString:
    @pytest.mark.parametrize(
        ("info", "language"),
        [
            ("", ""),
            ("   ", ""),
            ("python", "python"),
            ("  python  ", "python"),
            ("c++", "c++"),
            ("c#", "c#"),
            ("objective-c", "objective-c"),
            ("python title=demo", "python"),
            ("json {1,3}", "json"),
            ("代码", "代码"),
        ],
    )
    def test_the_first_word_names_the_language(self, convert: Callable[[str], str], info: str, language: str) -> None:
        assert convert(f"```{info}\nx = 1\n```") == _block(language, "x = 1\n")

    def test_the_language_cannot_leave_the_class_attribute(self, convert: Callable[[str], str]) -> None:
        assert convert('```"onload=x<\nx\n```') == _block("&quot;onload=x&lt;", "x\n")

    def test_the_code_is_escaped_and_never_formatted(self, convert: Callable[[str], str]) -> None:
        converted = convert("```c++\nif (a < b && *p) { /* **not bold** `tick` */ }\n```")
        assert converted == _block("c++", "if (a &lt; b &amp;&amp; *p) { /* **not bold** `tick` */ }\n")

    def test_every_block_of_a_reply_keeps_its_own_language(self, convert: Callable[[str], str]) -> None:
        text = "First:\n```c++\nint a;\n```\nthen\n```python title=demo\nb = 1\n```\nand\n```\nplain\n```\nend"
        blocks = [_block("c++", "int a;\n"), _block("python", "b = 1\n"), _block("", "plain\n")]
        assert convert(text) == f"First:\n{blocks[0]}\nthen\n{blocks[1]}\nand\n{blocks[2]}\nend"


class TestWhereABlockStarts:
    def test_an_indented_fence_in_a_list_item_is_a_block(self, convert: Callable[[str], str]) -> None:
        converted = convert("1. Install:\n   ```c#\n   var x = 1;\n   ```\n2. Run")
        assert _block("c#", "   var x = 1;\n   ") in converted
        assert "```" not in converted

    def test_prose_that_mentions_backticks_does_not_open_a_block(self, convert: Callable[[str], str]) -> None:
        converted = convert("Wrap code in ``` fences like this:\n\n```python\nprint(1)\n```\n")
        assert converted == f"Wrap code in ``` fences like this:\n\n{_block('python', 'print(1)\n')}\n"

    def test_an_inline_span_of_triple_backticks_at_the_start_of_a_line_does_not_open_a_block(
        self, convert: Callable[[str], str]
    ) -> None:
        converted = convert("```code``` marks a span in some chats.\n\n```python\nprint(1)\n```\n")
        assert converted.count("<pre") == 1
        assert _block("python", "print(1)\n") in converted

    def test_a_fence_that_follows_text_still_opens_a_block_when_it_carries_a_word(self, convert: Callable[[str], str]) -> None:
        assert convert("Result:```json\n{}\n```") == f"Result:{_block('json', '{}\n')}"

    @pytest.mark.parametrize("fence", ["```", "````", "``````````"])
    @pytest.mark.parametrize("info", ["", "c++", "python title=demo"])
    def test_a_block_without_a_closing_fence_is_left_as_text(self, convert: Callable[[str], str], fence: str, info: str) -> None:
        assert "<pre>" not in convert(f"{fence}{info}\nint x;\n")


class TestLongerFences:
    """A block ends at the run of backticks that opened it, so a longer fence can show the shorter ones."""

    def test_four_backticks_fence_a_block(self, convert: Callable[[str], str]) -> None:
        assert convert("````python\nx = 1\n````") == _block("python", "x = 1\n")

    def test_the_blocks_a_longer_fence_documents_stay_code(self, convert: Callable[[str], str]) -> None:
        documented = "```bash\nnpm install\n```\n"
        converted = convert(f"Example of the syntax:\n\n````markdown\n{documented}````\n\nThat is all.")
        assert converted == f"Example of the syntax:\n\n{_block('markdown', documented)}\n\nThat is all."

    def test_a_shorter_run_does_not_close_the_block(self, convert: Callable[[str], str]) -> None:
        assert convert("````\nx\n```\ny\n````") == _block("", "x\n```\ny\n")

    def test_five_backticks_show_a_block_of_four(self, convert: Callable[[str], str]) -> None:
        assert convert("`````md\n````py\nx\n````\n`````") == _block("md", "````py\nx\n````\n")

    def test_an_indented_long_fence_in_a_list_item_is_a_block(self, convert: Callable[[str], str]) -> None:
        converted = convert("- item\n\n    ````sh\n    ls\n    ````\n- next")
        assert _block("sh", "    ls\n    ") in converted
        assert "`" not in converted

    def test_blocks_of_different_fence_lengths_side_by_side(self, convert: Callable[[str], str]) -> None:
        text = "```a\n1\n```\n\n````b\n```\n2\n```\n````\n\n```c\n3\n```"
        expected = [_block("a", "1\n"), _block("b", "```\n2\n```\n"), _block("c", "3\n")]
        assert convert(text) == "\n\n".join(expected)

    def test_a_degenerate_line_of_backticks_is_converted_in_linear_time(self, convert: Callable[[str], str]) -> None:
        # Tried at every offset, a run of thousands of backticks takes seconds; as a few windows it takes milliseconds.
        started = time.perf_counter()
        convert("`" * 32_000 + "a\n" + "x" * 32_000)
        assert time.perf_counter() - started < 2.0


# Pieces of markdown that each hold a different way to set something aside (blocks of every length, spans, link targets,
# table cells, stray backticks, fences that never close) for the exhaustive no-leak check.
_FRAGMENTS = (
    "Use `npm install` now.",
    "**bold `x` bold**",
    "[`code`](http://x.y)",
    "[docs](`http://x.y`)",
    "Use ` here:",
    "and ` there.",
    "```python\nx = 1\n```",
    "```\nplain\n```",
    "````markdown\n```bash\nnpm install\n```\n````",
    "`````md\n````py\nx\n````\n`````",
    "| a | b |\n|---|---|\n| x | y |",
    "| a | b |\n|---|---|\n| `x` | y |",
    "| `a` | b |\n|---|---|\n| `x|y` | z |",
    "see ```py\nx\n``` here",
    "```py\nx = 1",
    "````py\nx = 1",
)


class TestSetAsideMarkup:
    """Code that was set aside is put back whole: never inside a span, a link target or another block."""

    def test_backticks_on_both_sides_of_a_block_do_not_wrap_it_in_a_span(self, convert: Callable[[str], str]) -> None:
        converted = convert("Use ` here:\n\n```py\nx\n```\n\nand ` there.")
        assert converted == f"Use ` here:\n\n{_block('py', 'x\n')}\n\nand ` there."

    def test_a_span_that_crosses_no_block_is_still_code(self, convert: Callable[[str], str]) -> None:
        assert convert("`a` and `b`") == "<code>a</code> and <code>b</code>"

    def test_a_link_to_inline_code_is_text_not_a_link(self, convert: Callable[[str], str]) -> None:
        assert convert("[docs](`http://x.y`)") == "[docs](<code>http://x.y</code>)"

    def test_a_link_whose_text_is_inline_code_is_a_link(self, convert: Callable[[str], str]) -> None:
        assert convert("[`code`](http://x.y)") == '<a href="http://x.y"><code>code</code></a>'

    @pytest.mark.parametrize("size", [1, 2, 3])
    def test_no_placeholder_survives_in_any_small_document(self, convert: Callable[[str], str], size: int) -> None:
        for combination in itertools.product(_FRAGMENTS, repeat=size):
            document = "\n\n".join(combination)
            assert "\x00" not in convert(document), document


_WORDS = ("alpha", "beta", "gamma", "delta", "omega")
_INFOS = ("", "py", "c++", "python title=demo", "json {1,3}")
_CODE_LINES = ("x = 1", "if (a < b && *p) {}", "**not bold** ~~nor struck~~ [a](b)", "    indented", "", "`tick` and ``pair``")


def _escape(code: str) -> str:
    return code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _code(rng: random.Random, fence_length: int) -> str:
    """Lines of code; inside a block of four backticks or more they include well-formed blocks of shorter fences."""
    lines: list[str] = []
    for _ in range(rng.randint(0, 4)):
        if fence_length > 3 and rng.random() < 0.4:
            inner = "`" * rng.randint(3, fence_length - 1)
            lines.append(f"{inner}{rng.choice(_INFOS)}\n{rng.choice(_CODE_LINES)}\n{inner}\n")
        else:
            lines.append(f"{rng.choice(_CODE_LINES)}\n")
    return "".join(lines)


def _block_piece(rng: random.Random) -> tuple[str, str]:
    """A fenced block (markdown, HTML) of a random fence length, info string, indentation and content."""
    fence_length = rng.choice((3, 3, 4, 5, 6, 10))
    fence = "`" * fence_length
    info = rng.choice(_INFOS)
    code = _code(rng, fence_length) + rng.choice(("", "", "  "))
    language = (info.split() or [""])[0]
    return f"{rng.choice(('', '', '   '))}{fence}{info}\n{code}{fence}", _block(language, _escape(code))


def _prose_piece(rng: random.Random) -> tuple[str, str]:
    text = " ".join(rng.choices(_WORDS, k=rng.randint(1, 5)))
    return text, text


def _inline_piece(rng: random.Random) -> tuple[str, str]:
    word = rng.choice(_WORDS)
    return f"`{word}`", f"<code>{word}</code>"


def _document(rng: random.Random) -> tuple[str, str]:
    """A markdown document and the HTML both converters must give for it."""
    if rng.random() < 0.3:
        # A stray backtick on each side of the blocks: both stay text, neither wraps the blocks in a span.
        pieces = [_prose_piece(rng) for _ in range(rng.randint(0, 2))]
        pieces.append(("Use ` here:", "Use ` here:"))
        pieces.extend(_block_piece(rng) for _ in range(rng.randint(1, 3)))
        pieces.append(("and ` there.", "and ` there."))
        pieces.extend(_prose_piece(rng) for _ in range(rng.randint(0, 2)))
    else:
        pieces = [rng.choice((_prose_piece, _inline_piece, _block_piece, _block_piece))(rng) for _ in range(rng.randint(1, 6))]
    return "\n\n".join(markdown for markdown, _ in pieces), "\n\n".join(html for _, html in pieces)


class TestRandomDocuments:
    def test_every_block_comes_out_as_one_pre_with_its_own_code(self, convert: Callable[[str], str]) -> None:
        for seed in range(2000):
            markdown, expected = _document(random.Random(seed))
            assert convert(markdown) == expected, f"seed {seed}: {markdown!r}"
