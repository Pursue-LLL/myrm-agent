"""``ContextDocument``: the body a channel attaches to a turn, and how it travels in message metadata."""

from __future__ import annotations

import json

import pytest

from app.channels.types import ContextDocument, ContextDocumentStatus


@pytest.mark.parametrize("status", list(ContextDocumentStatus))
def test_every_status_survives_the_metadata_round_trip(status: ContextDocumentStatus) -> None:
    document = ContextDocument.ready("# Plan\nbody") if status is ContextDocumentStatus.READY else ContextDocument(status)

    assert ContextDocument.from_metadata(document.as_metadata()) == document


def test_metadata_form_is_plain_json_data() -> None:
    """The inbound journal and the data-plane ledger serialize message metadata as JSON."""
    document = ContextDocument.ready("# Plan\n正文")

    assert ContextDocument.from_metadata(json.loads(json.dumps(document.as_metadata()))) == document


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "ready",
        [],
        {},
        {"status": "ready"},
        {"status": "bogus", "markdown": "", "total_chars": 0},
        {"status": "ready", "markdown": 1, "total_chars": 0},
        {"status": "ready", "markdown": "", "total_chars": "3"},
    ],
)
def test_anything_but_the_metadata_form_is_not_a_document(raw: object) -> None:
    assert ContextDocument.from_metadata(raw) is None


def test_clamped_cuts_the_body_and_keeps_the_original_length() -> None:
    document = ContextDocument.ready("a" * 10).clamped(4)

    assert document.markdown == "aaaa"
    assert document.total_chars == 10
    assert document.is_shortened


def test_a_body_within_the_limit_is_returned_as_is() -> None:
    document = ContextDocument.ready("a" * 10)

    assert document.clamped(10) is document
    assert not document.is_shortened
