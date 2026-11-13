"""The streaming chunker sees a fenced block whatever its info string says, so a preview waits for the block to close."""

import pytest

from app.channels.routing.block_chunker import BlockChunker, ChunkConfig

_INFO_STRINGS = ["", "python", "c++", "c#", "objective-c", "python title=demo", "json {1,3}", "代码"]
_CODE = "int x = 0;\n" * 30
_PROSE = "Explanation words. " * 32


def _chunker() -> BlockChunker:
    return BlockChunker(ChunkConfig(block_size=100))


@pytest.mark.parametrize("info", _INFO_STRINGS)
@pytest.mark.parametrize("fence", ["```", "````", "    ```"])
def test_a_block_is_open_until_its_closing_fence(info: str, fence: str) -> None:
    chunker = _chunker()
    opened = f"Here is the code:\n{fence}{info}\n{_CODE}"
    closed = f"{opened}{fence}\n"
    after = closed + _PROSE

    assert chunker._is_inside_code_fence(opened)
    assert not chunker.should_emit_block(opened, is_final=False)
    assert not chunker._is_inside_code_fence(closed)
    assert not chunker._is_inside_code_fence(after)
    assert chunker.should_emit_block(after, is_final=False)


@pytest.mark.parametrize("info", _INFO_STRINGS)
def test_a_break_never_lands_inside_a_block(info: str) -> None:
    chunker = _chunker()
    closed = f"Here is the code:\n```{info}\n{_CODE}```\n"
    block_end = closed.rindex("```") + 3

    for max_length in range(len(closed) // 3, block_end):
        point = chunker.find_break_point(closed + _PROSE, max_length)
        assert point == 0 or point >= block_end, f"{max_length=}: {point=}"


def test_a_block_that_closes_with_spaces_after_its_fence_is_closed() -> None:
    assert not _chunker()._is_inside_code_fence("```c++\ncode\n```  \nafter")


def test_blocks_with_line_endings_of_a_windows_client_are_seen() -> None:
    chunker = _chunker()

    assert chunker._is_inside_code_fence("```python\r\ncode\r\n")
    assert chunker._is_inside_code_fence("```c++\r\ncode\r\n")
    assert not chunker._is_inside_code_fence("```c++\r\ncode\r\n```\r\nafter")


def test_each_block_of_a_reply_counts_whatever_its_info_string() -> None:
    chunker = _chunker()
    first = "First:\n```c++\ncode\n```\nSecond:\n```python\nmore"
    second = "First:\n```python\ncode\n```\nSecond:\n```c#\nmore\n```\nDone"

    assert chunker._is_inside_code_fence(first)
    assert not chunker._is_inside_code_fence(second)


def test_a_fence_closing_the_end_of_a_code_line_still_closes_the_block() -> None:
    chunker = _chunker()

    assert not chunker._is_inside_code_fence("```python\ncode```\nmore")
    assert chunker._is_inside_code_fence("```python\ncode```\nmore\n```js\nx")


def test_a_line_that_opens_and_closes_a_span_of_backticks_does_not_shift_the_blocks_after_it() -> None:
    chunker = _chunker()

    assert not chunker._is_inside_code_fence("```code``` is how a block looks on one line.\n```c++\ncode\n```\nafter")
    assert chunker._is_inside_code_fence("```code``` is how a block looks on one line.\n```c++\ncode")


@pytest.mark.parametrize(
    "prose",
    [
        "Use triple backticks (```) to start a block.\n",
        "```code``` is how a block looks on one line.\n",
        "Write ``` then the language.\n",
    ],
)
def test_backticks_inside_a_line_of_prose_are_not_a_fence(prose: str) -> None:
    chunker = _chunker()
    text = prose + _PROSE

    assert not chunker._is_inside_code_fence(text)
    assert chunker.should_emit_block(text, is_final=False)
