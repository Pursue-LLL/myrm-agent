"""A pooled execution unit is built for one credential track, so the fingerprint keeps the tracks apart.

The skill backend baked into a unit lists the credential-gated skills for its track; a turn on the other track must
rebuild instead of being served a unit that lists skills it holds no credential for.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security import CredentialTrack

from app.ai_agents.general_agent.agent import GeneralAgent
from app.core.types import ModelConfig
from app.services.agent.execution_cache.fingerprint import compute_execution_fingerprint


def _agent(track: CredentialTrack | None = None) -> GeneralAgent:
    model_cfg = ModelConfig(model="test-model", api_key="test-key", base_url="http://test")
    if track is None:
        return GeneralAgent(model_cfg=model_cfg, mcp_config=None)
    return GeneralAgent(model_cfg=model_cfg, mcp_config=None, credential_track=track)


def test_the_two_tracks_never_share_a_pooled_unit() -> None:
    assert compute_execution_fingerprint(_agent(CredentialTrack.PERSONAL)) != compute_execution_fingerprint(
        _agent(CredentialTrack.SHARED)
    )


def test_an_agent_without_a_track_is_on_the_personal_one() -> None:
    assert compute_execution_fingerprint(_agent()) == compute_execution_fingerprint(_agent(CredentialTrack.PERSONAL))


def test_the_fingerprint_of_one_track_is_stable() -> None:
    assert compute_execution_fingerprint(_agent(CredentialTrack.SHARED)) == compute_execution_fingerprint(
        _agent(CredentialTrack.SHARED)
    )
