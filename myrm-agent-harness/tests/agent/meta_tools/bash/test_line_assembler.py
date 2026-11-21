"""``LineAssembler`` cuts a job's byte stream into lines and keeps the unfinished last line visible.

The lines must be the ones a line reader returns, wherever the chunk boundaries fall, so the differential test
checks random streams against a one-pass reference of the same rule.
"""

from __future__ import annotations

import codecs
import random

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.line_assembler import TAIL_CHARS, LineAssembler

_CAP = 32 * 1024
_PIECES = (
    b"alpha",
    b" ",
    b"\t",
    b"\n",
    b"\r",
    b"\r\n",
    b"\n\n",
    "é".encode(),
    "世界".encode(),
    "😀".encode(),
    b"\xff",
    b"\xc3",
    b"\xe2\x82",
    b"x" * 40,
    b"y" * 100,
)
_CHUNK_SIZES = (1, 2, 3, 7, 64, 1024, 64 * 1024)


def _feed_in_chunks(data: bytes, chunk_size: int, *, cap: int = _CAP) -> tuple[LineAssembler, list[str]]:
    assembler = LineAssembler(max_line_chars=cap)
    lines: list[str] = []
    for start in range(0, len(data), chunk_size):
        lines.extend(assembler.feed(data[start : start + chunk_size]))
    return assembler, lines


def _clip(text: str, cap: int) -> str:
    return f"{text[:cap]}... [+{len(text) - cap} chars truncated]" if len(text) > cap else text


def _reference(data: bytes, cap: int) -> tuple[list[str], str, list[str]]:
    """The rule in one pass over the whole stream: the lines, the unfinished tail and the line the end of stream adds."""
    *complete, rest = data.split(b"\n")
    lines = [_clip(piece.decode("utf-8", errors="replace").rstrip(), cap) for piece in complete]
    pending_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    tail = pending_decoder.decode(rest)[-TAIL_CHARS:]
    final = rest.decode("utf-8", errors="replace")
    return lines, tail, [_clip(final.rstrip(), cap)] if final else []


def test_a_line_split_across_chunks_is_returned_whole() -> None:
    assembler = LineAssembler(max_line_chars=_CAP)

    assert assembler.feed(b"hel") == []
    assert assembler.feed(b"lo wor") == []
    assert assembler.feed(b"ld\nnext") == ["hello world"]
    assert assembler.tail == "next"


def test_trailing_whitespace_is_stripped_and_a_blank_line_is_an_empty_line() -> None:
    assembler = LineAssembler(max_line_chars=_CAP)

    assert assembler.feed(b"a  \r\n   \t\nb \n\n") == ["a", "", "b", ""]
    assert assembler.tail == ""


def test_trailing_whitespace_split_across_chunks_is_still_stripped() -> None:
    assembler = LineAssembler(max_line_chars=_CAP)

    assert assembler.feed(b"done  ") == []
    assert assembler.feed(b"   \r") == []
    assert assembler.feed(b"\n") == ["done"]


def test_a_multibyte_character_cut_by_a_chunk_boundary_is_decoded_whole() -> None:
    encoded = "naïve 世界\n".encode()
    assembler = LineAssembler(max_line_chars=_CAP)

    lines = [line for byte in encoded for line in assembler.feed(bytes([byte]))]

    assert lines == ["naïve 世界"]


def test_bytes_that_are_not_utf8_become_replacement_characters() -> None:
    assembler = LineAssembler(max_line_chars=_CAP)

    assert assembler.feed(b"a\xffb\xc3\n") == ["a\ufffdb\ufffd"]


def test_the_tail_is_what_follows_the_last_newline_and_keeps_its_trailing_space() -> None:
    assembler = LineAssembler(max_line_chars=_CAP)

    assembler.feed(b"line one\nContinue? [y/N] ")
    assert assembler.tail == "Continue? [y/N] "

    assembler.feed(b"y\n")
    assert assembler.tail == ""


def test_the_tail_keeps_only_its_last_characters() -> None:
    assembler = LineAssembler(max_line_chars=_CAP)

    assembler.feed(b"a" * 1000 + b"END")

    assert assembler.tail == "a" * (TAIL_CHARS - 3) + "END"


@pytest.mark.parametrize(
    ("length", "expected"),
    [(_CAP - 1, "x" * (_CAP - 1)), (_CAP, "x" * _CAP), (_CAP + 1, "x" * _CAP + "... [+1 chars truncated]")],
)
def test_a_line_keeps_its_first_32_ki_characters_and_counts_the_rest(length: int, expected: str) -> None:
    for chunk_size in (1000, 64 * 1024):
        _, lines = _feed_in_chunks(b"x" * length + b"\n", chunk_size)

        assert lines == [expected]


def test_a_line_far_past_the_cap_costs_the_cap_not_its_length() -> None:
    assembler = LineAssembler(max_line_chars=_CAP)

    for _ in range(40):
        assembler.feed(b"z" * 64 * 1024)
    lines = assembler.feed(b"\n")

    assert lines == ["z" * _CAP + f"... [+{40 * 64 * 1024 - _CAP} chars truncated]"]


def test_the_end_of_the_stream_turns_the_unfinished_line_into_a_line() -> None:
    assembler = LineAssembler(max_line_chars=_CAP)
    assembler.feed(b"first\nlast without newline  ")

    assert assembler.finish() == ["last without newline"]


def test_the_end_of_a_stream_that_ended_with_a_newline_adds_nothing() -> None:
    assembler = LineAssembler(max_line_chars=_CAP)
    assembler.feed(b"only line\n")

    assert assembler.finish() == []


def test_the_end_of_the_stream_decodes_a_cut_character_as_a_replacement() -> None:
    assembler = LineAssembler(max_line_chars=_CAP)
    assembler.feed(b"ab" + "世".encode()[:2])

    assert assembler.finish() == ["ab\ufffd"]


@pytest.mark.parametrize("seed", range(200))
def test_random_streams_cut_into_the_lines_a_single_pass_gives(seed: int) -> None:
    rng = random.Random(seed)
    data = b"".join(rng.choice(_PIECES) for _ in range(rng.randint(0, 60)))
    cap = rng.choice((8, 64, _CAP))
    expected_lines, expected_tail, expected_last = _reference(data, cap)

    for chunk_size in {1, rng.choice(_CHUNK_SIZES), rng.choice(_CHUNK_SIZES)}:
        assembler, lines = _feed_in_chunks(data, chunk_size, cap=cap)

        assert lines == expected_lines, f"chunk_size={chunk_size}"
        assert assembler.tail == expected_tail, f"chunk_size={chunk_size}"
        assert assembler.finish() == expected_last, f"chunk_size={chunk_size}"
