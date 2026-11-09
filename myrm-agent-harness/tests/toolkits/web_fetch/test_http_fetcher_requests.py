"""Tests for the request layer of HttpFetcher: redirects, SSRF pinning, proxy pool, session vault, cache headers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.core.security.guards.url_allowlist import SSRFSecurityError
from myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher import HttpFetcher
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetchResult
from tests.toolkits.web_fetch._http3_support import success_result


@pytest.mark.asyncio
async def test_fetch_with_redirects_text_response(install_fake_scrapling: AsyncMock) -> None:
    fetcher = HttpFetcher()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.body = success_result().html.encode()
    mock_response.encoding = "utf-8"
    mock_response.url = "https://blocked.example/article"
    mock_response.headers = {"content-type": "text/html"}
    install_fake_scrapling.return_value = mock_response

    with patch.dict("os.environ", {"MYRM_ENABLE_SSRF_SHIELD": "false"}):
        result = await fetcher._fetch_with_redirects(
            "https://blocked.example/article",
            headers={},
            cookie_jar=None,
            enable_ssrf_shield=False,
            allowed_hosts=[],
            use_http3=False,
        )

    assert result is not None
    assert result.status_code == 200
    assert "Real article content" in result.html


@pytest.mark.asyncio
async def test_fetch_with_redirects_304(install_fake_scrapling: AsyncMock) -> None:
    fetcher = HttpFetcher()
    mock_response = MagicMock()
    mock_response.status = 304
    mock_response.body = b""
    mock_response.encoding = "utf-8"
    mock_response.url = "https://blocked.example/article"
    mock_response.headers = {"etag": "abc"}
    install_fake_scrapling.return_value = mock_response

    result = await fetcher._fetch_with_redirects(
        "https://blocked.example/article",
        headers={"If-None-Match": "abc"},
        cookie_jar=None,
        enable_ssrf_shield=False,
        allowed_hosts=[],
        use_http3=False,
    )

    assert result is not None
    assert result.status_code == 304


@pytest.mark.asyncio
async def test_fetch_with_redirects_binary_body(install_fake_scrapling: AsyncMock) -> None:
    fetcher = HttpFetcher()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.body = b"%PDF-1.4"
    mock_response.encoding = "utf-8"
    mock_response.url = "https://blocked.example/doc.pdf"
    mock_response.headers = {"content-type": "application/pdf"}
    install_fake_scrapling.return_value = mock_response

    result = await fetcher._fetch_with_redirects(
        "https://blocked.example/doc.pdf",
        headers={},
        cookie_jar=None,
        enable_ssrf_shield=False,
        allowed_hosts=[],
        use_http3=False,
    )

    assert result is not None
    assert result.raw_body == b"%PDF-1.4"


@pytest.mark.asyncio
async def test_fetch_forwards_cache_headers() -> None:
    fetcher = HttpFetcher()
    captured_headers: list[dict[str, str]] = []

    async def fake_fetch_with_redirects(
        _url: str,
        *,
        headers: dict[str, str],
        use_http3: bool,
        **_kwargs: object,
    ) -> FetchResult | None:
        captured_headers.append(headers.copy())
        return success_result() if not use_http3 else None

    with patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects):
        result = await fetcher.fetch(
            "https://blocked.example/article",
            etag='"abc123"',
            last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
        )

    assert result is not None
    assert captured_headers[0]["If-None-Match"] == '"abc123"'
    assert captured_headers[0]["If-Modified-Since"] == "Wed, 01 Jan 2025 00:00:00 GMT"


@pytest.mark.asyncio
async def test_fetch_with_redirects_follows_location(install_fake_scrapling: AsyncMock) -> None:
    fetcher = HttpFetcher()
    redirect_response = MagicMock()
    redirect_response.status = 302
    redirect_response.body = b""
    redirect_response.encoding = "utf-8"
    redirect_response.url = "https://blocked.example/old"
    redirect_response.headers = {"Location": "/article"}

    final_response = MagicMock()
    final_response.status = 200
    final_response.body = success_result().html.encode()
    final_response.encoding = "utf-8"
    final_response.url = "https://blocked.example/article"
    final_response.headers = {"content-type": "text/html"}

    install_fake_scrapling.side_effect = [redirect_response, final_response]

    result = await fetcher._fetch_with_redirects(
        "https://blocked.example/old",
        headers={},
        cookie_jar=None,
        enable_ssrf_shield=False,
        allowed_hosts=[],
        use_http3=False,
    )

    assert result is not None
    assert result.status_code == 200
    assert install_fake_scrapling.call_count == 2


@pytest.mark.asyncio
async def test_fetch_with_redirects_ssrf_blocked(install_fake_scrapling: AsyncMock) -> None:
    fetcher = HttpFetcher()

    with (
        patch(
            "myrm_agent_harness.toolkits.web_fetch.fetchers.target_guard.async_pin_url",
            new=AsyncMock(side_effect=SSRFSecurityError("blocked")),
        ),
        pytest.raises(SSRFSecurityError, match="blocked"),
    ):
        await fetcher._fetch_with_redirects(
            "http://127.0.0.1/internal",
            headers={},
            cookie_jar=None,
            enable_ssrf_shield=True,
            allowed_hosts=[],
            use_http3=False,
        )

    install_fake_scrapling.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_with_redirects_redirect_missing_location(install_fake_scrapling: AsyncMock) -> None:
    fetcher = HttpFetcher()
    redirect_response = MagicMock()
    redirect_response.status = 302
    redirect_response.body = b""
    redirect_response.encoding = "utf-8"
    redirect_response.url = "https://blocked.example/old"
    redirect_response.headers = {}
    install_fake_scrapling.return_value = redirect_response

    result = await fetcher._fetch_with_redirects(
        "https://blocked.example/old",
        headers={},
        cookie_jar=None,
        enable_ssrf_shield=False,
        allowed_hosts=[],
        use_http3=False,
    )

    assert result is None


@pytest.mark.asyncio
async def test_fetch_with_redirects_too_many_redirects(install_fake_scrapling: AsyncMock) -> None:
    fetcher = HttpFetcher()
    redirect_response = MagicMock()
    redirect_response.status = 302
    redirect_response.body = b""
    redirect_response.encoding = "utf-8"
    redirect_response.url = "https://blocked.example/loop"
    redirect_response.headers = {"Location": "/loop"}
    install_fake_scrapling.return_value = redirect_response

    result = await fetcher._fetch_with_redirects(
        "https://blocked.example/loop",
        headers={},
        cookie_jar=None,
        enable_ssrf_shield=False,
        allowed_hosts=[],
        use_http3=False,
    )

    assert result is None
    assert install_fake_scrapling.call_count == 6


@pytest.mark.asyncio
async def test_fetch_with_redirects_async_fetcher_exception(install_fake_scrapling: AsyncMock) -> None:
    fetcher = HttpFetcher()
    install_fake_scrapling.side_effect = RuntimeError("network down")

    result = await fetcher._fetch_with_redirects(
        "https://blocked.example/article",
        headers={},
        cookie_jar=None,
        enable_ssrf_shield=False,
        allowed_hosts=[],
        use_http3=False,
    )

    assert result is None


@pytest.mark.asyncio
async def test_proxy_pool_injects_proxy_kwarg(install_fake_scrapling: AsyncMock) -> None:
    proxy_pool = MagicMock()
    proxy_pool.get_next.return_value = MagicMock(to_url=lambda: "http://proxy.local:8080")
    fetcher = HttpFetcher(proxy_pool=proxy_pool)

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.body = success_result().html.encode()
    mock_response.encoding = "utf-8"
    mock_response.url = "https://blocked.example/article"
    mock_response.headers = {"content-type": "text/html"}
    install_fake_scrapling.return_value = mock_response

    with patch.dict("os.environ", {"MYRM_ENABLE_SSRF_SHIELD": "false", "MYRM_HTTP3_RETRY": "0"}):
        await fetcher.fetch("https://blocked.example/article")

    assert install_fake_scrapling.call_args.kwargs["proxy"] == "http://proxy.local:8080"


@pytest.mark.asyncio
async def test_session_vault_load_failure_returns_none() -> None:
    mock_vault = MagicMock()
    mock_vault.load = AsyncMock(side_effect=RuntimeError("vault unavailable"))
    fetcher = HttpFetcher(session_vault=mock_vault)

    async def fake_fetch_with_redirects(*_args: object, **_kwargs: object) -> FetchResult | None:
        return success_result()

    with patch.object(fetcher, "_fetch_with_redirects", side_effect=fake_fetch_with_redirects):
        result = await fetcher.fetch("https://blocked.example/article")

    assert result is not None


@pytest.mark.asyncio
async def test_session_vault_empty_entry_skips_cookies(install_fake_scrapling: AsyncMock) -> None:
    mock_vault = MagicMock()
    mock_vault.load = AsyncMock(return_value=None)
    fetcher = HttpFetcher(session_vault=mock_vault)

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.body = success_result().html.encode()
    mock_response.encoding = "utf-8"
    mock_response.url = "https://blocked.example/article"
    mock_response.headers = {"content-type": "text/html"}
    install_fake_scrapling.return_value = mock_response

    with patch.dict("os.environ", {"MYRM_ENABLE_SSRF_SHIELD": "false", "MYRM_HTTP3_RETRY": "0"}):
        await fetcher.fetch("https://blocked.example/article")

    assert "cookies" not in install_fake_scrapling.call_args.kwargs


@pytest.mark.asyncio
async def test_fetch_with_redirects_ssrf_rewrites_url(install_fake_scrapling: AsyncMock) -> None:
    fetcher = HttpFetcher()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.body = success_result().html.encode()
    mock_response.encoding = "utf-8"
    mock_response.url = "https://blocked.example/article"
    mock_response.headers = {"content-type": "text/html"}
    install_fake_scrapling.return_value = mock_response

    with patch(
        "myrm_agent_harness.toolkits.web_fetch.fetchers.target_guard.async_pin_url",
        new=AsyncMock(return_value=("https://10.0.0.1/safe", {"Host": "blocked.example"})),
    ):
        result = await fetcher._fetch_with_redirects(
            "https://blocked.example/article",
            headers={},
            cookie_jar=None,
            enable_ssrf_shield=True,
            allowed_hosts=["blocked.example"],
            use_http3=False,
        )

    assert result is not None
    assert install_fake_scrapling.call_args.args[0] == "https://10.0.0.1/safe"


@pytest.mark.asyncio
async def test_fetch_with_redirects_pinned_ip_tls_mismatch_fallback(install_fake_scrapling: AsyncMock) -> None:
    fetcher = HttpFetcher()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.body = success_result().html.encode()
    mock_response.encoding = "utf-8"
    mock_response.url = "https://blocked.example/article"
    mock_response.headers = {"content-type": "text/html"}

    # First call with pinned IP fails with TLS error, second call with domain succeeds
    install_fake_scrapling.side_effect = [
        Exception("curl: (60) SSL: no alternative certificate subject name"),
        mock_response,
    ]

    with patch(
        "myrm_agent_harness.toolkits.web_fetch.fetchers.target_guard.async_pin_url",
        new=AsyncMock(return_value=("https://10.0.0.1/safe", {"Host": "blocked.example"})),
    ):
        result = await fetcher._fetch_with_redirects(
            "https://blocked.example/article",
            headers={},
            cookie_jar=None,
            enable_ssrf_shield=True,
            allowed_hosts=["blocked.example"],
            use_http3=False,
        )

    assert result is not None
    assert install_fake_scrapling.call_count == 2
    assert install_fake_scrapling.call_args_list[0].args[0] == "https://10.0.0.1/safe"
    assert install_fake_scrapling.call_args_list[1].args[0] == "https://blocked.example/article"
