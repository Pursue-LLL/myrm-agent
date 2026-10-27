"""The part of a refusal result written for a person, cut from the notes that instruct the model."""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.model_directed_notes import (
    DIAGNOSTIC_OPEN,
    SYSTEM_NOTE_OPEN,
    user_facing_text,
)

_REASON = "Action rejected by user: use a dry run first"


def test_text_without_a_note_is_unchanged() -> None:
    assert user_facing_text(_REASON) == _REASON
    assert user_facing_text("") == ""


@pytest.mark.parametrize(
    "tail",
    [
        f"\n\n{SYSTEM_NOTE_OPEN}Do not run it again.]",
        f"\n\n{DIAGNOSTIC_OPEN}\nDiagnostic ID: abc\nInstruction: choose a branch",
        f"\n\n{SYSTEM_NOTE_OPEN}Do not run it again.]\n\n{DIAGNOSTIC_OPEN}\nReason Code: x",
        f"\n\n{DIAGNOSTIC_OPEN}\nReason Code: x\n\n{SYSTEM_NOTE_OPEN}Stop.]",
    ],
)
def test_everything_from_the_first_note_on_is_cut(tail: str) -> None:
    assert user_facing_text(_REASON + tail) == _REASON


def test_a_marker_inside_a_sentence_is_not_a_note() -> None:
    text = f"Tool said {SYSTEM_NOTE_OPEN}not a note] and {DIAGNOSTIC_OPEN} inline"
    assert user_facing_text(text) == text


def test_nothing_is_left_when_the_result_opens_with_a_note() -> None:
    assert user_facing_text(f"\n\n{SYSTEM_NOTE_OPEN}Stop.]") == ""
