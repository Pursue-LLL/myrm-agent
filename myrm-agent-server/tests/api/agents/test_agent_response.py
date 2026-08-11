"""Tests for _to_agent_response allow_discovery serialization."""

from myrm_agent_harness.backends.profiles.types import AgentProfile

from app.api.agents._agent_response import _to_agent_response


def _profile(*, metadata: dict | None) -> AgentProfile:
    return AgentProfile(id="a1", display_name="Agent1", metadata=metadata)


def test_allow_discovery_false_is_serialized() -> None:
    response = _to_agent_response(
        _profile(metadata={"allow_discovery": False})
    )
    assert response.allow_discovery is False


def test_allow_discovery_true_is_serialized() -> None:
    response = _to_agent_response(
        _profile(metadata={"allow_discovery": True})
    )
    assert response.allow_discovery is True


def test_allow_discovery_defaults_true_when_missing() -> None:
    response = _to_agent_response(_profile(metadata=None))
    assert response.allow_discovery is True
