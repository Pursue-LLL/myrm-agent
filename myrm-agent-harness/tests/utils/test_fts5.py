"""FTS5 helpers: query sanitizing, rank relevance, integrity check and heal of a really damaged index."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from myrm_agent_harness.utils.db import fts5
from myrm_agent_harness.utils.db.fts5 import (
    fts5_auto_heal,
    fts5_integrity_check,
    relevance_from_rank,
    sanitize_fts5_query,
)
from tests.support.fts5_corruption import CORRUPTIONS, corrupt_fts5_content_page, corrupt_fts5_index


def test_sanitize_fts5_query_strips_dangerous_chars():
    assert sanitize_fts5_query("hello +world") == "hello  world"
    assert sanitize_fts5_query("error {code}") == "error  code"
    assert sanitize_fts5_query("function(arg)") == "function arg"
    assert sanitize_fts5_query('unmatched"quote') == "unmatched quote"
    assert sanitize_fts5_query("start ^end") == "start  end"


def test_sanitize_fts5_preserves_quoted_phrases():
    assert sanitize_fts5_query('find "exact phrase here"') == 'find "exact phrase here"'
    assert sanitize_fts5_query('"phrase 1" AND "phrase 2"') == '"phrase 1" AND "phrase 2"'


def test_sanitize_fts5_quotes_hyphenated_terms():
    assert sanitize_fts5_query("npm-install") == '"npm-install"'
    assert sanitize_fts5_query("run my-script-name now") == 'run "my-script-name" now'
    assert sanitize_fts5_query('already "quoted-term"') == 'already "quoted-term"'


def test_sanitize_fts5_quotes_dotted_terms():
    assert sanitize_fts5_query("app.config.ts") == '"app.config.ts"'
    assert sanitize_fts5_query("version P2.2") == 'version "P2.2"'


def test_sanitize_fts5_handles_asterisks():
    assert sanitize_fts5_query("prefix*") == "prefix*"
    assert sanitize_fts5_query("prefix***") == "prefix*"
    assert sanitize_fts5_query("*suffix") == "suffix"
    assert sanitize_fts5_query(" * suffix") == "suffix"


def test_sanitize_fts5_removes_dangling_booleans():
    assert sanitize_fts5_query("AND hello") == "hello"
    assert sanitize_fts5_query("hello OR") == "hello"
    assert sanitize_fts5_query("NOT") == ""
    assert sanitize_fts5_query("valid AND query") == "valid AND query"


def test_sanitize_fts5_strips_angle_brackets_and_slashes():
    result = sanitize_fts5_query("<script>alert(1)</script>")
    assert "<" not in result
    assert ">" not in result
    assert "/" not in result

    result2 = sanitize_fts5_query("hello <b>world</b>")
    assert "<" not in result2
    assert ">" not in result2


def test_sanitize_fts5_strips_colons_and_special_punctuation():
    result = sanitize_fts5_query("column:value")
    assert ":" not in result

    result2 = sanitize_fts5_query("C:\\Users\\test")
    assert "\\" not in result2


def test_sanitize_fts5_handles_all_boolean_operators():
    assert sanitize_fts5_query("AND OR NOT") == ""
    assert sanitize_fts5_query("AND") == ""
    assert sanitize_fts5_query("OR") == ""


def test_sanitize_fts5_empty_and_whitespace():
    assert sanitize_fts5_query("") == ""
    assert sanitize_fts5_query("   ") == ""


def test_sanitize_fts5_strips_hyphens_preserves_compounds():
    assert sanitize_fts5_query("-negative") == "negative"
    assert sanitize_fts5_query("hello -world") == "hello  world"
    assert sanitize_fts5_query("---") == ""
    assert sanitize_fts5_query("-") == ""
    assert sanitize_fts5_query("hello---world") == "hello world"
    assert sanitize_fts5_query("chat-send") == '"chat-send"'
    assert sanitize_fts5_query("npm-install") == '"npm-install"'


def test_sanitize_fts5_strips_brackets_pipe_null():
    result = sanitize_fts5_query("[bracket]")
    assert "[" not in result
    assert "]" not in result
    result2 = sanitize_fts5_query("|pipe")
    assert "|" not in result2
    result3 = sanitize_fts5_query("\x00null")
    assert "\x00" not in result3


def test_sanitize_fts5_strips_near_operator():
    result = sanitize_fts5_query("NEAR")
    assert result == ""
    result2 = sanitize_fts5_query("hello NEAR world")
    assert "NEAR" not in result2


_NOTES = 60


@pytest.fixture
def notes(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """An FTS5 table of ``_NOTES`` rows that all match "payment"."""
    conn = sqlite3.connect(tmp_path / "notes.db")
    conn.execute("CREATE VIRTUAL TABLE notes_fts USING fts5(title, body)")
    conn.executemany(
        "INSERT INTO notes_fts VALUES (?, ?)",
        [(f"note {i}", f"payment gateway topic {i} " * 20) for i in range(_NOTES)],
    )
    conn.commit()
    yield conn
    conn.close()


def _payment_matches(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT count(*) FROM notes_fts WHERE notes_fts MATCH 'payment'").fetchone()[0])


def test_integrity_check_passes_on_a_healthy_index(notes: sqlite3.Connection) -> None:
    assert fts5_integrity_check(notes, "notes_fts") is True


@pytest.mark.parametrize("kind", CORRUPTIONS)
def test_integrity_check_reports_a_really_damaged_index(notes: sqlite3.Connection, kind: str) -> None:
    corrupt_fts5_index(notes, "notes_fts", kind)

    assert fts5_integrity_check(notes, "notes_fts") is False


@pytest.mark.parametrize("kind", CORRUPTIONS)
def test_auto_heal_rebuilds_a_really_damaged_index(notes: sqlite3.Connection, kind: str) -> None:
    corrupt_fts5_index(notes, "notes_fts", kind)

    assert fts5_auto_heal(notes, "notes_fts") is True
    assert fts5_integrity_check(notes, "notes_fts") is True
    assert _payment_matches(notes) == _NOTES


def test_auto_heal_declines_when_the_stored_text_cannot_be_read(tmp_path: Path, notes: sqlite3.Connection) -> None:
    """The rebuild reads the stored text, so a table whose rows are unreadable is not reported as healed."""
    notes.close()
    db_path = tmp_path / "notes.db"
    corrupt_fts5_content_page(db_path, "notes_fts")

    with closing(sqlite3.connect(db_path)) as conn:
        assert fts5_auto_heal(conn, "notes_fts") is False
        assert fts5_integrity_check(conn, "notes_fts") is False


def test_auto_heal_leaves_a_healthy_index_alone(notes: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    def rebuilt(conn: sqlite3.Connection, table: str) -> None:
        raise AssertionError("a healthy index must not be rebuilt")

    monkeypatch.setattr(fts5, "fts5_rebuild", rebuilt)

    assert fts5_auto_heal(notes, "notes_fts") is False


def test_a_better_fts_rank_scores_higher() -> None:
    ranks = [-0.1, -1.0, -5.0, -20.0]  # FTS5 ranks a better match with a lower, negative number
    scores = [relevance_from_rank(rank) for rank in ranks]

    assert scores == sorted(scores)
    assert len(set(scores)) == len(scores)


def test_the_relevance_score_is_a_fraction_below_one() -> None:
    assert all(0.0 <= relevance_from_rank(rank) < 1.0 for rank in (0.0, -1e-6, -1.0, -1e6))
