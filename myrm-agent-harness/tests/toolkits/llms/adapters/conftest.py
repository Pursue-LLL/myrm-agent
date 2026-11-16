"""Fixtures for the adapter tests that touch process-wide output-cap state."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from myrm_agent_harness.toolkits.llms.adapters.chat_model import output_cap_recovery
from myrm_agent_harness.toolkits.llms.ephemeral_output_tokens import reset_ephemeral_max_output_tokens


@pytest.fixture
def isolated_ceiling_memo() -> Iterator[None]:
    """The learned-ceiling memo is process-wide; every test starts and ends with it empty."""
    saved = dict(output_cap_recovery._LEARNED_CEILINGS)
    output_cap_recovery._LEARNED_CEILINGS.clear()
    reset_ephemeral_max_output_tokens()
    yield
    output_cap_recovery._LEARNED_CEILINGS.clear()
    output_cap_recovery._LEARNED_CEILINGS.update(saved)
    reset_ephemeral_max_output_tokens()
