"""Tests for ``FetchEngineEscalationMixin``: L4 remote escalation and the bilibili cookie loader."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from tests.toolkits.web_fetch._degradation_support import (
    http_result,
    make_document,
    mock_pipeline,
    stub_fetchers,
)


class TestEscalationMixin:
    @pytest.mark.asyncio
    async def test_escalation_no_providers(self) -> None:
        engine = FetchEngine()
        engine._escalation_providers = None

        doc, result = await engine._try_escalation("http://example.com/page")

        assert doc is None
        assert result is None
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_escalation_provider_failure_then_success(self) -> None:
        engine = FetchEngine()
        engine._pipeline = mock_pipeline()  # type: ignore[assignment]
        engine._pipeline.aprocess.return_value = make_document()
        good = SimpleNamespace(
            provider_id="reader2",
            fetch_url=AsyncMock(return_value=SimpleNamespace(content="# final", is_markdown=True, url=None, title="t")),
        )
        bad = SimpleNamespace(
            provider_id="broken",
            fetch_url=AsyncMock(side_effect=RuntimeError("boom")),
        )
        engine.set_escalation_providers([bad, good])

        doc, result = await engine._try_escalation("http://example.com/page")

        assert doc is not None
        assert doc.page_content == "# final"
        assert result is None
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_escalation_html_content_pipeline(self) -> None:
        engine = FetchEngine()
        engine._pipeline = mock_pipeline()  # type: ignore[assignment]
        engine._pipeline.aprocess.return_value = make_document("html doc")
        provider = SimpleNamespace(
            provider_id="reader4",
            fetch_url=AsyncMock(
                return_value=SimpleNamespace(
                    content="<p>html</p>",
                    is_markdown=False,
                    url="http://example.com/page",
                    title="t",
                )
            ),
        )
        engine.set_escalation_providers([provider])

        doc, _result = await engine._try_escalation("http://example.com/page")

        assert doc is not None
        assert doc.metadata.get("escalation_provider") == "reader4"
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_escalation_empty_content_skipped(self) -> None:
        engine = FetchEngine()
        provider = SimpleNamespace(
            provider_id="reader5",
            fetch_url=AsyncMock(return_value=SimpleNamespace(content="   ", is_markdown=True, url=None, title="")),
        )
        engine.set_escalation_providers([provider])

        doc, result = await engine._try_escalation("http://example.com/page")

        assert doc is None
        assert result is None
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_load_bilibili_cookies_no_vault(self) -> None:
        engine = FetchEngine()
        engine._http_fetcher._session_vault = None

        cookies = await engine._load_bilibili_cookies()

        assert cookies is None
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_load_bilibili_cookies_with_entry(self) -> None:
        engine = FetchEngine()
        vault = AsyncMock()
        vault.load.return_value = SimpleNamespace(
            storage_state={
                "cookies": [
                    {"name": "SESSDATA", "value": "v1"},
                    {"name": "buvid3", "value": "v2"},
                ]
            }
        )
        engine._http_fetcher._session_vault = vault

        cookies = await engine._load_bilibili_cookies()

        assert cookies == {"SESSDATA": "v1", "buvid3": "v2"}
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_load_bilibili_cookies_missing_storage_state(self) -> None:
        engine = FetchEngine()
        vault = AsyncMock()
        vault.load.return_value = SimpleNamespace(storage_state=None)
        engine._http_fetcher._session_vault = vault

        cookies = await engine._load_bilibili_cookies()

        assert cookies is None
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_load_bilibili_cookies_vault_error(self) -> None:
        engine = FetchEngine()
        vault = AsyncMock()
        vault.load.side_effect = RuntimeError("vault error")
        engine._http_fetcher._session_vault = vault

        cookies = await engine._load_bilibili_cookies()

        assert cookies is None
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_escalation_html_pipeline_returns_none_continues(self) -> None:
        engine = FetchEngine()
        http, _, _ = stub_fetchers(engine)
        http.fetch.return_value = http_result("", status=404)
        engine._escalation_providers = [
            SimpleNamespace(
                provider_id="p1",
                fetch_url=AsyncMock(
                    return_value=SimpleNamespace(
                        content="<p>raw html</p>",
                        is_markdown=False,
                        url=None,
                        title=None,
                    )
                ),
            )
        ]
        engine._pipeline = mock_pipeline()  # type: ignore[assignment]
        engine._pipeline.aprocess.return_value = None

        doc, result = await engine._crawl_with_degradation("http://example.com/page")

        assert doc is None
        assert result is None
        await engine.shutdown()
