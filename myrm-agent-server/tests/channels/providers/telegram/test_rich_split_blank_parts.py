"""Telegram's Rich Message splitter never emits a part of whitespace alone, and always advances.

Telegram refuses a message with no visible text, which would fail the whole delivery, so whitespace that a cut leaves
at the head or the tail of the text is dropped. A character dearer than the limit still goes out on its own part.
"""

import random

import pytest

from app.channels.providers.telegram.html_converter import split_markdown_rich

pytestmark = pytest.mark.timeout(30)


def test_whitespace_left_after_the_last_cut_is_dropped():
    assert split_markdown_rich("a" * 32000 + "   ") == ["a" * 32000]
    assert split_markdown_rich("a" * 50 + "   ", limit=50) == ["a" * 50]


def test_whitespace_ahead_of_the_text_is_no_part():
    parts = split_markdown_rich(" " * 100 + "word " * 20, limit=40)

    assert parts
    assert all(part.strip() for part in parts)
    assert "".join(parts).split() == ["word"] * 20


def test_a_character_dearer_than_the_limit_goes_out_alone_and_the_split_ends():
    assert split_markdown_rich("\U0001f600" * 3, limit=3) == ["\U0001f600"] * 3


def test_a_text_that_fits_is_returned_whole_and_one_of_whitespace_alone_gives_no_part():
    assert split_markdown_rich("  padded  ", limit=100) == ["  padded  "]
    assert split_markdown_rich(" \n\t\n", limit=100) == []
    assert split_markdown_rich("") == []


def test_random_whitespace_heavy_documents_split_into_visible_parts_that_keep_every_word():
    alphabet = ["a", "b", "word", " ", " ", "\n", "\n\n", "\t", "。", "\U0001f600", "中", ". "]
    for seed in range(3000):
        rng = random.Random(seed)
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 120)))
        limit = rng.randint(8, 120)

        parts = split_markdown_rich(text, limit=limit)

        assert all(len(part.encode("utf-8")) <= limit for part in parts), f"seed {seed} limit {limit}: {parts!r}"
        assert all(part.strip() for part in parts), f"seed {seed} limit {limit}: {text!r} -> {parts!r}"
        assert "".join("".join(parts).split()) == "".join(text.split()), f"seed {seed} limit {limit}: {text!r}"
