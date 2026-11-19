"""FTS5 helpers: query sanitizing, rank relevance, integrity check and heal of a really damaged index."""

from __future__ import annotations

import random
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


def test_sanitize_fts5_query_strips_dangerous_chars() -> None:
    assert sanitize_fts5_query("hello +world") == "hello  world"
    assert sanitize_fts5_query("error {code}") == "error  code"
    assert sanitize_fts5_query("function(arg)") == "function arg"
    assert sanitize_fts5_query('unmatched"quote') == "unmatched quote"
    assert sanitize_fts5_query("start ^end") == "start  end"


def test_sanitize_fts5_preserves_quoted_phrases() -> None:
    assert sanitize_fts5_query('find "exact phrase here"') == 'find "exact phrase here"'
    assert sanitize_fts5_query('"phrase 1" AND "phrase 2"') == '"phrase 1" AND "phrase 2"'


def test_sanitize_fts5_quotes_hyphenated_terms() -> None:
    assert sanitize_fts5_query("npm-install") == '"npm-install"'
    assert sanitize_fts5_query("run my-script-name now") == 'run "my-script-name" now'
    assert sanitize_fts5_query('already "quoted-term"') == 'already "quoted-term"'


def test_sanitize_fts5_quotes_dotted_terms() -> None:
    assert sanitize_fts5_query("app.config.ts") == '"app.config.ts"'
    assert sanitize_fts5_query("version P2.2") == 'version "P2.2"'


def test_sanitize_fts5_handles_asterisks() -> None:
    assert sanitize_fts5_query("prefix*") == "prefix*"
    assert sanitize_fts5_query("prefix***") == "prefix*"
    assert sanitize_fts5_query("*suffix") == "suffix"
    assert sanitize_fts5_query(" * suffix") == "suffix"


def test_sanitize_fts5_removes_dangling_booleans() -> None:
    assert sanitize_fts5_query("AND hello") == "hello"
    assert sanitize_fts5_query("hello OR") == "hello"
    assert sanitize_fts5_query("NOT") == ""
    assert sanitize_fts5_query("valid AND query") == "valid AND query"


def test_sanitize_fts5_strips_angle_brackets_and_slashes() -> None:
    result = sanitize_fts5_query("<script>alert(1)</script>")
    assert "<" not in result
    assert ">" not in result
    assert "/" not in result

    result2 = sanitize_fts5_query("hello <b>world</b>")
    assert "<" not in result2
    assert ">" not in result2


def test_sanitize_fts5_strips_colons_and_special_punctuation() -> None:
    result = sanitize_fts5_query("column:value")
    assert ":" not in result

    result2 = sanitize_fts5_query("C:\\Users\\test")
    assert "\\" not in result2


def test_sanitize_fts5_handles_all_boolean_operators() -> None:
    assert sanitize_fts5_query("AND OR NOT") == ""
    assert sanitize_fts5_query("AND") == ""
    assert sanitize_fts5_query("OR") == ""


def test_sanitize_fts5_empty_and_whitespace() -> None:
    assert sanitize_fts5_query("") == ""
    assert sanitize_fts5_query("   ") == ""


def test_sanitize_fts5_strips_hyphens_preserves_compounds() -> None:
    assert sanitize_fts5_query("-negative") == "negative"
    assert sanitize_fts5_query("hello -world") == "hello  world"
    assert sanitize_fts5_query("---") == ""
    assert sanitize_fts5_query("-") == ""
    assert sanitize_fts5_query("hello---world") == "hello world"
    assert sanitize_fts5_query("chat-send") == '"chat-send"'
    assert sanitize_fts5_query("npm-install") == '"npm-install"'


def test_sanitize_fts5_strips_brackets_pipe_null() -> None:
    result = sanitize_fts5_query("[bracket]")
    assert "[" not in result
    assert "]" not in result
    result2 = sanitize_fts5_query("|pipe")
    assert "|" not in result2
    result3 = sanitize_fts5_query("\x00null")
    assert "\x00" not in result3


def test_sanitize_fts5_strips_near_operator() -> None:
    result = sanitize_fts5_query("NEAR")
    assert result == ""
    result2 = sanitize_fts5_query("hello NEAR world")
    assert "NEAR" not in result2


def test_sanitize_fts5_quotes_pieces_fts5_does_not_read_as_a_word() -> None:
    assert sanitize_fts5_query("don't") == '"don\'t"'
    assert sanitize_fts5_query("see `code` here") == 'see "`code`" here'
    assert sanitize_fts5_query("hello world.") == 'hello "world."'
    assert sanitize_fts5_query("e.g.") == '"e.g" "."'
    assert sanitize_fts5_query("你好.") == '"你好."'
    assert sanitize_fts5_query("foo*bar") == '"foo*bar"'


def test_sanitize_fts5_keeps_a_prefix_star_after_a_quoted_word() -> None:
    assert sanitize_fts5_query("chat-sen*") == '"chat-sen"*'
    assert sanitize_fts5_query("it's*") == '"it\'s"*'


def test_sanitize_fts5_separates_quoted_pieces_that_touch() -> None:
    """FTS5 reads two touching quoted pieces as one phrase that holds a literal quote."""
    assert sanitize_fts5_query('"a""b"') == '"a" "b"'


def test_sanitize_fts5_keeps_a_boolean_operator_only_between_two_operands() -> None:
    assert sanitize_fts5_query("a AND AND b").split() == ["a", "AND", "b"]
    assert sanitize_fts5_query("a AND NEAR") == "a"
    assert sanitize_fts5_query("a NOT b") == "a NOT b"
    assert sanitize_fts5_query("a-*") == "a"


# ---------------------------------------------------------------------------
# Output contract: FTS5 reads whatever the sanitizer returns
# ---------------------------------------------------------------------------

_TOKENIZERS = ("unicode61", "porter unicode61", "trigram")
_EVERYDAY_QUERIES = (
    "don't",
    "it's what's",
    "John's I'm we're",
    "e.g.",
    "i.e. etc.",
    "Inc.",
    "hello world.",
    "wait...",
    "v2.0.",
    "node.js,",
    "'quoted'",
    "`code`",
    "C++",
    "a, b",
    "$100",
    "50%",
    "#tag @user",
    "https://example.com/a?b=c",
    "src/app/page.tsx",
    "key=value",
    "foo: bar",
    "(draft)",
    "[todo]",
    "what?! really",
    "你好.",
    "你好，世界",
    "emoji 🙂.",
)
_SYNTAX_EDGE_QUERIES = (
    "AND",
    "OR OR",
    "a AND AND b",
    "a OR NOT",
    "a AND NEAR",
    "x NEAR/3 y",
    "NOT NOT a",
    "AND*",
    "*AND",
    "*",
    "**",
    "a * b",
    "a-*",
    "foo*bar",
    "foo**",
    "chat-sen*",
    '"phrase"*',
    '"a""b"',
    '"" a',
    '"unclosed',
    'a"b"c',
    "-",
    "--x--",
    "a - b",
    "col:val",
    "{x} [y] a|b",
    "\x00x\x01y\ttab\nnl",
)
_FUZZ_PIECES = (
    *("a", "foo", "你好", "é", "🙂", "_", "7", "x.y", "a-b", "AND", "OR", "NOT", "NEAR", "near"),
    *("'", "`", ".", "..", "-", "*", "**", '"', ",", ";", ":", "(", ")", "[", "]", "{", "}"),
    *("+", "^", "/", "\\", "|", "&", "%", "$", "#", "@", "!", "?", "<", ">", "=", "~"),
    *("\x00", "\t", "\n", " ", " "),
)
_FUZZ_CASES = 3000


def _random_query(rng: random.Random) -> str:
    return "".join(rng.choice(_FUZZ_PIECES) for _ in range(rng.randint(1, 14)))


def _rejected_output(conn: sqlite3.Connection, raw: str) -> str:
    """The sanitizer's output for ``raw`` when FTS5 rejects it as a MATCH expression, otherwise empty."""
    output = sanitize_fts5_query(raw)
    if not output:
        return ""
    try:
        conn.execute("SELECT rowid FROM docs WHERE docs MATCH ?", (output,)).fetchall()
    except sqlite3.OperationalError:
        return output
    return ""


@pytest.mark.parametrize("tokenizer", _TOKENIZERS)
def test_the_output_is_always_a_query_fts5_can_parse(tokenizer: str) -> None:
    rng = random.Random(20260116)
    queries = [*_EVERYDAY_QUERIES, *_SYNTAX_EDGE_QUERIES, *(_random_query(rng) for _ in range(_FUZZ_CASES))]

    with closing(sqlite3.connect(":memory:")) as conn:
        conn.execute(f"CREATE VIRTUAL TABLE docs USING fts5(body, tokenize='{tokenizer}')")
        rejected = {raw: output for raw in queries if (output := _rejected_output(conn, raw))}

    assert not rejected, (
        f"{len(rejected)} of {len(queries)} outputs are not FTS5 syntax, first: {list(rejected.items())[:5]}"
    )


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
