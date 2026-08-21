"""Unit tests for Pre-Publish Outbound Content Gate."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.core.outbound_gate import (
    LinkProbeResult,
    OutboundContentGate,
    get_outbound_content_gate,
)
from app.channels.types.messages import OutboundMessage


@pytest.fixture
def gate() -> OutboundContentGate:
    return OutboundContentGate(timeout_seconds=0.5, cache_ttl_seconds=60.0)


def _make_msg(content: str, metadata: dict[str, object] | None = None) -> OutboundMessage:
    return OutboundMessage(
        channel="telegram",
        recipient_id="chat-1",
        content=content,
        user_id="user-1",
        metadata=metadata,
    )


def test_url_extraction(gate: OutboundContentGate) -> None:
    text = (
        "Check this out: https://example.com/docs, and also http://test.org/api?key=123! "
        "Trailing punctuation: https://github.com/myrm/repo. "
        "<https://bracketed.com/path> and (https://paren.org/doc)"
    )
    urls = gate.extract_urls(text)
    assert "https://example.com/docs" in urls
    assert "http://test.org/api?key=123" in urls
    assert "https://github.com/myrm/repo" in urls
    assert "https://bracketed.com/path" in urls
    assert "https://paren.org/doc" in urls


@pytest.mark.asyncio
async def test_trusted_host_fast_path(gate: OutboundContentGate) -> None:
    res = await gate.probe_url("https://github.com/open-perplexity/myrm")
    assert res.is_alive is True
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_probe_cache_hit(gate: OutboundContentGate) -> None:
    url = "https://custom-mock-site.org/alive"
    mock_result = LinkProbeResult(url=url, is_alive=True, status_code=200)

    with patch.object(gate, "_network_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = mock_result

        # First call: hits network probe
        res1 = await gate.probe_url(url)
        assert res1.is_alive is True
        assert mock_probe.call_count == 1

        # Second call: hits cache
        res2 = await gate.probe_url(url)
        assert res2.is_alive is True
        assert mock_probe.call_count == 1


@pytest.mark.asyncio
async def test_interactive_chat_warning_on_dead_link(gate: OutboundContentGate) -> None:
    msg = _make_msg("Read more at https://dead-domain-xyz.org/doc404 here.")

    with patch.object(gate, "probe_url", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = LinkProbeResult(
            url="https://dead-domain-xyz.org/doc404",
            is_alive=False,
            status_code=404,
            error="HTTP 404",
        )

        result_msg = await gate.evaluate_and_apply(msg)
        assert result_msg is not None
        assert "Read more at https://dead-domain-xyz.org/doc404" in result_msg.content
        assert "dead-domain-xyz.org/doc404" in result_msg.content


@pytest.mark.asyncio
async def test_cron_fail_closed_hold_on_dead_link(gate: OutboundContentGate) -> None:
    cron_metadata = {"cron_context": {"job_name": "daily_report"}, "job_id": "cron-123"}
    msg = _make_msg("Morning brief: https://broken-link.com/post", metadata=cron_metadata)

    with patch.object(gate, "probe_url", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = LinkProbeResult(
            url="https://broken-link.com/post",
            is_alive=False,
            status_code=404,
            error="HTTP 404",
        )

        result = await gate.evaluate_and_apply(msg)
        assert result is None  # Fail-Closed HOLD


@pytest.mark.asyncio
async def test_passthrough_when_all_links_alive(gate: OutboundContentGate) -> None:
    cron_metadata = {"cron_context": {"job_name": "daily_report"}}
    msg = _make_msg("Morning brief: https://example.com/ok", metadata=cron_metadata)

    with patch.object(gate, "probe_url", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = LinkProbeResult(
            url="https://example.com/ok",
            is_alive=True,
            status_code=200,
        )

        result = await gate.evaluate_and_apply(msg)
        assert result is msg
