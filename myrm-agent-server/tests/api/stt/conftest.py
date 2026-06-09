"""STT API tests — routes depend on verify_voice_enabled (feature flags)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from myrm_agent_harness.core.features import _reset_for_testing

from tests.support.feature_flags import seed_voice_interaction_flags


@pytest.fixture(autouse=True)
def _voice_interaction_feature_flags() -> Iterator[None]:
    seed_voice_interaction_flags()
    yield
    _reset_for_testing()
