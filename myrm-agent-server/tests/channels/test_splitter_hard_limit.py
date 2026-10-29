"""Hard length limit of rendering/splitter.py: no chunk is over ``max_len`` and none is an empty code block."""

from __future__ import annotations

import random

import pytest

from app.channels.rendering.splitter import split_message
from tests.channels.splitter_testkit import EMPTY_FENCE, random_document, text_of


class TestHardLimit:
    """A platform refuses a message over its limit, so no chunk goes past ``max_len`` and none is an empty code block."""

    @pytest.mark.parametrize("line_len", [1985, 1990, 1999, 2000, 2300, 5000])
    def test_a_long_fenced_line_is_cut_to_the_limit(self, line_len: int) -> None:
        line = "y" * line_len
        chunks = split_message(f"```json\n{line}\n```", max_len=2000)

        assert all(len(chunk) <= 2000 for chunk in chunks)
        assert all(chunk.startswith("```json\n") and chunk.endswith("\n```") for chunk in chunks)
        assert "".join(chunk.split("\n")[1] for chunk in chunks) == line

    def test_a_fence_opener_does_not_become_a_chunk_of_its_own(self) -> None:
        chunks = split_message("intro\n```json\n" + "y" * 2300 + "\n```", max_len=2000)

        assert chunks[0].strip() == "intro"
        assert not any(EMPTY_FENCE.match(chunk.strip()) for chunk in chunks)

    def test_the_closing_symbol_of_a_long_fence_is_reserved_in_full(self) -> None:
        fence = "`" * 10
        chunks = split_message("\n".join([fence, *["x" * 39] * 10, fence]), max_len=100)

        assert len(chunks) > 1
        assert all(len(chunk) <= 100 for chunk in chunks)

    def test_random_documents_stay_within_the_limit_without_empty_blocks_or_lost_text(self) -> None:
        rng = random.Random(20261030)
        for _ in range(300):
            limit = rng.choice([120, 300, 2000])
            document = random_document(rng, limit)
            chunks = split_message(document, max_len=limit)

            assert all(len(chunk) <= limit for chunk in chunks), (limit, [len(c) for c in chunks])
            assert not any(EMPTY_FENCE.match(chunk.strip()) for chunk in chunks)
            assert text_of(chunks) == text_of([document])
