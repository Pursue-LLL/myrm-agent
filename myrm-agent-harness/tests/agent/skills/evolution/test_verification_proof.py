"""VerificationProof deserialization."""

from __future__ import annotations

from myrm_agent_harness.agent.skills.evolution.core.types import VerificationProof


def test_verification_proof_ignores_a_stored_success_streak() -> None:
    stored = VerificationProof(is_verified=True).to_dict() | {"success_streak": 4}

    proof = VerificationProof.from_dict(stored)

    assert proof.is_verified is True
    assert "success_streak" not in proof.to_dict()
