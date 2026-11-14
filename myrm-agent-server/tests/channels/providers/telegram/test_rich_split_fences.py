"""Telegram's Rich Message splitter never cuts a code block that fits in a part, and fences the pieces of one that does not.

Fences are read as the router splitter reads them: backticks or tildes, any length, nested blocks held by the longer
fence. The sweep at the end judges random documents with a small CommonMark reader that shares nothing with the code.
"""

import random
import re

import pytest

from app.channels.providers.telegram.html_converter import split_markdown_rich

pytestmark = pytest.mark.timeout(30)

PROSE_60 = "p" * 60


def _split(text: str, limit: int) -> list[str]:
    parts = split_markdown_rich(text, limit=limit)
    assert all(len(part.encode("utf-8")) <= limit for part in parts), parts
    return parts


def test_a_nested_block_straddling_the_cut_moves_whole():
    inner = "```python\nprint(1)\n```\n"
    block = "````markdown\n" + inner * 2 + "````"
    assert _split(PROSE_60 + "\n" + block, 100) == [PROSE_60 + "\n", block]


def test_a_tilde_block_straddling_the_cut_moves_whole():
    block = "~~~js\n" + "code line\n" * 5 + "~~~"
    assert _split(PROSE_60 + "\n" + block, 90) == [PROSE_60 + "\n", block]


def test_triple_backticks_inside_a_line_never_move_the_cut():
    line = "a ```x``` b\n"
    assert _split(line * 10, 50) == [line * 4, line * 4, line * 2]


def test_a_block_that_starts_the_part_and_fits_is_kept_whole_though_a_blank_line_inside_it_is_the_better_break():
    block = "```\naaa\n\nbbb\n```"
    assert _split(block + "\n" + "t" * 100, 40) == [block, "t" * 40, "t" * 40, "t" * 20]


def test_a_block_exactly_as_big_as_a_part_is_kept_whole():
    block = "```\naaa\n\nbbb\n```"
    size = len(block)
    assert _split(block + "\n" + "t" * 100, size)[0] == block
    assert _split(block + "\n" + "t" * 100, size - 1)[0] != block


@pytest.mark.parametrize("blank", ["\n", "\n  \n", "   \n\t\n"], ids=["one-newline", "blank-lines", "spaces-and-tabs"])
def test_blank_lines_ahead_of_a_block_are_dropped_when_the_block_has_to_start_the_part(blank):
    block = "```\naaa\n\nbbb\n```"
    assert _split(blank + block + "\n" + "t" * 100, 40) == [block, "t" * 40, "t" * 40, "t" * 20]


def test_a_block_bigger_than_a_part_goes_out_in_fenced_pieces():
    text = "```python\n" + "x = 1\n" * 40 + "```\nafter"
    parts = _split(text, 100)
    assert parts[-1] == "after"
    assert len(parts) > 3
    for piece in parts[:-1]:
        assert piece.startswith("```python\n") and piece.endswith("\n```"), piece
    assert "".join(parts[:-1]).count("x = 1") == 40


def test_an_unclosed_block_bigger_than_a_part_goes_out_in_fenced_pieces_after_the_text_before_it():
    text = "intro\n```\n" + "line\n" * 50
    parts = _split(text, 80)
    assert parts[0] == "intro\n"
    assert len(parts) > 2
    for piece in parts[1:]:
        assert piece.startswith("```\n") and piece.endswith("\n```"), piece
    assert "".join(parts[1:]).count("line") == 50


def test_the_text_after_a_block_bigger_than_a_part_is_read_from_the_end_of_that_block():
    big = "```python\n" + "x = 1\n" * 40 + "```"
    block = "```\n" + "a" * 20 + "\n" + "a" * 20 + "\n```"
    parts = _split(big + "\n" + PROSE_60 + "\n" + block, 100)
    assert parts[-2:] == [PROSE_60 + "\n", block]


# --- random documents, against an independent reader --------------------------------------------------------------

_FENCE_LINE = re.compile(r"^[ \t]*(`{3,10}|~{3,10})([^`]*)$")
_PROSE = ("Plain line.", "中文内容，很长很长的一行。", "Emoji \U0001f600 line", "word " * 8, "", "A sentence. Another one! Fine?")
_INFOS = ("", "python", "c++", "json {1,3}", "代码")
_CODE = ("x = 1", "print('hi')", "中文代码", "")


def _open_block(text: str) -> bool:
    """Whether ``text`` ends inside a code block, read the CommonMark way."""
    opener = ""
    for line in text.split("\n"):
        fence = _FENCE_LINE.match(line)
        if fence and not opener:
            opener = fence.group(1)
        elif fence and not fence.group(2).strip() and fence.group(1)[0] == opener[0] and len(fence.group(1)) >= len(opener):
            opener = ""
    return bool(opener)


def _words(text: str) -> str:
    """What a reader sees of ``text``: its lines without fence lines, newlines left out."""
    return re.sub(r"\n+", "", "".join(line for line in text.split("\n") if not _FENCE_LINE.match(line)))


def _block(rng: random.Random) -> list[str]:
    code = [rng.choice(_CODE) if rng.random() < 0.7 else "y" * rng.randint(1, 40) for _ in range(rng.randint(1, 8))]
    kind = rng.choice(("plain", "plain", "tilde", "nested"))
    if kind == "plain":
        return ["```" + rng.choice(_INFOS), *code, "```"]
    if kind == "tilde":
        return ["~~~" + rng.choice(_INFOS), *code, "~~~"]
    inner = ["```" + rng.choice(_INFOS), *code, "```"]
    return ["````" + rng.choice(("markdown", "")), *inner, *inner, "````"]


def _document(rng: random.Random) -> str:
    lines: list[str] = []
    for _ in range(rng.randint(3, 14)):
        if rng.random() < 0.35:
            lines.append(rng.choice(_PROSE))
        else:
            lines.extend(_block(rng))
        if rng.random() < 0.08:
            lines.append("inline ```x``` triple backticks mid-line")
    if rng.random() < 0.1:
        lines.extend(["```python", "unclosed tail"])
    return "\n".join(lines)


def _biggest_block(text: str) -> int:
    """The UTF-8 size of the biggest code block in ``text``, one that is never closed running to the end."""
    biggest = 0
    start = -1
    opener = ""
    offset = 0
    for line in text.split("\n"):
        end = offset + len(line)
        fence = _FENCE_LINE.match(line)
        if fence and start < 0:
            start, opener = offset, fence.group(1)
        elif fence and not fence.group(2).strip() and fence.group(1)[0] == opener[0] and len(fence.group(1)) >= len(opener):
            biggest = max(biggest, len(text[start:end].encode("utf-8")))
            start = -1
        offset = end + 1
    return max(biggest, len(text[start:].encode("utf-8")) if start >= 0 else 0)


@pytest.mark.parametrize("fits", [True, False], ids=["every-block-fits-a-part", "blocks-may-outgrow-a-part"])
def test_random_documents_split_into_parts_that_hold_their_blocks_whole(fits):
    problems: list[str] = []
    split_documents = 0
    for seed in range(400):
        rng = random.Random(seed)
        text = _document(rng)
        limit = max(40, _biggest_block(text)) + rng.choice((0, 5, 20, 60)) if fits else rng.choice((40, 60, 80, 120, 200))
        parts = split_markdown_rich(text, limit=limit)
        split_documents += len(parts) > 1
        if any(len(part.encode("utf-8")) > limit for part in parts):
            problems.append(f"{seed}: a part is over the limit")
        elif _words(text) != _words("\n".join(parts)):
            problems.append(f"{seed}: text lost or reordered")
        elif any(_open_block(part) for part in parts[:-1]) or (_open_block(parts[-1]) and not _open_block(text)):
            problems.append(f"{seed}: a part ends inside a block")
    assert not problems, problems[:5]
    assert split_documents > 300, "the sweep must reach the splitter"
