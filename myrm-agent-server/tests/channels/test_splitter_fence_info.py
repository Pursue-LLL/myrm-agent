"""The router's splitter keeps a code block intact whatever its info string says, and ends a block as CommonMark does.

A chunk is judged by a small CommonMark reader that shares nothing with the splitter: every chunk must end outside a
block, and the prose lines and code lines of all the chunks together must be those of the message.
"""

import random
import re

import pytest

from app.channels.rendering.splitter import split_message

_FENCE_LINE = re.compile(r"^(`{3,}|~{3,})([^`]*)$")
_EMPTY_BLOCK = re.compile(r"^(`{3,}|~{3,})[^`\n]*\n(`{3,}|~{3,})$", re.MULTILINE)

_INFO_STRINGS = [
    "python",
    "c++",
    "c#",
    "objective-c",
    "vb.net",
    "shell-session",
    "python title=demo",
    "json {1,3}",
    "代码",
]


def _read(text: str) -> tuple[list[str], list[str], bool]:
    """The prose lines and the code lines of ``text`` as CommonMark sees them, and whether it ends inside a block."""
    prose: list[str] = []
    code: list[str] = []
    opener = ""
    for line in text.split("\n"):
        fence = _FENCE_LINE.match(line.strip())
        if not opener:
            if fence:
                opener = fence.group(1)
            elif line.strip():
                prose.append(line)
        elif fence and not fence.group(2) and fence.group(1)[0] == opener[0] and len(fence.group(1)) >= len(opener):
            opener = ""
        elif line.strip():
            code.append(line)
    return prose, code, bool(opener)


def _split_intact(text: str, max_len: int) -> list[str]:
    """The chunks of ``text``, after checking each fits, ends outside a block, and that none of the text got lost or moved."""
    chunks = split_message(text, max_len)
    if len(text) <= max_len:
        assert chunks == [text]  # A message that fits goes out as written, even when its own block is left open.
        return chunks
    prose: list[str] = []
    code: list[str] = []
    for chunk in chunks:
        assert len(chunk) <= max_len, f"{max_len=}: {chunk!r}"
        chunk_prose, chunk_code, inside_block = _read(chunk)
        assert not inside_block, f"{max_len=}: a chunk ends inside a block: {chunk!r}"
        prose += chunk_prose
        code += chunk_code
    expected_prose, expected_code, _ = _read(text)
    assert prose == expected_prose, f"{max_len=}"
    assert code == expected_code, f"{max_len=}"
    return chunks


def _code_lines(count: int) -> list[str]:
    return [f"line {index:02d} {'x' * 20}" for index in range(count)]


@pytest.mark.parametrize("info", _INFO_STRINGS)
def test_a_block_is_closed_and_reopened_with_its_info_string_across_chunks(info: str) -> None:
    text = "\n".join(["Intro paragraph.", f"```{info}", *_code_lines(30), "```", "Closing paragraph."])

    for max_len in range(90, 400, 13):
        chunks = _split_intact(text, max_len)

        assert len(chunks) > 1
        for chunk in chunks[1:]:
            if _read(chunk)[1]:
                assert chunk.startswith(f"```{info}\n"), f"{max_len=}: {chunk!r}"


@pytest.mark.parametrize("fence", ["```", "````", "~~~"])
@pytest.mark.parametrize("info", ["c++", "python title=demo"])
def test_a_block_of_any_fence_character_and_length_keeps_its_info_string(fence: str, info: str) -> None:
    text = "\n".join(["Intro paragraph.", f"{fence}{info}", *_code_lines(30), fence, "Closing paragraph."])

    for max_len in range(90, 400, 13):
        _split_intact(text, max_len)


@pytest.mark.parametrize(
    ("opener", "closer"),
    [("```", "````"), ("```", "``````"), ("~~~", "~~~~"), ("````", "`````"), ("```c++", "````")],
)
def test_a_longer_bare_fence_closes_the_block(opener: str, closer: str) -> None:
    after = [f"Afterwards {index:02d} {'y' * 20}" for index in range(10)]
    text = "\n".join(["Intro paragraph.", opener, *_code_lines(20), closer, *after])

    for max_len in range(90, 300, 11):
        _split_intact(text, max_len)


@pytest.mark.parametrize(
    ("opener", "closer", "inside"),
    [
        ("```", "```", "```python"),
        ("```", "```", "```c++"),
        ("```", "```", "~~~"),
        ("~~~", "~~~", "```"),
        ("~~~", "~~~", "~~~bash"),
        ("````", "````", "```"),
        ("````", "````", "~~~~"),
        ("````markdown", "````", "```python"),
    ],
)
def test_a_fence_line_that_cannot_close_the_block_is_code(opener: str, closer: str, inside: str) -> None:
    code = [*_code_lines(8), inside, *_code_lines(8), inside, *_code_lines(8)]
    text = "\n".join(["Intro paragraph.", opener, *code, closer, "Closing paragraph."])

    for max_len in range(90, 400, 13):
        _split_intact(text, max_len)


@pytest.mark.parametrize("info", ["", "c++"])
def test_an_opening_line_with_no_code_under_it_moves_to_the_next_chunk(info: str) -> None:
    text = "\n".join(["Intro paragraph.", "p" * 20, "q" * 35, f"```{info}", *_code_lines(10), "```"])

    for max_len in range(14, 300):
        for chunk in split_message(text, max_len):
            assert len(chunk) <= max_len, f"{max_len=}: {chunk!r}"
            assert not _EMPTY_BLOCK.search(chunk), f"{max_len=}: a chunk holds an opening line and nothing else: {chunk!r}"


@pytest.mark.parametrize("closed", [True, False])
def test_a_code_line_equal_to_the_opening_line_is_code_where_a_chunk_ends(closed: bool) -> None:
    code = [*_code_lines(6), "```python", *_code_lines(6), "```python"]
    text = "\n".join(["```python", *code, *(["```"] if closed else [])])

    for max_len in range(60, 300, 3):
        _split_intact(text, max_len)


def test_a_line_of_backticks_with_backticks_after_it_is_prose() -> None:
    prose = ["``` and ``` are fences in Markdown", *[f"Paragraph {index:02d} {'w' * 25}" for index in range(10)]]
    text = "\n".join(prose)

    for max_len in range(60, 200, 9):
        assert "".join(_split_intact(text, max_len)) == text


def _random_line(rng: random.Random) -> str:
    kind = rng.random()
    if kind < 0.5:
        return f"text {rng.randrange(1000)} {'w' * rng.randrange(1, 25)}"
    if kind < 0.6:
        return ""
    return rng.choice("`~") * rng.randrange(3, 6) + rng.choice(["", "", "", *_INFO_STRINGS])


def test_random_documents_are_split_without_moving_prose_into_code_or_code_into_prose() -> None:
    for seed in range(200):
        rng = random.Random(seed)
        text = "\n".join(_random_line(rng) for _ in range(rng.randrange(20, 70)))

        for max_len in (rng.randrange(70, 120), rng.randrange(120, 260), rng.randrange(260, 600)):
            try:
                _split_intact(text, max_len)
            except AssertionError as error:
                raise AssertionError(f"{seed=}: {error}") from error
