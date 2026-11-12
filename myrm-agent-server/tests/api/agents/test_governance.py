"""Tests for the agent responsibility metadata fields on the response and update DTOs."""

from myrm_agent_harness.backends.profiles.types import AgentProfile
from pydantic import ValidationError

from app.api.agents._agent_response import _to_agent_response
from app.database.dto import AgentUpdate


def test_response_serializes_governance_fields() -> None:
    profile = AgentProfile(
        id="a1",
        display_name="A1",
        metadata={"responsibility_scope": "Scope", "owner_label": "Owner", "acceptance_criteria": ["Done"]},
    )
    response = _to_agent_response(profile)
    assert response.responsibility_scope == "Scope"
    assert response.owner_label == "Owner"
    assert response.acceptance_criteria == ["Done"]


def test_response_defaults_governance_fields() -> None:
    response = _to_agent_response(AgentProfile(id="a1", display_name="A1", metadata=None))
    assert response.responsibility_scope is None
    assert response.acceptance_criteria is None


def test_agent_update_accepts_governance_fields() -> None:
    update = AgentUpdate(responsibility_scope="Scope", owner_label="Owner", acceptance_criteria=["A", "B"])
    assert update.responsibility_scope == "Scope"
    assert update.acceptance_criteria == ["A", "B"]


def test_agent_update_rejects_oversized_governance_fields() -> None:
    try:
        AgentUpdate(acceptance_criteria=[f"item-{i}" for i in range(21)])
    except ValidationError:
        return
    raise AssertionError("acceptance_criteria over 20 items must be rejected")
