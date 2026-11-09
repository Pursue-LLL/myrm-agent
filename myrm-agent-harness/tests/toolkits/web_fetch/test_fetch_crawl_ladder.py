"""Tests for the ``FetchEngine._crawl_with_degradation`` tier ladder.

Covers every start tier (HTTP, BROWSER, STEALTH), the downgrade/escalation order, non-degradable
stops, the L4 escalation tail and the weixin / resource-sampling branches of the ladder.
"""

from __future__ import annotations

import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import (
    FetcherType,
)
from tests.toolkits.web_fetch._degradation_support import (
    RICH_HTML,
    http_result,
    make_document,
    make_engine,
    stub_fetchers,
)


class TestCrawlWithDegradation:
    @pytest.mark.asyncio
    async def test_stealth_start_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            _http, _browser, stealth = stub_fetchers(engine)
            engine._router = SimpleNamespace(
                select=lambda url: SimpleNamespace(fetcher_type=FetcherType.STEALTH),
                report_result=lambda *a, **k: None,
                shutdown=lambda: None,
            )
            stealth.fetch.return_value = http_result(RICH_HTML)
            engine._pipeline.aprocess.return_value = make_document()

            doc, result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            assert result is not None
            stealth.fetch.assert_awaited_once()
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_stealth_fail_then_browser_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            _http, browser, stealth = stub_fetchers(engine)
            engine._router = SimpleNamespace(
                select=lambda url: SimpleNamespace(fetcher_type=FetcherType.STEALTH),
                report_result=lambda *a, **k: None,
                shutdown=lambda: None,
            )
            stealth.fetch.return_value = None
            browser.fetch.return_value = http_result(RICH_HTML)
            engine._pipeline.aprocess.return_value = make_document()

            doc, _result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_stealth_and_browser_fail_then_escalation(self) -> None:
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
            provider = SimpleNamespace(
                provider_id="reader",
                fetch_url=AsyncMock(
                    return_value=SimpleNamespace(
                        content="# md",
                        is_markdown=True,
                        url="http://example.com/page",
                        title="t",
                    )
                ),
            )
            engine.set_escalation_providers([provider])

            doc, result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            assert doc.metadata.get("escalation_provider") == "reader"
            assert result is None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_browser_start_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            _http, browser, _stealth = stub_fetchers(engine)
            engine._router = SimpleNamespace(
                select=lambda url: SimpleNamespace(fetcher_type=FetcherType.BROWSER),
                report_result=lambda *a, **k: None,
                shutdown=lambda: None,
            )
            browser.fetch.return_value = http_result(RICH_HTML)
            engine._pipeline.aprocess.return_value = make_document()

            doc, _result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_http_success_no_degradation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result(RICH_HTML)
            engine._pipeline.aprocess.return_value = make_document()

            doc, _result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            http.fetch.assert_awaited_once()
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_http_4xx_not_degradable_returns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, browser, stealth = stub_fetchers(engine)
            http.fetch.return_value = http_result("", status=404)

            doc, _result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is None
            browser.fetch.assert_not_awaited()
            stealth.fetch.assert_not_awaited()
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_full_ladder_failure_without_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, browser, stealth = stub_fetchers(engine)
            http.fetch.return_value = None
            browser.fetch.return_value = None
            stealth.fetch.return_value = None

            doc, result = await engine._crawl_with_degradation("http://example.com/page", allow_escalation=False)

            assert doc is None
            assert result is None
            await engine.shutdown()


class TestLadderRemainingBranches:
    @pytest.mark.asyncio
    async def test_weixin_no_js_content_returns_none_degrades(self) -> None:
        """Weixin URL with real content but no js_content div => skip generic."""
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, _, _ = stub_fetchers(engine)
            http.fetch.return_value = http_result(RICH_HTML)
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
                doc, degradable, _, _, _, result = await engine._try_fetch_and_process(url, FetcherType.HTTP)

                assert doc is None
                assert degradable is True
                assert result is not None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_browser_ladder_escalation_success(self) -> None:
        """BROWSER + STEALTH both fail, remote escalation returns markdown doc."""
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            _http, browser, stealth = stub_fetchers(engine)
            engine._router = SimpleNamespace(
                select=lambda url: SimpleNamespace(fetcher_type=FetcherType.BROWSER),
                report_result=lambda *a, **k: None,
                shutdown=lambda: None,
            )
            browser.fetch.return_value = None
            stealth.fetch.return_value = None
            engine._escalation_providers = [
                SimpleNamespace(
                    provider_id="esc",
                    fetch_url=AsyncMock(
                        return_value=SimpleNamespace(
                            content="# Escaped body",
                            is_markdown=True,
                            url="http://escalated.example",
                            title="Esc",
                        )
                    ),
                )
            ]

            doc, result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            assert doc.page_content == "# Escaped body"
            assert doc.metadata["escalation_provider"] == "esc"
            assert result is None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_http_ladder_browser_success(self) -> None:
        """HTTP degradable, then BROWSER tier succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, browser, _stealth = stub_fetchers(engine)
            http.fetch.return_value = None
            browser.fetch.return_value = http_result(RICH_HTML)
            engine._pipeline.aprocess.return_value = make_document("browser final")

            doc, _result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            assert doc.page_content == "browser final"
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_browser_ladder_escalation_returns_none(self) -> None:
        """BROWSER + STEALTH fail and escalation unavailable => return last result."""
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            _http, browser, stealth = stub_fetchers(engine)
            engine._router = SimpleNamespace(
                select=lambda url: SimpleNamespace(fetcher_type=FetcherType.BROWSER),
                report_result=lambda *a, **k: None,
                shutdown=lambda: None,
            )
            browser.fetch.return_value = None
            stealth.fetch.return_value = None
            engine._escalation_providers = None

            doc, result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is None
            assert result is None
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_http_ladder_escalation_success(self) -> None:
        """HTTP + BROWSER + STEALTH all fail, escalation succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, browser, stealth = stub_fetchers(engine)
            http.fetch.return_value = None
            browser.fetch.return_value = None
            stealth.fetch.return_value = None
            engine._escalation_providers = [
                SimpleNamespace(
                    provider_id="esc2",
                    fetch_url=AsyncMock(
                        return_value=SimpleNamespace(
                            content="# Last resort",
                            is_markdown=True,
                            url=None,
                            title=None,
                        )
                    ),
                )
            ]

            doc, _result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            assert doc.page_content == "# Last resort"
            await engine.shutdown()

    @pytest.mark.asyncio
    async def test_escalation_html_pipeline_none_then_next_provider(self) -> None:
        """First escalation provider yields HTML that the pipeline drops => continue to next."""
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(tmp)
            http, browser, stealth = stub_fetchers(engine)
            http.fetch.return_value = None
            browser.fetch.return_value = None
            stealth.fetch.return_value = None
            engine._pipeline.aprocess.side_effect = [None, make_document("html escaped")]
            engine._escalation_providers = [
                SimpleNamespace(
                    provider_id="p1",
                    fetch_url=AsyncMock(
                        return_value=SimpleNamespace(
                            content="<p>raw one</p>",
                            is_markdown=False,
                            url=None,
                            title=None,
                        )
                    ),
                ),
                SimpleNamespace(
                    provider_id="p2",
                    fetch_url=AsyncMock(
                        return_value=SimpleNamespace(
                            content="<p>raw two</p>",
                            is_markdown=False,
                            url=None,
                            title=None,
                        )
                    ),
                ),
            ]

            doc, _result = await engine._crawl_with_degradation("http://example.com/page")

            assert doc is not None
            assert doc.page_content == "html escaped"
            assert doc.metadata["escalation_provider"] == "p2"
            await engine.shutdown()

    def test_psutil_import_failure_sets_flag(self, monkeypatch) -> None:
        import importlib
        import sys

        from myrm_agent_harness.toolkits.web_fetch.engine import fetch_mixin as fm

        monkeypatch.setitem(sys.modules, "psutil", None)
        reloaded = importlib.reload(fm)
        assert reloaded._PSUTIL_AVAILABLE is False
