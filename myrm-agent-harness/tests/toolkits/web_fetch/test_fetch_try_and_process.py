"""Tests for ``FetchEngine._try_fetch_and_process`` result handling.

Covers 304, non-degradable 4xx, empty shell, binary bodies, weixin fast path, anti-bot detection,
truncation events, browser launch mode and the resource-sampling fallbacks.
"""

from __future__ import annotations

import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import (
    FetcherType,
    FetchResult,
)
from tests.toolkits.web_fetch._degradation_support import (
    RICH_HTML,
    http_result,
    make_document,
    make_engine,
    stub_fetchers,
)


class TestTryFetchAndProcess:
    @pytest.mark.asyncio
    async def test_http_304_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result("", status=304)

            doc, degradable, _, _, _, result = await engine._try_fetch_and_process(
                "http://example.com/page", FetcherType.HTTP, etag="abc"
            )

            assert doc is None
            assert degradable is False
            assert result is not None and result.status_code == 304
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_http_4xx_non_degradable_aborts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result("", status=404)

            doc, degradable, _, _, _, result = await engine._try_fetch_and_process(
                "http://example.com/page", FetcherType.HTTP
            )

            assert doc is None
            assert degradable is False
            assert result is None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_http_empty_shell_degrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result("<html><head></head></html>")

            doc, degradable, _, _, _, _ = await engine._try_fetch_and_process(
                "http://example.com/page", FetcherType.HTTP
            )

            assert doc is None
            assert degradable is True
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_fetcher_none_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = None

            doc, degradable, _, _, _, result = await engine._try_fetch_and_process(
                "http://example.com/page", FetcherType.HTTP
            )

            assert doc is None
            assert degradable is True
            assert result is None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_binary_body_routed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = FetchResult(
                html=RICH_HTML,
                url="http://example.com/img.png",
                raw_body=b"\x89PNG\r\n",
                headers={"content-type": "image/png"},
            )
            with patch(
                "myrm_agent_harness.toolkits.web_fetch.processing.binary_router.route_binary_content",
                new=AsyncMock(return_value=make_document("binary")),
            ):
                doc, degradable, _, _, _, result = await engine._try_fetch_and_process(
                    "http://example.com/img.png", FetcherType.HTTP
                )

                assert doc is not None
                assert doc.page_content == "binary"
                assert degradable is False
                assert result is not None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_weixin_url_parsed_fastpath(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result(RICH_HTML)
            url = "https://mp.weixin.qq.com/s/abc123"
            with patch(
                "myrm_agent_harness.toolkits.web_fetch.extractors.weixin_extractor.parse_weixin_article_html",
                new=lambda html, url=None: make_document("weixin"),
            ):
                doc, degradable, _, _, _, _ = await engine._try_fetch_and_process(url, FetcherType.HTTP)

                assert doc is not None
                assert doc.page_content == "weixin"
                assert degradable is False
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_weixin_without_js_content_degrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result("<html>shell</html>")
            url = "https://mp.weixin.qq.com/s/abc123"
            with (
                patch(
                    "myrm_agent_harness.toolkits.web_fetch.extractors.weixin_extractor.parse_weixin_article_html",
                    new=lambda html, url=None: None,
                ),
                patch(
                    "myrm_agent_harness.toolkits.web_fetch.extractors.weixin_extractor.has_weixin_js_content",
                    new=lambda html: False,
                ),
            ):
                doc, degradable, _, _, _, _ = await engine._try_fetch_and_process(url, FetcherType.HTTP)

                assert doc is None
                assert degradable is True
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_antibot_detected_degrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result(RICH_HTML, status=503)
            with patch(
                "myrm_agent_harness.toolkits.web_fetch.engine.fetch_mixin.detect_antibot",
                new=lambda status, html: (True, "challenge"),
            ):
                doc, degradable, _, _, _, result = await engine._try_fetch_and_process(
                    "http://example.com/page", FetcherType.HTTP
                )

                assert doc is None
                assert degradable is True
                assert result is None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_pipeline_doc_returns_with_truncation_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result(RICH_HTML)
            truncated = make_document("truncated content")
            truncated.metadata["was_truncated"] = True
            engine._pipeline.aprocess.return_value = truncated
            with patch(
                "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
                new=AsyncMock(return_value=None),
            ):
                doc, degradable, _, _, _, result = await engine._try_fetch_and_process(
                    "http://example.com/page", FetcherType.HTTP
                )

                assert doc is not None
                assert degradable is True
                assert result is not None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_browser_launch_mode_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            _, browser, _ = stub_fetchers(engine)
            browser.set_launch_mode_preference = MagicMock()
            browser.fetch.return_value = http_result(RICH_HTML)

            with patch(
                "myrm_agent_harness.toolkits.web_fetch.escalation.context.get_bound_browser_launch_mode",
                new=lambda: "EXTENSION",
            ):
                await engine._try_fetch_and_process("http://example.com/page", FetcherType.BROWSER)

                browser.set_launch_mode_preference.assert_called_once_with("EXTENSION")
            await engine.shutdown()


class TestFetchMixinRemaining:
    @pytest.mark.asyncio
    async def test_weixin_with_js_content_continues_generic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result(RICH_HTML)
            engine._pipeline.aprocess.return_value = make_document("generic")
            with (
                patch(
                    "myrm_agent_harness.toolkits.web_fetch.extractors.weixin_extractor.parse_weixin_article_html",
                    new=lambda html, url=None: None,
                ),
                patch(
                    "myrm_agent_harness.toolkits.web_fetch.extractors.weixin_extractor.has_weixin_js_content",
                    new=lambda html: True,
                ),
            ):
                doc, degradable, _, _, _, _result = await engine._try_fetch_and_process(
                    "https://mp.weixin.qq.com/s/abc123", FetcherType.HTTP
                )

                assert doc is not None
                assert doc.page_content == "generic"
                assert degradable is True
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_psutil_unavailable_returns_none_metrics(self, monkeypatch) -> None:
        from myrm_agent_harness.toolkits.web_fetch.engine import fetch_mixin as fm

        monkeypatch.setattr(fm, "_PSUTIL_AVAILABLE", False)
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result(RICH_HTML)
            engine._pipeline.aprocess.return_value = make_document()

            doc, _, _, cpu, mem, _ = await engine._try_fetch_and_process("http://example.com/page", FetcherType.HTTP)

            assert doc is not None
            assert cpu is None
            assert mem is None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_stealth_ladder_escalation_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            _http, browser, stealth = stub_fetchers(engine)
            engine._router = SimpleNamespace(
                select=lambda url: SimpleNamespace(fetcher_type=FetcherType.STEALTH),
                report_result=lambda *a, **k: None,
                shutdown=lambda: None,
            )
            stealth.fetch.return_value = None
            browser.fetch.return_value = None
            engine._escalation_providers = None

            doc, result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is None
            assert result is None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_browser_ladder_stealth_fallback_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            _http, browser, stealth = stub_fetchers(engine)
            engine._router = SimpleNamespace(
                select=lambda url: SimpleNamespace(fetcher_type=FetcherType.BROWSER),
                report_result=lambda *a, **k: None,
                shutdown=lambda: None,
            )
            browser.fetch.return_value = None
            stealth.fetch.return_value = http_result(RICH_HTML)
            engine._pipeline.aprocess.return_value = make_document("stealth")

            doc, _result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            assert doc.page_content == "stealth"
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_http_ladder_stealth_fallback_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, browser, stealth = stub_fetchers(engine)
            http.fetch.return_value = None
            browser.fetch.return_value = None
            stealth.fetch.return_value = http_result(RICH_HTML)
            engine._pipeline.aprocess.return_value = make_document("stealth final")

            doc, _result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            assert doc.page_content == "stealth final"
            await engine.shutdown()
