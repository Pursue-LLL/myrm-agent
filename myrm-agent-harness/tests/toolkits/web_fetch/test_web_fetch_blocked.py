"""Web fetch meta-tool URL guards: blocked-hostname decontamination, SSRF, mode-specific arguments."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain.tools import BaseTool

import myrm_agent_harness.toolkits.web_fetch.web_fetch_agent_tools as mod
from myrm_agent_harness.agent.errors import ToolErrorCategory
from myrm_agent_harness.toolkits.web_fetch.web_fetch_agent_tools import (
    create_web_fetch_tool,
)
from myrm_agent_harness.utils.errors import ToolError

HF_BLOCKLIST = ("huggingface.co", "*.huggingface.co", "hf.co", "*.hf.co")


def _make_tool(mode: str, **kwargs: object) -> BaseTool:
    """``plain``: full read only. ``extract``: reranker and embedding configured, so ``operation`` exists."""
    if mode == "plain":
        return create_web_fetch_tool(**kwargs)
    return create_web_fetch_tool(MagicMock(), MagicMock(), **kwargs)


def _args(mode: str, urls: list[str], reason: str = "probe") -> dict[str, object]:
    args: dict[str, object] = {"urls": urls, "reason": reason}
    if mode == "extract":
        args["operation"] = "fetch_full_content"
    return args


@pytest.fixture(params=["plain", "extract"])
def mode(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.mark.asyncio
async def test_blocked_hf_host_rejected_before_fetch(mode: str) -> None:
    tool = _make_tool(mode, blocked_hostnames=HF_BLOCKLIST)
    with pytest.raises(ToolError) as exc_info:
        await tool.ainvoke(_args(mode, ["https://huggingface.co/datasets/leak"], "decontamination probe"))
    assert exc_info.value.error_code == "BENCHMARK_BLOCKED_HOST"


@pytest.mark.asyncio
async def test_blocked_short_alias_rejected(mode: str) -> None:
    tool = _make_tool(mode, blocked_hostnames=HF_BLOCKLIST)
    with pytest.raises(ToolError):
        await tool.ainvoke(_args(mode, ["https://hf.co/models/x"], "decontamination probe"))


@pytest.mark.asyncio
async def test_blocked_subdomain_rejected(mode: str) -> None:
    tool = _make_tool(mode, blocked_hostnames=HF_BLOCKLIST)
    with pytest.raises(ToolError):
        await tool.ainvoke(_args(mode, ["https://datasets-server.huggingface.co/rows"], "decontamination probe"))


@pytest.mark.asyncio
async def test_one_blocked_url_among_clean_ones_rejects_the_whole_call(mode: str) -> None:
    tool = _make_tool(mode, blocked_hostnames=HF_BLOCKLIST)
    with patch.object(mod, "_fetch_full_content") as mock_fetch, pytest.raises(ToolError):
        await tool.ainvoke(_args(mode, ["https://example.com/a", "https://hf.co/x"]))
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_extract_operation_is_guarded_too() -> None:
    tool = _make_tool("extract", blocked_hostnames=HF_BLOCKLIST)
    with patch.object(mod, "_fetch_and_extract") as mock_extract, pytest.raises(ToolError) as exc_info:
        await tool.ainvoke(
            {
                "urls": ["https://hf.co/x"],
                "operation": "fetch_and_extract",
                "questions": ["anything"],
                "reason": "probe",
            }
        )
    assert exc_info.value.error_code == "BENCHMARK_BLOCKED_HOST"
    mock_extract.assert_not_called()


@pytest.mark.asyncio
async def test_clean_url_reaches_fetch_stage(mode: str) -> None:
    """A public non-blocked URL passes the blocklist; the engine handles it."""
    tool = _make_tool(mode, blocked_hostnames=HF_BLOCKLIST)
    # Patch the engine entry so the test never touches the network; reaching
    # _fetch_full_content means the guards let the URL through.
    with patch.object(mod, "_fetch_full_content") as mock_fetch:
        mock_fetch.return_value = {"content": "ok", "metadata": {}}
        result = await tool.ainvoke(_args(mode, ["https://example.com/article"]))
        assert result.get("content") == "ok"
        mock_fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_private_network_urls_are_refused_unless_allowed(mode: str) -> None:
    tool = _make_tool(mode)
    with pytest.raises(ToolError, match="SSRF protection"):
        await tool.ainvoke(_args(mode, ["http://127.0.0.1:8080/admin"]))

    allowed = _make_tool(mode, allow_private_networks=True)
    with patch.object(mod, "_fetch_full_content") as mock_fetch:
        mock_fetch.return_value = {"content": "ok", "metadata": {}}
        await allowed.ainvoke(_args(mode, ["http://127.0.0.1:8080/admin"]))
    mock_fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_urls_carrying_secrets_are_refused(mode: str) -> None:
    tool = _make_tool(mode)
    secret_url = "https://example.com/callback?api_key=sk-1234567890abcdef1234567890abcdef"
    with pytest.raises(ToolError, match="data exfiltration"):
        await tool.ainvoke(_args(mode, [secret_url]))


@pytest.mark.asyncio
async def test_block_error_text(mode: str) -> None:
    tool = _make_tool(mode, blocked_hostnames=HF_BLOCKLIST)
    try:
        await tool.ainvoke(_args(mode, ["https://hf.co/x"], ""))
    except ToolError as exc:
        assert "URL blocked" in str(exc)
        assert exc.error_category == ToolErrorCategory.BENCHMARK_BLOCKED.value
    else:  # pragma: no cover
        pytest.fail("expected ToolError")
