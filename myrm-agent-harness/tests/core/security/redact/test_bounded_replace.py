"""Bounded replace: a long text is cut into overlapping chunks and a match is replaced once, whole."""

from __future__ import annotations

import re

import pytest

from myrm_agent_harness.core.security.redact.bounded_replace import (
    _CHUNK_OVERLAP,
    _REDACT_REGEX_CHUNK_SIZE,
    _replace_pattern_bounded,
)

_CHUNK_END = _REDACT_REGEX_CHUNK_SIZE + _CHUNK_OVERLAP
_SECRET = "SECRETabcdefghijklmnop"
_TEXT_LENGTH = 40_000


class TestAMatchAtTheEndOfAChunk:
    """The first chunk ends inside the overlap, so it sees a match there cut short; the next chunk sees it whole."""

    @pytest.mark.parametrize("boundary", [_CHUNK_END, _CHUNK_END + _REDACT_REGEX_CHUNK_SIZE])
    def test_the_whole_match_is_replaced(self, boundary: int) -> None:
        pattern = re.compile(r"SECRET[a-z]+")
        for offset in range(boundary - len(_SECRET) - 2, boundary + 2):
            text = "." * offset + _SECRET + "." * (_TEXT_LENGTH - offset - len(_SECRET))
            assert _replace_pattern_bounded(text, pattern, "X") == "." * offset + "X" + "." * (
                _TEXT_LENGTH - offset - len(_SECRET)
            ), offset

    def test_a_match_inside_the_overlap_is_replaced_once(self) -> None:
        pattern = re.compile(r"SECRET[a-z]+")
        offset = _REDACT_REGEX_CHUNK_SIZE + 100
        text = "." * offset + _SECRET + "." * (_TEXT_LENGTH - offset - len(_SECRET))
        assert _replace_pattern_bounded(text, pattern, "X").count("X") == 1
