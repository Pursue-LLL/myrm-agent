"""A fenced block becomes one ``<pre>`` in Telegram and in Matrix, whatever its info string says.

The info string after the opening backticks is free text (``c++``, ``python title=demo``); only its first word names the
language. A block that was not recognised came out as an inline code span with stray backticks and the language as its
first line.
"""

from __future__ import annotations

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

    @pytest.mark.parametrize("info", ["", "c++", "python title=demo"])
    def test_a_block_without_a_closing_fence_is_left_as_text(self, convert: Callable[[str], str], info: str) -> None:
        assert "<pre>" not in convert(f"```{info}\nint x;\n")
