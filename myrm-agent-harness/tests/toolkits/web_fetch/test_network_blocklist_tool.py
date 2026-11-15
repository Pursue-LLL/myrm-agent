"""The tool reads the user's current network blocklist on every call and hands it to the engine that call builds.

The engine is the shared one only while no list applies; the rerank path passes the list through the retriever to the
same per-call engine.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.tools import BaseTool

import myrm_agent_harness.toolkits.web_fetch.web_fetch_agent_tools as tool_module
from myrm_agent_harness.toolkits.retriever.engine import RetrieverManager
from myrm_agent_harness.toolkits.web_fetch import web_fetch_tools


def _make_tool(mode: str, **kwargs: object) -> BaseTool:
    """``plain``: full read only. ``extract``: reranker and embedding configured, so ``operation`` exists."""
    if mode == "plain":
        return tool_module.create_web_fetch_tool(allow_private_networks=True, **kwargs)
    return tool_module.create_web_fetch_tool(MagicMock(), MagicMock(), allow_private_networks=True, **kwargs)


@pytest.mark.asyncio
class TestToolWiring:
    @pytest.mark.parametrize("mode", ["plain", "extract"])
    async def test_the_provider_is_read_on_every_call(self, mode: str) -> None:
        lists = iter([("a.example",), ("b.example", "c.example")])
        tool = _make_tool(mode, network_blocklist_provider=lambda: next(lists))
        args: dict[str, object] = {"urls": ["https://example.com/"], "reason": "probe"}
        if mode == "extract":
            args["operation"] = "fetch_full_content"

        with patch.object(tool_module, "_fetch_full_content", new=AsyncMock(return_value={})) as fetch:
            await tool.ainvoke(args)
            await tool.ainvoke(args)

        assert [call.kwargs["network_blocklist"] for call in fetch.await_args_list] == [
            ("a.example",),
            ("b.example", "c.example"),
        ]

    async def test_extract_hands_the_current_list_to_the_extraction(self) -> None:
        tool = _make_tool("extract", network_blocklist_provider=lambda: ("a.example",))

        with patch.object(tool_module, "_fetch_and_extract", new=AsyncMock(return_value={})) as extract:
            await tool.ainvoke(
                {
                    "urls": ["https://example.com/"],
                    "operation": "fetch_and_extract",
                    "questions": ["q"],
                    "reason": "probe",
                }
            )

        assert extract.await_args.kwargs["network_blocklist"] == ("a.example",)

    async def test_without_a_provider_no_list_applies(self) -> None:
        tool = _make_tool("plain")

        with patch.object(tool_module, "_fetch_full_content", new=AsyncMock(return_value={})) as fetch:
            await tool.ainvoke({"urls": ["https://example.com/"], "reason": "probe"})

        assert fetch.await_args.kwargs["network_blocklist"] == ()

    async def test_a_list_gets_an_engine_of_its_own_and_no_list_the_shared_engine(self) -> None:
        failed = ([], [("https://example.com/", None)])

        with (
            patch("myrm_agent_harness.toolkits.web_fetch.FetchEngine") as engine_class,
            patch.object(web_fetch_tools, "crawl_many", new=AsyncMock(return_value=failed)) as shared,
        ):
            engine_class.return_value.crawl_many = AsyncMock(return_value=failed)
            await tool_module._fetch_full_content(["https://example.com/"], network_blocklist=("a.example",))
            assert engine_class.call_args.kwargs["network_blocklist"] == ("a.example",)
            shared.assert_not_awaited()

            engine_class.reset_mock()
            await tool_module._fetch_full_content(["https://example.com/"])
            engine_class.assert_not_called()
            shared.assert_awaited_once()

    async def test_the_extraction_hands_the_list_to_the_retriever(self) -> None:
        retrieve = AsyncMock(return_value=([], "context", ""))

        with (
            patch("myrm_agent_harness.toolkits.retriever.engine.RetrieverManager.retrieve_from_urls", new=retrieve),
            patch("myrm_agent_harness.toolkits.retriever.embedding.factory.get_embedding_service"),
            patch("myrm_agent_harness.toolkits.retriever.reranker.factory.get_reranker_service"),
        ):
            await tool_module._fetch_and_extract(
                ["https://example.com/"], ["q"], MagicMock(), MagicMock(), network_blocklist=("a.example",)
            )

        assert retrieve.await_args.kwargs["network_blocklist"] == ("a.example",)

    async def test_the_retriever_builds_its_engine_with_the_list(self) -> None:
        with patch("myrm_agent_harness.toolkits.web_fetch.FetchEngine") as engine_class:
            engine_class.return_value.crawl_many = AsyncMock(return_value=([], []))
            await RetrieverManager().retrieve_from_urls(
                ["https://example.com/"], "q", MagicMock(), MagicMock(), network_blocklist=("a.example",)
            )

        assert engine_class.call_args.kwargs["network_blocklist"] == ("a.example",)
