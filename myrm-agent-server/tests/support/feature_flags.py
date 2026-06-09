"""Harness feature-flag bootstrap for API tests that bypass app lifespan."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from myrm_agent_harness.core.features import _reset_for_testing, init_features


def seed_voice_interaction_flags() -> None:
    from app.services.features.registration import register_all_features

    _reset_for_testing()
    register_all_features()
    init_features(overrides={"voice_interaction": True})


@pytest.fixture
def voice_interaction_feature_flags() -> Iterator[None]:
    """Enable voice_interaction for routes guarded by verify_voice_enabled."""
    seed_voice_interaction_flags()
    yield
    _reset_for_testing()


