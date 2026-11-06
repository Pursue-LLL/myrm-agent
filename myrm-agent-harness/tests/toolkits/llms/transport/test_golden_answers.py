"""Golden answers test: every recorded provider answer is read as the previous stack read it, except where registered.

[INPUT]
- golden_answers (POS: replays the recorded answers through the chat adapter on the installed stack)
- golden_answers_baseline.json (POS: the answers and the message the previous stack returned for each)
- golden_answers_allowed (POS: registry of intended differences)
- golden_compare (POS: comparison engine)

[OUTPUT]
- tests that fail on any unregistered difference, on a registered difference whose facts changed, and on a registry
  entry that matches nothing

[POS]
Safety net for what a user sees and what a turn costs. 121 answers of the OpenAI, Anthropic, Gemini and Ollama wires
(plain, server-sent-event and NDJSON bodies; tool calls, cache and reasoning usage, thinking blocks, blocked prompts,
cut-off outputs, and bodies that are no answer) must yield the same text, tool calls, finish reason, token counts and
raise-or-return outcome as before the stack was replaced.
"""

from __future__ import annotations

import pytest

from .golden_answers import AnswerCase, load_baseline, recorded, replay_answers
from .golden_answers_allowed import ANSWER_ALLOWED
from .golden_compare import Report, compare


@pytest.fixture(scope="module")
def baseline() -> dict[str, AnswerCase]:
    return load_baseline()


@pytest.fixture(scope="module")
def report(baseline: dict[str, AnswerCase]) -> Report:
    return compare({name: recorded(case) for name, case in baseline.items()}, replay_answers(baseline), ANSWER_ALLOWED)


def test_the_recording_keeps_every_case(baseline: dict[str, AnswerCase]) -> None:
    """A case cannot leave the contract unnoticed: removing one from the file changes this count."""
    assert len(baseline) == 121


def test_every_answer_is_read_as_before_or_registered(report: Report) -> None:
    assert not report.unexplained, f"{len(report.unexplained)} answers:\n{report.describe()}"


def test_the_registry_has_no_stale_entries(report: Report) -> None:
    assert not report.stale, f"registered differences that no longer occur: {report.stale}"
