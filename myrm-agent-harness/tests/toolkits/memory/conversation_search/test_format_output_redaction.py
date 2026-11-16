"""Conversation search output is redacted before anything alters or cuts it."""

from __future__ import annotations

import base64
import hashlib

import pytest

from myrm_agent_harness.toolkits.memory.conversation_search.format_output import format_conversation_hit
from myrm_agent_harness.toolkits.memory.conversation_search.types import (
    MAX_EXPANDED_SNIPPET_CHARS,
    MAX_SNIPPET_CHARS,
    ConversationSearchHit,
)


def _private_key_block() -> tuple[str, list[str]]:
    """A PEM-shaped block assembled at run time, with its body rows."""
    rows = [base64.b64encode(hashlib.sha256(str(i).encode()).digest() * 2).decode()[:64] for i in range(25)]
    begin, end = "-----BEGIN " + "RSA PRIVATE KEY-----", "-----END " + "RSA PRIVATE KEY-----"
    return "\n".join([begin, *rows, end]), rows


def _token() -> str:
    """A GitHub-token-shaped credential assembled at run time."""
    return "ghp_" + hashlib.sha256(b"conversation-search").hexdigest()[:36]


def _snippet_line(snippet: str, *, is_expanded: bool = False) -> str:
    hit = ConversationSearchHit(conversation_id="chat-1", message_id="msg-1", snippet=snippet, score=1.0)
    text = format_conversation_hit(1, hit, is_expanded=is_expanded)
    return next(line for line in text.splitlines() if line.startswith("snippet: "))


def _exposes_a_row(line: str, rows: list[str]) -> bool:
    return any(row[:16] in line for row in rows)


@pytest.mark.parametrize(
    ("is_expanded", "limit"),
    [(False, MAX_SNIPPET_CHARS), (True, MAX_EXPANDED_SNIPPET_CHARS)],
    ids=["snippet", "expanded"],
)
def test_a_private_key_block_the_length_cut_would_split_is_masked_whole(is_expanded: bool, limit: int) -> None:
    block, rows = _private_key_block()

    # The cut falls 300 chars into the block.
    line = _snippet_line("w" * (limit - 300) + " " + block + " " + "tail " * 400, is_expanded=is_expanded)

    assert "w" * (limit - 300) in line
    assert not _exposes_a_row(line, rows)
    assert line.endswith("...")


def test_a_block_that_redaction_shrinks_below_the_limit_is_shown_whole() -> None:
    block, rows = _private_key_block()

    line = _snippet_line(f"before {block} after")

    assert line.startswith("snippet: before ")
    assert line.endswith(" after")
    assert not _exposes_a_row(line, rows)


def test_the_redaction_window_edge_never_exposes_the_start_of_a_private_key_block() -> None:
    block, rows = _private_key_block()

    # Twelve blocks outrun the redaction window, and masking them leaves the window edge inside the visible text.
    line = _snippet_line(" ".join([block] * 12), is_expanded=True)

    assert not _exposes_a_row(line, rows)
    assert line.endswith("...")


def test_a_line_anchored_credential_is_masked_before_whitespace_is_collapsed() -> None:
    stored = "database:\n  host: db.internal\n  password: Zk3Qm8Vt2Lp9Xw4R\n  port: 5432\n"

    line = _snippet_line(stored)

    assert "Zk3Qm8Vt2Lp9Xw4R" not in line
    assert "password: ***" in line
    assert line == "snippet: database: host: db.internal password: *** port: 5432"


def test_whitespace_heavy_text_still_fills_the_snippet_limit() -> None:
    line = _snippet_line("word    \n\n  " * 8000)

    assert len(line) >= len("snippet: ") + MAX_SNIPPET_CHARS - 1
    assert line.endswith("...")


def test_a_title_naming_a_credential_is_masked() -> None:
    token = _token()
    hit = ConversationSearchHit(
        conversation_id="chat-1", title=f"deploy with {token} today", snippet="notes", score=1.0
    )

    header = format_conversation_hit(1, hit).splitlines()[0]

    assert token not in header
    assert header.startswith("1. deploy with ghp_")
    assert "(conversation_id: chat-1" in header
