"""What ExecutionStreamBuffer hands back: the whole output while it fits, head and tail with the middle counted beyond.

Covers:
- An output that fits ``max_chars`` comes back exactly: no notice splits it where the head ends, and ``truncated`` is False
- An output beyond it keeps its head and tail, and one notice counts exactly the characters dropped between them
- The result, notice included, fits ``max_chars``, so the cut that ``ExecutionResult`` makes of stdout leaves it alone
- ``reserve`` keeps room for text the caller appends to a cut output, and costs an output that fits nothing
"""

from __future__ import annotations

import re

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.common.executor_utils import MAX_OUTPUT_CHARS
from myrm_agent_harness.toolkits.code_execution.session.stream_buffer import ExecutionStreamBuffer

_EXIT_MARKER = "EXIT_MARKER"
_END_MARKER = "END_MARKER"
_NOTICE = re.compile(
    r"\n\n\[System Warning: The middle (\d+) characters of output were truncated to prevent memory overflow\]\n\n"
)
_CHUNK_BYTES = 8192


def _text(chars: int) -> str:
    """``chars`` characters in which every position reads differently, so a kept part can be placed in the whole."""
    return "".join(f"{index:07d}\n" for index in range(chars // 8 + 1))[:chars]


def _filled(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> ExecutionStreamBuffer:
    buffer = ExecutionStreamBuffer(max_chars=max_chars)
    data = text.encode("utf-8")
    for start in range(0, len(data), _CHUNK_BYTES):
        buffer.process_bytes(data[start : start + _CHUNK_BYTES], _EXIT_MARKER, _END_MARKER)
    return buffer


def _parts(output: str) -> tuple[str, int, str]:
    """The head, the dropped count the notice states, and the tail of a cut output."""
    notice = _NOTICE.search(output)
    assert notice is not None, "a cut output carries the notice"
    assert len(_NOTICE.findall(output)) == 1
    return output[: notice.start()], int(notice[1]), output[notice.end() :]


class TestOutputThatFits:
    def test_output_beyond_the_head_comes_back_exactly(self) -> None:
        text = _text(150_000)
        buffer = _filled(text)

        assert buffer.get_final_output() == text
        assert not buffer.truncated

    def test_output_of_exactly_max_chars_comes_back_exactly(self) -> None:
        text = _text(MAX_OUTPUT_CHARS)
        buffer = _filled(text)

        assert buffer.get_final_output() == text
        assert not buffer.truncated

    def test_output_within_the_head_comes_back_exactly(self) -> None:
        text = _text(1000)
        buffer = _filled(text)

        assert buffer.get_final_output() == text
        assert not buffer.truncated


class TestOutputBeyondMaxChars:
    def test_head_and_tail_are_kept_and_the_middle_is_counted_exactly(self) -> None:
        text = _text(500_000)
        buffer = _filled(text)

        output = buffer.get_final_output()
        head, dropped, tail = _parts(output)

        assert buffer.truncated
        assert head and tail
        assert text.startswith(head)
        assert text.endswith(tail)
        assert len(head) + dropped + len(tail) == len(text)

    @pytest.mark.parametrize(
        "chars",
        [MAX_OUTPUT_CHARS + 1, MAX_OUTPUT_CHARS + 9_890, 300_000, 1_100_000],
        ids=["one-beyond", "count-grows-a-digit", "six-digit-count", "seven-digit-count"],
    )
    def test_the_result_fits_max_chars_and_counts_exactly_at_every_size(self, chars: int) -> None:
        # The notice is a digit longer for a larger count: the room set aside for it must cover every size.
        text = _text(chars)
        buffer = _filled(text)

        output = buffer.get_final_output()
        head, dropped, tail = _parts(output)

        assert buffer.truncated
        assert len(output) <= MAX_OUTPUT_CHARS
        assert len(head) + dropped + len(tail) == len(text)


class TestReserve:
    def test_room_is_kept_for_what_the_caller_appends(self) -> None:
        text = _text(500_000)
        buffer = _filled(text)

        output = buffer.get_final_output(reserve=500)
        head, dropped, tail = _parts(output)

        assert len(output) + 500 <= MAX_OUTPUT_CHARS
        assert text.startswith(head)
        assert text.endswith(tail)
        assert len(head) + dropped + len(tail) == len(text)

    def test_an_output_that_fits_gives_nothing_up_for_it(self) -> None:
        # The caller appends its text to a cut output only, so an output that fits needs no room.
        text = _text(MAX_OUTPUT_CHARS - 100)
        buffer = _filled(text)

        assert buffer.get_final_output(reserve=500) == text
        assert not buffer.truncated


class TestCapTooSmallForTheNotice:
    def test_the_head_is_kept_and_every_character_is_still_counted(self) -> None:
        text = _text(1000)
        buffer = _filled(text, max_chars=100)

        head, dropped, tail = _parts(buffer.get_final_output())

        assert text.startswith(head)
        assert text.endswith(tail)
        assert len(head) + dropped + len(tail) == len(text)
