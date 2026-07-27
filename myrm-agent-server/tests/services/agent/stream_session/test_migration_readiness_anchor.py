from __future__ import annotations

from app.services.agent.stream_session.migration_readiness_anchor import (
    resolve_first_turn_outcome,
)


def test_resolve_first_turn_outcome_failed_on_fatal_error() -> None:
    assert resolve_first_turn_outcome(had_fatal_error=True, has_assistant_content=True) == "failed"


def test_resolve_first_turn_outcome_success_with_content() -> None:
    assert resolve_first_turn_outcome(had_fatal_error=False, has_assistant_content=True) == "success"


def test_resolve_first_turn_outcome_no_output_without_content() -> None:
    assert resolve_first_turn_outcome(had_fatal_error=False, has_assistant_content=False) == "no_output"
