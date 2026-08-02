"""Unit tests for FAQ router helper functions."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.api.faq.router import _entry_to_response
from app.api.faq.schemas import FaqEntryResponse
from app.database.models.faq import FaqEntry


def _make_entry(**overrides: object) -> MagicMock:
    now = datetime.now(tz=timezone.utc)
    defaults = dict(
        id="entry-abc",
        corpus_id="corpus-xyz",
        question="How to login?",
        answer="Click the Login button.",
        tags="auth",
        sort_order=0,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    entry = MagicMock(spec=FaqEntry)
    for k, v in defaults.items():
        setattr(entry, k, v)
    return entry


def test_entry_to_response_basic() -> None:
    entry = _make_entry()
    resp = _entry_to_response(entry)

    assert isinstance(resp, FaqEntryResponse)
    assert resp.id == "entry-abc"
    assert resp.corpus_id == "corpus-xyz"
    assert resp.question == "How to login?"
    assert resp.answer == "Click the Login button."
    assert resp.tags == "auth"
    assert resp.sort_order == 0
    assert resp.created_at == entry.created_at.isoformat()
    assert resp.updated_at == entry.updated_at.isoformat()


def test_entry_to_response_empty_tags() -> None:
    entry = _make_entry(tags="")
    resp = _entry_to_response(entry)
    assert resp.tags == ""


def test_entry_to_response_high_sort_order() -> None:
    entry = _make_entry(sort_order=999)
    resp = _entry_to_response(entry)
    assert resp.sort_order == 999
