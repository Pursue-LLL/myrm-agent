"""The LIKE pattern of a typed query matches the typed text; phrase quotes go unless the caller keeps them.

A query with nothing searchable left in it has no pattern, because ``%%`` would match every row.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from app.database.repositories.like_pattern import LIKE_ESCAPE_CLAUSE, like_contains_pattern, typed_needle

_ROWS = (
    "plain docker notes",
    'say "hi" now',
    "say hi now",
    "ratio is 50% of total",
    "ratio is 5000 of total",
    "name foo_bar here",
    "name fooxbar here",
    "path C:\\Users\\me\\proj",
    "path C:Usersmeproj",
    "uses C++ templates",
    "uses C templates",
    "he said it's fine",
    "tail a_ end",
    "tail ab end",
    "沙箱部署记录",
)


@pytest.fixture(scope="module")
def table() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE messages (content TEXT)")
    conn.executemany("INSERT INTO messages(content) VALUES (?)", [(row,) for row in _ROWS])
    yield conn
    conn.close()


def _found(conn: sqlite3.Connection, typed: str, *, keep_quotes: bool = False) -> list[str]:
    pattern = like_contains_pattern(typed, keep_quotes=keep_quotes)
    assert pattern is not None
    rows = conn.execute(f"SELECT content FROM messages WHERE content LIKE ? {LIKE_ESCAPE_CLAUSE} ORDER BY rowid", (pattern,))
    return [row[0] for row in rows]


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("docker", ["plain docker notes"]),
        ("DOCKER", ["plain docker notes"]),
        ("  docker \u3000", ["plain docker notes"]),
        ("沙箱", ["沙箱部署记录"]),
        ("50%", ["ratio is 50% of total"]),
        ("foo_bar", ["name foo_bar here"]),
        ("a_", ["tail a_ end"]),
        ("C:\\Users\\me", ["path C:\\Users\\me\\proj"]),
        ("C++", ["uses C++ templates"]),
        ("it's", ["he said it's fine"]),
        ('"docker"', ["plain docker notes"]),
        ('"ab"', ["tail ab end"]),
    ],
)
def test_the_pattern_matches_the_typed_text_literally(table: sqlite3.Connection, typed: str, expected: list[str]) -> None:
    assert _found(table, typed) == expected


@pytest.mark.parametrize(
    ("typed", "keep_quotes", "expected"),
    [
        ('"hi"', False, ['say "hi" now', "say hi now"]),
        ('"hi"', True, ['say "hi" now']),
        ('say "hi"', True, ['say "hi" now']),
        ("hi", True, ['say "hi" now', "say hi now"]),
    ],
)
def test_a_caller_decides_whether_the_typed_quotes_are_part_of_the_text(
    table: sqlite3.Connection, typed: str, keep_quotes: bool, expected: list[str]
) -> None:
    assert _found(table, typed, keep_quotes=keep_quotes) == expected


@pytest.mark.parametrize("typed", ["", "   ", "\u3000", '""', '"', ' " " ', '" "" "'])
def test_nothing_searchable_means_no_pattern(typed: str) -> None:
    assert like_contains_pattern(typed) is None


@pytest.mark.parametrize(
    ("typed", "pattern"),
    [('""', '%""%'), ('"', '%"%'), (' " " ', '%" "%'), ("", None), ("   ", None), ("\u3000", None)],
)
def test_quotes_that_are_kept_are_searchable_text_and_only_blank_means_no_pattern(typed: str, pattern: str | None) -> None:
    assert like_contains_pattern(typed, keep_quotes=True) == pattern


@pytest.mark.parametrize(
    ("typed", "keep_quotes", "needle"),
    [
        ('  "ab" ', False, "ab"),
        ('  "ab" ', True, '"ab"'),
        ("C++", False, "C++"),
        ('""', False, None),
        ('""', True, '""'),
        ("   ", True, None),
    ],
)
def test_the_needle_is_the_typed_text_without_surrounding_whitespace(typed: str, keep_quotes: bool, needle: str | None) -> None:
    assert typed_needle(typed, keep_quotes=keep_quotes) == needle


def test_the_escape_character_is_escaped_before_the_wildcards() -> None:
    assert like_contains_pattern("100%_x\\") == "%100\\%\\_x\\\\%"
