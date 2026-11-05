"""Fixtures for the length-truncation recovery tests."""

import asyncio
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.streaming.stream_executor import (
    StreamContext,
)
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.toolkits.llms.utils import model_utils


@pytest.fixture(autouse=True)
def _unmapped_output_ceilings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin every model to "ceiling unknown": boost expectations must not depend on the model catalog."""
    monkeypatch.setattr(model_utils, "get_model_output_ceiling", lambda _model: None)


@pytest.fixture
def mock_context():
    stats = AgentRunStatistics()
    ctx = StreamContext(
        agent=None,
        agent_input={},
        merged_context={"locale": "en"},
        run_config={},
        stats=stats,
        message_id="test_msg_id",
        cancel_token=None,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
    )
    return ctx
