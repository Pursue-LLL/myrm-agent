"""Slicing a long card text keeps every chunk a self-contained document: code blocks closed, table headers repeated."""

from __future__ import annotations

import random

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


def _lines(chunks: list[str]) -> list[str]:
    return [line for chunk in chunks for line in chunk.split("\n")]


def _fences(chunk: str) -> list[str]:
    return [line for line in chunk.split("\n") if line.strip().startswith("```")]


def _table_runs(chunk: str) -> list[list[str]]:
    """The runs of consecutive table rows of ``chunk`` that sit outside code blocks."""
    runs: list[list[str]] = []
    in_fence = False
    previous_was_row = False
    for line in chunk.split("\n"):
        if line.strip().startswith("```"):
            in_fence, previous_was_row = not in_fence, False
        elif not in_fence and is_table_row(line):
            if previous_was_row:
                runs[-1].append(line)
            else:
                runs.append([line])
            previous_was_row = True
        else:
            previous_was_row = False
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


def test_the_budget_is_inclusive_and_counted_in_bytes() -> None:
    text = "你好世界\n你好世界"  # 12 + 1 + 12 bytes

    assert slice_card_markdown(text, max_bytes=25) == [text]
    assert slice_card_markdown(text, max_bytes=24) == ["你好世界", "你好世界"]


def test_the_default_budget_leaves_room_for_the_card_envelope() -> None:
    assert DEFAULT_MAX_CARD_BYTES == 24_000
    chunks = slice_card_markdown("\n".join("x" * 99 for _ in range(1000)))

    assert len(chunks) > 1
    assert all(len(chunk.encode()) <= DEFAULT_MAX_CARD_BYTES for chunk in chunks)


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
    assert all(len(_fences(chunk)) % 2 == 0 for chunk in chunks)
    continuing = [chunk for chunk in chunks[1:] if chunk.startswith("```python\nprint(")]
    assert continuing, "a continuation chunk must reopen the block with its language"


@pytest.mark.parametrize("max_bytes", range(10, 80))
def test_no_boundary_leaves_a_fence_unbalanced_or_an_empty_block(max_bytes: int) -> None:
    """The sweep puts a boundary at every line: before an opening fence, inside a block and before a closing fence."""
    chunks = slice_card_markdown(_PROSE_DOC, max_bytes=max_bytes)

    assert all(len(_fences(chunk)) % 2 == 0 for chunk in chunks), chunks
    assert [line for line in _lines(chunks) if line.startswith(("para", "print", "tail"))] == [
        "para one line",
        "para two line",
        "print(1)",
        "print(2)",
        "tail",
    ]
    for chunk in chunks:
        lines = chunk.split("\n")
        assert not (len(lines) == 2 and all(line.startswith("```") for line in lines)), f"empty block in {chunks}"


@pytest.mark.parametrize("max_bytes", range(10, 90))
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
    assert all(len(_fences(chunk)) % 2 == 0 for chunk in chunks)
    assert all(chunk.startswith("```text") for chunk in chunks)


def test_a_block_left_open_by_the_text_is_closed_in_the_last_chunk() -> None:
    chunks = slice_card_markdown("\n".join(["```python", *(f"x = {i}" for i in range(30))]), max_bytes=100)

    assert len(chunks) > 1
    assert all(len(_fences(chunk)) % 2 == 0 for chunk in chunks)
    assert chunks[-1].endswith("\n```")


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
        kind = rng.choice(("prose", "code", "table"))
        if kind == "table":
            headers[f"| row {block}."] = f"| H{block} | x |"
            lines += [f"| H{block} | x |", "|---|---|"]
        elif kind == "code":
            lines.append(f"```{rng.choice(['', 'python', 'json'])}")
        for n in range(rng.randint(1, 8)):
            line = {
                "prose": f"prose {block}.{n} {'w' * rng.randint(0, 25)}",
                "code": f"code {block}.{n} {'c' * rng.randint(0, 25)}",
                "table": f"| row {block}.{n} | {'v' * rng.randint(0, 15)} |",
            }[kind]
            lines.append(line)
            body.append(line)
        if kind == "code":
            lines.append("```")
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
        assert len(chunk.encode()) <= max_bytes
        assert len(_fences(chunk)) % 2 == 0
        for run in _table_runs(chunk):
            data_rows = [line for line in run if line.startswith("| row")]
            if data_rows:
                table_header = next(header for prefix, header in headers.items() if data_rows[0].startswith(prefix))
                assert run[:2] == [table_header, _SEPARATOR]
