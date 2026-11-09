"""Tests for the L1 HTTP/3 (QUIC) retry lane of HttpFetcher.fetch and its hand-off to the engine ladder."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher import HttpFetcher
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType, FetchResult
from myrm_agent_harness.toolkits.web_fetch.probe.http3_probe import get_http3_retry_metrics
from myrm_agent_harness.toolkits.web_fetch.router.site_experience import SiteExperienceStore
from tests.toolkits.web_fetch._http3_support import blocked_result, success_result

pytestmark = pytest.mark.usefixtures("http3_env")


@pytest.fixture
def site_store(tmp_path: Path) -> SiteExperienceStore:
    return SiteExperienceStore(storage_path=tmp_path / "site_experience.json")


@pytest.mark.asyncio
async def test_http2_blocked_then_http3_retry_success(site_store: SiteExperienceStore) -> None:
    fetcher = HttpFetcher()
    calls: list[bool] = []

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        calls.append(use_http3)
        if use_http3:
            return success_result()
        return blocked_result()

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
            new=AsyncMock(return_value=True),
        ),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.get_global_site_experience_store",
            return_value=site_store,
        ),
    ):
        result = await fetcher.fetch("https://blocked.example/article")

    assert result is not None
    assert result.status_code == 200
    assert calls == [False, True]
    metrics = get_http3_retry_metrics()
    assert metrics["http3_retry_attempts"] == 1
    assert metrics["http3_retry_success"] == 1


@pytest.mark.asyncio
async def test_prefer_http3_skips_http2(site_store: SiteExperienceStore) -> None:
    site_store.set_prefer_http3("blocked.example")
    fetcher = HttpFetcher()
    calls: list[bool] = []

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        calls.append(use_http3)
        return success_result()

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
            new=AsyncMock(return_value=True),
        ),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.get_global_site_experience_store",
            return_value=site_store,
        ),
    ):
        result = await fetcher.fetch("https://blocked.example/article")

    assert result is not None
    assert calls == [True]


@pytest.mark.asyncio
async def test_prefer_http3_clears_on_quic_failure(site_store: SiteExperienceStore) -> None:
    site_store.set_prefer_http3("blocked.example")
    fetcher = HttpFetcher()

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        assert use_http3 is True
        return blocked_result()

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
            new=AsyncMock(return_value=True),
        ),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.get_global_site_experience_store",
            return_value=site_store,
        ),
    ):
        result = await fetcher.fetch("https://blocked.example/article")

    assert result is not None
    assert result.status_code == 403
    assert site_store.get_prefer_http3("blocked.example") is False


@pytest.mark.asyncio
async def test_proxy_pool_skips_http3_retry() -> None:
    proxy_pool = MagicMock()
    proxy_pool.get_next.return_value = MagicMock(to_url=lambda: "http://proxy.local:8080")
    fetcher = HttpFetcher(proxy_pool=proxy_pool)
    calls: list[bool] = []

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        calls.append(use_http3)
        return blocked_result()

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
            new=AsyncMock(return_value=True),
        ),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
    ):
        result = await fetcher.fetch("https://blocked.example/article")

    assert result is not None
    assert result.status_code == 403
    assert calls == [False]


@pytest.mark.asyncio
async def test_http3_retry_disabled_only_http2() -> None:
    fetcher = HttpFetcher()
    calls: list[bool] = []

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        calls.append(use_http3)
        return blocked_result()

    with (
        patch.dict("os.environ", {"MYRM_HTTP3_RETRY": "0"}),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
    ):
        result = await fetcher.fetch("https://blocked.example/article")

    assert result is not None
    assert result.status_code == 403
    assert calls == [False]


@pytest.mark.asyncio
async def test_http3_success_marks_site_experience(site_store: SiteExperienceStore) -> None:
    fetcher = HttpFetcher()

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        if use_http3:
            return success_result()
        return blocked_result()

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
            new=AsyncMock(return_value=True),
        ),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.get_global_site_experience_store",
            return_value=site_store,
        ),
    ):
        await fetcher.fetch("https://blocked.example/article")

    assert site_store.get_prefer_http3("blocked.example") is True


@pytest.mark.asyncio
async def test_engine_cache_metrics_exposes_http3_retry() -> None:
    engine = FetchEngine()
    metrics = engine.get_cache_metrics()
    assert "http3_retry" in metrics
    assert "http3_retry_attempts" in metrics["http3_retry"]
    assert "http3_retry_success" in metrics["http3_retry"]
    await engine.shutdown()


@pytest.mark.asyncio
async def test_fetch_engine_skips_browser_when_l1_http_succeeds() -> None:
    from langchain_core.documents import Document

    from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType

    engine = FetchEngine()
    browser_fetch = AsyncMock(return_value=None)

    async def mock_try_and_report(
        url: str,
        fetcher_type: FetcherType,
        **_kwargs: object,
    ) -> tuple[Document | None, bool, FetchResult | None]:
        if fetcher_type == FetcherType.HTTP:
            doc = Document(page_content="L1 success", metadata={"url": url})
            return doc, False, success_result()
        return None, True, None

    with (
        patch.object(engine, "_try_and_report", side_effect=mock_try_and_report),
        patch.object(engine._browser_fetcher, "fetch", browser_fetch),
    ):
        doc, _fetch_result = await engine._crawl_with_degradation("https://blocked.example/article")

    assert doc is not None
    assert doc.page_content == "L1 success"
    browser_fetch.assert_not_called()
    await engine.shutdown()


@pytest.mark.asyncio
async def test_fetch_http3_passes_impersonate_none(
    install_fake_scrapling: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MYRM_HTTP3_RETRY", "1")
    fetcher = HttpFetcher()
    install_fake_scrapling.return_value = blocked_result()

    with patch(
        "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
        new=AsyncMock(return_value=True),
    ):
        await fetcher.fetch("https://blocked.example/article")

    http3_calls = [call for call in install_fake_scrapling.call_args_list if call.kwargs.get("http3")]
    assert http3_calls
    assert http3_calls[0].kwargs.get("impersonate") is None


@pytest.mark.asyncio
async def test_http2_success_skips_http3_retry() -> None:
    fetcher = HttpFetcher()
    calls: list[bool] = []

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        calls.append(use_http3)
        return success_result()

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
            new=AsyncMock(return_value=True),
        ),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
    ):
        result = await fetcher.fetch("https://blocked.example/article")

    assert result is not None
    assert result.status_code == 200
    assert calls == [False]


@pytest.mark.asyncio
async def test_quic_unavailable_returns_http2_only() -> None:
    fetcher = HttpFetcher()
    calls: list[bool] = []

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        calls.append(use_http3)
        return blocked_result()

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
            new=AsyncMock(return_value=False),
        ),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
    ):
        result = await fetcher.fetch("https://blocked.example/article")

    assert result is not None
    assert result.status_code == 403
    assert calls == [False]


@pytest.mark.asyncio
async def test_http3_retry_failure_records_metric(site_store: SiteExperienceStore) -> None:
    fetcher = HttpFetcher()

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        return blocked_result()

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
            new=AsyncMock(return_value=True),
        ),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.get_global_site_experience_store",
            return_value=site_store,
        ),
    ):
        await fetcher.fetch("https://blocked.example/article")

    metrics = get_http3_retry_metrics()
    assert metrics["http3_retry_attempts"] == 1
    assert metrics["http3_retry_success"] == 0


@pytest.mark.asyncio
async def test_prefer_http3_false_when_quic_unavailable(site_store: SiteExperienceStore) -> None:
    site_store.set_prefer_http3("blocked.example")
    fetcher = HttpFetcher()
    calls: list[bool] = []

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        calls.append(use_http3)
        return success_result()

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
            new=AsyncMock(return_value=False),
        ),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.get_global_site_experience_store",
            return_value=site_store,
        ),
    ):
        result = await fetcher.fetch("https://blocked.example/article")

    assert result is not None
    assert calls == [False]


@pytest.mark.asyncio
async def test_http2_none_http3_returns_http3_result(site_store: SiteExperienceStore) -> None:
    fetcher = HttpFetcher()
    http3_only = success_result()

    async def fake_fetch_with_redirects(*_args: object, use_http3: bool, **_kwargs: object) -> FetchResult | None:
        if use_http3:
            return http3_only
        return None

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.is_quic_egress_available",
            new=AsyncMock(return_value=True),
        ),
        patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects),
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher.get_global_site_experience_store",
            return_value=site_store,
        ),
    ):
        result = await fetcher.fetch("https://blocked.example/article")

    assert result is http3_only


@pytest.mark.asyncio
async def test_fetch_engine_escalates_browser_when_l1_fails() -> None:
    from langchain_core.documents import Document

    engine = FetchEngine()
    browser_doc = Document(page_content="Browser fallback", metadata={"url": "https://blocked.example/article"})
    fetcher_types: list[FetcherType] = []

    async def mock_try_and_report(
        url: str,
        fetcher_type: FetcherType,
        **_kwargs: object,
    ) -> tuple[Document | None, bool, FetchResult | None]:
        fetcher_types.append(fetcher_type)
        if fetcher_type == FetcherType.HTTP:
            return None, True, blocked_result()
        if fetcher_type == FetcherType.BROWSER:
            return browser_doc, False, None
        return None, True, None

    with patch.object(engine, "_try_and_report", side_effect=mock_try_and_report):
        doc, _fetch_result = await engine._crawl_with_degradation("https://blocked.example/article")

    assert doc is not None
    assert doc.page_content == "Browser fallback"
    assert fetcher_types == [FetcherType.HTTP, FetcherType.BROWSER]
    await engine.shutdown()
