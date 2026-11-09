"""Tests for the HTTP/3 enablement flag, the QUIC egress probe and the HTTP/3 retry predicates of HttpFetcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher import HttpFetcher
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType, FetchResult
from tests.toolkits.web_fetch._http3_support import blocked_result, success_result

pytestmark = pytest.mark.usefixtures("http3_env")


def test_should_retry_with_http3_on_403_and_antibot_not_429() -> None:
    fetcher = HttpFetcher()
    assert fetcher._should_retry_with_http3(blocked_result()) is True
    assert fetcher._should_retry_with_http3(blocked_result(status=429)) is False
    assert fetcher._should_retry_with_http3(None) is True
    assert fetcher._should_retry_with_http3(success_result()) is False
    assert fetcher._should_retry_with_http3(blocked_result(status=404)) is False


@pytest.mark.asyncio
async def test_http3_probe_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from myrm_agent_harness.toolkits.web_fetch.probe.http3_probe import is_http3_retry_enabled, is_quic_egress_available

    monkeypatch.delenv("MYRM_HTTP3_RETRY", raising=False)
    assert is_http3_retry_enabled() is False
    assert await is_quic_egress_available() is False


@pytest.mark.asyncio
async def test_http3_probe_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from myrm_agent_harness.toolkits.web_fetch.probe import http3_probe

    monkeypatch.setenv("MYRM_HTTP3_RETRY", "1")
    http3_probe.reset_http3_state_for_tests()

    with patch.object(http3_probe, "_probe_quic_egress", new=AsyncMock(return_value=True)):
        assert await http3_probe.is_quic_egress_available() is True

    http3_probe.reset_http3_state_for_tests()
    with patch.object(http3_probe, "_probe_quic_egress", new=AsyncMock(return_value=False)):
        assert await http3_probe.is_quic_egress_available() is False


def test_extract_domain_strips_www() -> None:
    assert HttpFetcher._extract_domain("https://www.blocked.example/path") == "blocked.example"


def test_should_retry_with_http3_branches() -> None:
    fetcher = HttpFetcher()
    not_modified = FetchResult(
        html="",
        url="https://blocked.example/article",
        status_code=304,
        fetcher_type=FetcherType.HTTP,
    )
    assert fetcher._should_retry_with_http3(not_modified) is False

    pdf_result = FetchResult(
        html="",
        url="https://blocked.example/doc.pdf",
        status_code=200,
        fetcher_type=FetcherType.HTTP,
        raw_body=b"%PDF-1.4",
    )
    assert fetcher._should_retry_with_http3(pdf_result) is False

    empty_shell = FetchResult(
        html="<html><body></body></html>",
        url="https://blocked.example/article",
        status_code=200,
        fetcher_type=FetcherType.HTTP,
    )
    assert fetcher._should_retry_with_http3(empty_shell) is True


@pytest.mark.asyncio
async def test_http3_probe_uses_cached_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from myrm_agent_harness.toolkits.web_fetch.probe import http3_probe

    monkeypatch.setenv("MYRM_HTTP3_RETRY", "1")
    http3_probe.reset_http3_state_for_tests()
    probe = AsyncMock(return_value=True)

    with patch.object(http3_probe, "_probe_quic_egress", probe):
        assert await http3_probe.is_quic_egress_available() is True
        assert await http3_probe.is_quic_egress_available() is True

    probe.assert_awaited_once()


@pytest.mark.asyncio
async def test_http3_probe_real_exception_path(install_fake_scrapling: AsyncMock) -> None:
    from myrm_agent_harness.toolkits.web_fetch.probe import http3_probe

    install_fake_scrapling.side_effect = RuntimeError("quic blocked")
    assert await http3_probe._probe_quic_egress() is False


def test_is_http3_retry_enabled_truthy_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    from myrm_agent_harness.toolkits.web_fetch.probe.http3_probe import is_http3_retry_enabled

    monkeypatch.setenv("MYRM_HTTP3_RETRY", "true")
    assert is_http3_retry_enabled() is True
    monkeypatch.setenv("MYRM_HTTP3_RETRY", "yes")
    assert is_http3_retry_enabled() is True
