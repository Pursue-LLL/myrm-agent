"""Conversation search output is redacted before any length cut touches it."""

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
