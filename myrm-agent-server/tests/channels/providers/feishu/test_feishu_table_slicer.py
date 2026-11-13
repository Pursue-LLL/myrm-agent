"""Slicing a long card text keeps every chunk a self-contained document: code blocks closed, table headers repeated."""

from __future__ import annotations

import json
import random
import re

import pytest

from app.channels.providers.feishu.table_slicer import (
    DEFAULT_MAX_CARD_BYTES,
    is_table_row,
    is_table_separator,
    slice_card_markdown,
)

_HEADER = "| Col A | Col B |"
_SEPARATOR = "|---|---|"
_PROSE_DOC = "para one line\npara two line\n```python\nprint(1)\nprint(2)\n```\ntail"
_TABLE_DOC = "\n".join([_HEADER, _SEPARATOR, *(f"| r{i} | v{i} |" for i in range(6)), "after"])
_FENCE = re.compile(r"^(`{3,})([^`]*)$")


def _lines(chunks: list[str]) -> list[str]:
    return [line for chunk in chunks for line in chunk.split("\n")]


def _request_bytes(text: str) -> int:
    """What ``text`` adds to the request body of a card message: escaped into the card JSON, then into the request."""

    def body(content: str) -> int:
        card = json.dumps({"markdown": content}, ensure_ascii=False, separators=(",", ":"))
        return len(json.dumps({"content": card}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    return body(text) - body("")


def _scan(chunk: str) -> tuple[list[str], bool]:
    """The lines of ``chunk`` outside its code blocks (a block leaves one blank line) and whether it ends inside one.

    A block closes on a bare run of backticks at least as long as the run that opened it (CommonMark).
    """
    outside: list[str] = []
    opener = 0
    for line in chunk.split("\n"):
        fence = _FENCE.match(line.strip())
        if opener:
            if fence and not fence.group(2).strip() and len(fence.group(1)) >= opener:
                opener = 0
        elif fence:
            opener = len(fence.group(1))
            outside.append("")
        else:
            outside.append(line)
    return outside, bool(opener)


def _left_open(chunk: str) -> bool:
    return _scan(chunk)[1]


def _table_runs(chunk: str) -> list[list[str]]:
    """The runs of consecutive table rows of ``chunk`` that sit outside code blocks."""
    runs: list[list[str]] = []
    previous_was_row = False
    for line in _scan(chunk)[0]:
        if is_table_row(line):
            if previous_was_row:
                runs[-1].append(line)
            else:
                runs.append([line])
        previous_was_row = is_table_row(line)
    return runs


def test_table_row_and_separator_detection() -> None:
    assert is_table_row("| Name | Value |") is True
    assert is_table_row("  | a | b | c |  ") is True
    assert is_table_row("Normal text without pipe") is False

    assert is_table_separator("|---|---|") is True
    assert is_table_separator("| :--- | :---: | ---: |") is True
    assert is_table_separator("| Name | Value |") is False


@pytest.mark.parametrize("text", ["", "short", "# Title\n\n| a | b |\n|---|---|\n| 1 | 2 |"])
def test_text_within_the_budget_comes_back_whole(text: str) -> None:
    assert slice_card_markdown(text) == [text]


def test_the_budget_is_inclusive_and_counted_in_bytes_of_the_request() -> None:
    text = "你好世界\n你好世界"  # 12 bytes, a newline of 3 bytes once escaped twice, 12 bytes

    assert _request_bytes(text) == 27
    assert slice_card_markdown(text, max_bytes=27) == [text]
    assert slice_card_markdown(text, max_bytes=26) == ["你好世界", "你好世界"]


@pytest.mark.parametrize(
    ("char", "request_bytes"),
    [("x", 1), ("é", 2), ("中", 3), ("😀", 4), ('"', 4), ("\\", 4), ("\t", 3), ("\x01", 7)],
    ids=["ascii", "latin", "cjk", "emoji", "quote", "backslash", "tab", "control"],
)
def test_a_character_counts_as_many_bytes_as_it_takes_in_the_request(char: str, request_bytes: int) -> None:
    """The card JSON escapes a quote, a backslash or a control character, and the request escapes the escape."""
    lines = [char * 10] * 3
    text = "\n".join(lines)
    total = 3 * 10 * request_bytes + 2 * 3  # three lines and the two newlines between them

    assert _request_bytes(text) == total
    assert slice_card_markdown(text, max_bytes=total) == [text]
    assert slice_card_markdown(text, max_bytes=total - 1) == ["\n".join(lines[:2]), lines[2]]


def test_the_default_budget_leaves_room_for_the_card_envelope() -> None:
    assert DEFAULT_MAX_CARD_BYTES == 24_000
    chunks = slice_card_markdown("\n".join("x" * 99 for _ in range(1000)))

    assert len(chunks) > 1
    assert all(_request_bytes(chunk) <= DEFAULT_MAX_CARD_BYTES for chunk in chunks)


def test_json_code_is_cut_into_chunks_that_fit_once_it_is_escaped() -> None:
    """Quotes take four bytes each in the request: 24,000 raw bytes of JSON are far over what Feishu accepts."""
    rows = [json.dumps({"id": i, "name": f"item-{i}", "tags": ["a", "b"]}) for i in range(800)]

    text = "```json\n" + "\n".join(rows) + "\n```"

    chunks = slice_card_markdown(text)

    assert len(chunks) > -(-len(text.encode()) // DEFAULT_MAX_CARD_BYTES), "the quotes must cost more chunks than the raw size"
    assert all(_request_bytes(chunk) <= DEFAULT_MAX_CARD_BYTES for chunk in chunks)
    assert [line for line in _lines(chunks) if line.startswith("{")] == rows


def test_slice_card_markdown_with_table_header_duplication() -> None:
    rows = [f"| row {i} cell A | row {i} cell B | row {i} cell C |" for i in range(100)]
    header = "| Col A | Col B | Col C |"
    separator = "|---|---|---|"
    chunks = slice_card_markdown("\n".join([header, separator, *rows]), max_bytes=500)

    assert len(chunks) > 1
    for index, chunk in enumerate(chunks):
        if index > 0 and "| row" in chunk:
            assert chunk.startswith(f"{header}\n{separator}\n"), f"chunk {index} lost the table header: {chunk[:100]}"


def test_a_code_block_cut_by_a_boundary_is_closed_and_reopened_with_its_language() -> None:
    code = [f"print({i})" for i in range(40)]
    chunks = slice_card_markdown("\n".join(["intro", "```python", *code, "```", "outro"]), max_bytes=120)

    assert len(chunks) > 2
    assert [line for line in _lines(chunks) if line.startswith("print(")] == code
    assert not any(_left_open(chunk) for chunk in chunks)
    continuing = [chunk for chunk in chunks[1:] if chunk.startswith("```python\nprint(")]
    assert continuing, "a continuation chunk must reopen the block with its language"


@pytest.mark.parametrize("max_bytes", range(10, 90))
def test_no_boundary_leaves_a_fence_unbalanced_or_an_empty_block(max_bytes: int) -> None:
    """The sweep puts a boundary at every line: before an opening fence, inside a block and before a closing fence."""
    chunks = slice_card_markdown(_PROSE_DOC, max_bytes=max_bytes)

    assert not any(_left_open(chunk) for chunk in chunks), chunks
    assert [line for line in _lines(chunks) if line.startswith(("para", "print", "tail"))] == [
        "para one line",
        "para two line",
        "print(1)",
        "print(2)",
        "tail",
    ]
    for chunk in chunks:
        lines = chunk.split("\n")
        assert not (len(lines) == 2 and all(_FENCE.match(line) for line in lines)), f"empty block in {chunks}"


@pytest.mark.parametrize("max_bytes", range(10, 140))
def test_no_boundary_separates_a_table_header_from_its_separator_or_duplicates_it(max_bytes: int) -> None:
    chunks = slice_card_markdown(_TABLE_DOC, max_bytes=max_bytes)

    assert [line for line in _lines(chunks) if line.startswith("| r")] == [f"| r{i} | v{i} |" for i in range(6)]
    for chunk in chunks:
        assert sum(1 for line in chunk.split("\n") if is_table_separator(line)) <= 1, chunks
        for run in _table_runs(chunk):
            if len(run) > 1 or run[0] != _HEADER:
                assert run[:2] == [_HEADER, _SEPARATOR], f"a table run starts without its header in {chunks}"
            else:
                pytest.fail(f"a header row is left without its separator in {chunks}")


def test_a_table_in_a_code_block_is_not_given_a_repeated_header() -> None:
    code = ["| a | b |", "|---|---|", *(f"| {i} | x |" for i in range(30))]
    chunks = slice_card_markdown("\n".join(["```text", *code, "```"]), max_bytes=100)

    assert len(chunks) > 1
    assert [line for line in _lines(chunks) if line not in ("```text", "```")] == code
    assert not any(_left_open(chunk) for chunk in chunks)
    assert all(chunk.startswith("```text") for chunk in chunks)


def test_a_block_left_open_by_the_text_is_closed_in_the_last_chunk() -> None:
    chunks = slice_card_markdown("\n".join(["```python", *(f"x = {i}" for i in range(30))]), max_bytes=100)

    assert len(chunks) > 1
    assert not any(_left_open(chunk) for chunk in chunks)
    assert chunks[-1].endswith("\n```")


@pytest.mark.parametrize("opening", ["```c++", "```python title=demo", "   ```json"])
def test_a_cut_block_is_reopened_with_the_whole_info_string(opening: str) -> None:
    chunks = slice_card_markdown("\n".join([opening, *(f"line {i}" for i in range(30)), "```"]), max_bytes=100)

    assert len(chunks) > 1
    assert all(chunk.lstrip().startswith(opening.strip()) for chunk in chunks)
    assert not any(_left_open(chunk) for chunk in chunks)


@pytest.mark.parametrize("max_bytes", range(40, 120, 3))
def test_a_block_fenced_with_four_backticks_survives_the_fences_inside_it(max_bytes: int) -> None:
    """The three-backtick lines inside the block are its content: they neither close it nor are closed for it."""
    body = [f"x = {i}" for i in range(12)]
    text = "\n".join(["````markdown", "```python", *body, "```", "````", "tail"])

    chunks = slice_card_markdown(text, max_bytes=max_bytes)

    assert not any(_left_open(chunk) for chunk in chunks), chunks
    assert [line for line in _lines(chunks) if line.startswith("x = ")] == body
    assert _lines(chunks).count("```python") == 1
    assert _lines(chunks).count("```") == 1
    assert chunks[-1].endswith("tail")


@pytest.mark.parametrize("max_bytes", range(30, 110, 4))
def test_backticks_inside_a_line_do_not_make_it_a_fence(max_bytes: int) -> None:
    inline = "```code``` is how a block looks in one line"
    text = "\n".join([inline, "between", "```python", *(f"print({i})" for i in range(8)), "```", "tail"])

    chunks = slice_card_markdown(text, max_bytes=max_bytes)

    assert _lines(chunks).count(inline) == 1
    assert not any(_left_open(chunk) for chunk in chunks), chunks
    assert [line for line in _lines(chunks) if line.startswith("print(")] == [f"print({i})" for i in range(8)]


def test_a_line_over_the_budget_gets_a_chunk_of_its_own_and_is_never_dropped() -> None:
    assert slice_card_markdown("\n".join(["a", "X" * 100, "b"]), max_bytes=20) == ["a", "X" * 100, "b"]


def test_a_table_header_with_a_separator_over_the_budget_is_kept_together() -> None:
    chunks = slice_card_markdown("\n".join(["intro", _HEADER, _SEPARATOR, "| 1 | 2 |"]), max_bytes=10)

    assert chunks == ["intro", f"{_HEADER}\n{_SEPARATOR}", f"{_HEADER}\n{_SEPARATOR}\n| 1 | 2 |"]


def _random_document(rng: random.Random) -> tuple[str, list[str], dict[str, str]]:
    """A document of prose, code blocks and tables; its body lines are unique so a chunk can be traced to them."""
    lines: list[str] = []
    body: list[str] = []
    headers: dict[str, str] = {}
    for block in range(rng.randint(2, 8)):
        kind = rng.choice(("prose", "code", "table", "nested"))
        if kind == "table":
            headers[f"| row {block}."] = f"| H{block} | x |"
            lines += [f"| H{block} | x |", "|---|---|"]
        elif kind == "code":
            lines.append(f"```{rng.choice(['', 'python', 'json'])}")
        elif kind == "nested":
            lines.append("````markdown")
        for n in range(rng.randint(1, 8)):
            quotes = rng.choice(("", '"' * rng.randint(1, 6), "\\" * rng.randint(1, 6)))  # escapes weigh more than they look
            line = {
                "prose": f"prose {block}.{n} {'w' * rng.randint(0, 25)}",
                "code": f"code {block}.{n} {'c' * rng.randint(0, 25)}{quotes}",
                "table": f"| row {block}.{n} | {'v' * rng.randint(0, 15)}{quotes} |",
                "nested": f"code {block}.{n} {'c' * rng.randint(0, 25)}{quotes}",
            }[kind]
            lines.append(line)
            body.append(line)
            if kind == "nested" and rng.random() < 0.3:
                lines.append(f"```python {block}.{n}")  # a block inside the block is only content to the outer one
        if kind in ("code", "nested"):
            lines.append("```" if kind == "code" else "````")
        lines.append("")
    return "\n".join(lines), body, headers


@pytest.mark.parametrize("seed", range(150))
def test_random_documents_slice_without_loss_and_into_self_contained_chunks(seed: int) -> None:
    rng = random.Random(seed)
    text, body, headers = _random_document(rng)
    max_bytes = rng.choice((120, 160, 240, 400))

    chunks = slice_card_markdown(text, max_bytes=max_bytes)

    assert [line for line in _lines(chunks) if line.startswith(("prose", "code ", "| row"))] == body
    assert sum(line == "" for line in _lines(chunks)) == sum(line == "" for line in text.split("\n"))
    for chunk in chunks:
        assert _request_bytes(chunk) <= max_bytes
        assert not _left_open(chunk)
        for run in _table_runs(chunk):
            data_rows = [line for line in run if line.startswith("| row")]
            if data_rows:
                table_header = next(header for prefix, header in headers.items() if data_rows[0].startswith(prefix))
                assert run[:2] == [table_header, _SEPARATOR]
