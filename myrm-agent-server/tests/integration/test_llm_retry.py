"""Integration tests for LLM empty response retry mechanism.

Tests verify:
- Retry mechanism doesn't affect normal requests
- Metrics API is accessible
- Metrics export to dict works
"""

import os

import pytest
from myrm_agent_harness.toolkits.llms import ChatLiteLLM

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("BASIC_API_KEY")
_TEST_MODEL = os.environ.get("BASIC_MODEL", "gpt-4o-mini")


@pytest.mark.asyncio
@pytest.mark.skipif(not OPENAI_API_KEY, reason="OPENAI_API_KEY or BASIC_API_KEY not set")
async def test_normal_request_with_retry_enabled():
    """Test normal LLM request with retry enabled (doesn't trigger retry)."""
    # Create LLM with retry enabled
    llm = ChatLiteLLM(
        model=_TEST_MODEL,
        openai_api_key=OPENAI_API_KEY,
        empty_retry_enabled=True,
        empty_retry_max_attempts=3,
        empty_retry_delay=0.5,
    )

    # Make a normal request
    import litellm
    from langchain_core.messages import HumanMessage

    messages = [HumanMessage(content="Say 'test' only")]
    try:
        result = await llm.ainvoke(messages)
    except litellm.AuthenticationError as e:
        pytest.skip(f"Skipping due to AuthenticationError with provided key: {e}")

    # Verify response is valid
    assert result is not None
    assert result.content  # Should have content

    # Verify metrics exist and show no retries (normal scenario)
    metrics = llm.retry_metrics
    assert metrics is not None
    assert metrics.get_total_retries() == 0  # No retries in normal scenario
    assert metrics.get_total_successes() == 0  # No retry successes (first attempt succeeded)


def test_retry_metrics_api():
    """Test retry metrics API and export."""
    llm = ChatLiteLLM(model=_TEST_MODEL)

    # Verify retry_metrics property exists
    metrics = llm.retry_metrics
    assert metrics is not None

    # Verify to_dict export works
    metrics_dict = metrics.to_dict()
    assert isinstance(metrics_dict, dict)
    assert "sync_retry_count" in metrics_dict
    assert "async_retry_count" in metrics_dict
    assert "stream_retry_count" in metrics_dict
    assert "total_retry_delay_ms" in metrics_dict

    # Verify helper methods
    assert metrics.get_total_retries() == 0
    assert metrics.get_total_successes() == 0
    assert metrics.get_success_rate() == 0.0
    assert metrics.get_avg_retry_delay_ms() == 0.0


def test_retry_config_validation():
    """Test retry configuration validation."""
    # Valid config
    llm = ChatLiteLLM(
        model=_TEST_MODEL,
        empty_retry_enabled=True,
        empty_retry_max_attempts=5,
        empty_retry_delay=1.0,
    )
    assert llm.empty_retry_enabled is True
    assert llm.empty_retry_max_attempts == 5
    assert llm.empty_retry_delay == 1.0

    # Invalid max_attempts (too high)
    with pytest.raises(ValueError):
        ChatLiteLLM(
            model=_TEST_MODEL,
            empty_retry_max_attempts=11,  # Max is 10
        )

    # Invalid delay (too low)
    with pytest.raises(ValueError):
        ChatLiteLLM(
            model=_TEST_MODEL,
            empty_retry_delay=0.05,  # Min is 0.1
        )
