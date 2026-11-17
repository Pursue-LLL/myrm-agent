"""``like_contains_pattern`` matches the typed text character for character, and nothing searchable means no pattern."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from app.database.repositories.like_pattern import LIKE_ESCAPE_CLAUSE, like_contains_pattern

_ROWS = (
    "plain docker notes",
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


def _found(conn: sqlite3.Connection, typed: str) -> list[str]:
    pattern = like_contains_pattern(typed)
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


@pytest.mark.parametrize("typed", ["", "   ", "\u3000", '""', '"', ' " " ', '" "" "'])
def test_nothing_searchable_means_no_pattern(typed: str) -> None:
    assert like_contains_pattern(typed) is None


def test_the_escape_character_is_escaped_before_the_wildcards() -> None:
    assert like_contains_pattern("100%_x\\") == "%100\\%\\_x\\\\%"
