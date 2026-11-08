"""Browser tools that navigate and read: the tool set, navigate, inspect, snapshot and extract.

The tools run against a scripted session; the real-browser proof is ``test_browser_session_integration``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.tools import create_browser_tools, mark_untrusted


def test_mark_untrusted() -> None:
    """Test mark_untrusted wraps content with 4-layer security boundary."""
    content = "untrusted content"
    result = mark_untrusted(content)

    assert "SECURITY NOTICE" in result
    assert "UNTRUSTED" in result
    assert "untrusted content" in result
    assert "<<<UNTRUSTED_DATA" in result
    assert "<<<END_UNTRUSTED_DATA" in result


def test_create_browser_tools(mock_session: MagicMock) -> None:
    """Test create_browser_tools returns 8 tools."""
    tools = create_browser_tools(mock_session)

    assert len(tools) == 8
    tool_names = {tool.name for tool in tools}
    assert tool_names == {
        "browser_navigate_tool",
        "browser_inspect_tool",
        "browser_snapshot_tool",
        "browser_interact_tool",
        "browser_extract_tool",
        "browser_manage_tool",
        "browser_execute_script_tool",
        "browser_ask_human_tool",
    }


# =============================================================================
# browser_navigate
# =============================================================================


@pytest.mark.asyncio
async def test_browser_navigate_basic(mock_session: MagicMock) -> None:
    """Test browser_navigate basic functionality."""
    tools = create_browser_tools(mock_session)
    navigate_tool = next(t for t in tools if t.name == "browser_navigate_tool")

    result = await navigate_tool.ainvoke({"url": "https://example.com"})

    assert "Navigated" in result["content"]
    assert result["metadata"]["sources"][0]["url"] == "https://example.com"
    mock_session.navigate.assert_called_once_with("https://example.com", verify_goal=None)


# =============================================================================
# browser_inspect
# =============================================================================


@pytest.mark.asyncio
async def test_browser_inspect_basic(mock_session: MagicMock) -> None:
    """Test browser_inspect returns page structure."""
    tools = create_browser_tools(mock_session)
    inspect_tool = next(t for t in tools if t.name == "browser_inspect_tool")

    result = await inspect_tool.ainvoke({})

    assert "Total refs" in result
    mock_session.inspect.assert_called_once()


# =============================================================================
# browser_snapshot
# =============================================================================


@pytest.mark.asyncio
async def test_browser_snapshot_default_params(mock_session: MagicMock) -> None:
    """Test browser_snapshot with default params."""
    tools = create_browser_tools(mock_session)
    snapshot_tool = next(t for t in tools if t.name == "browser_snapshot_tool")

    result = await snapshot_tool.ainvoke({})

    assert "button" in result
    call_args = mock_session.snapshot.call_args
    assert call_args.kwargs["scope"] == "content"
    assert call_args.kwargs["diff"] is True
    assert call_args.kwargs["compact"] is False


@pytest.mark.asyncio
async def test_browser_snapshot_returns_string_only(mock_session: MagicMock) -> None:
    """Test browser_snapshot when session returns string only (not tuple)."""
    mock_session.snapshot = AsyncMock(return_value='- button "Click" [ref=e0]')
    tools = create_browser_tools(mock_session)
    snapshot_tool = next(t for t in tools if t.name == "browser_snapshot_tool")

    result = await snapshot_tool.ainvoke({})

    assert "button" in result
    assert "UNTRUSTED_DATA" in result


@pytest.mark.asyncio
async def test_browser_snapshot_custom_params(mock_session: MagicMock) -> None:
    """Test browser_snapshot with custom params."""
    tools = create_browser_tools(mock_session)
    snapshot_tool = next(t for t in tools if t.name == "browser_snapshot_tool")

    result = await snapshot_tool.ainvoke(
        {
            "scope": "interactive",
            "diff": False,
            "compact": True,
            "selector": "#main",
            "max_tokens": 500,
        }
    )

    assert "button" in result
    call_args = mock_session.snapshot.call_args
    assert call_args.kwargs["scope"] == "interactive"
    assert call_args.kwargs["diff"] is False
    assert call_args.kwargs["compact"] is True
    assert call_args.kwargs["selector"] == "#main"
    assert call_args.kwargs["max_tokens"] == 500


# =============================================================================
# browser_extract
# =============================================================================


@pytest.mark.asyncio
async def test_browser_extract_text_default(mock_session: MagicMock) -> None:
    """Test browser_extract text mode (default)."""
    tools = create_browser_tools(mock_session)
    extract_tool = next(t for t in tools if t.name == "browser_extract_tool")

    result = await extract_tool.ainvoke({})

    assert "UNTRUSTED_DATA" in result
    assert "Page text content" in result
    mock_session.extract_text.assert_called_once()


@pytest.mark.asyncio
async def test_browser_extract_text_explicit(mock_session: MagicMock) -> None:
    """Test browser_extract text mode (explicit)."""
    tools = create_browser_tools(mock_session)
    extract_tool = next(t for t in tools if t.name == "browser_extract_tool")

    result = await extract_tool.ainvoke({"mode": "text"})

    assert "UNTRUSTED_DATA" in result
    assert "Page text content" in result
    mock_session.extract_text.assert_called_once()


@pytest.mark.asyncio
async def test_browser_extract_screenshot_default(mock_session: MagicMock) -> None:
    """Test browser_extract screenshot mode."""
    tools = create_browser_tools(mock_session)
    extract_tool = next(t for t in tools if t.name == "browser_extract_tool")

    result = await extract_tool.ainvoke({"mode": "screenshot"})

    assert "data:image/jpeg" in result
    mock_session.extract_screenshot.assert_called_once_with(scale=1.0)


@pytest.mark.asyncio
async def test_browser_extract_screenshot_annotated(mock_session: MagicMock) -> None:
    """Test browser_extract screenshot with annotation."""
    tools = create_browser_tools(mock_session)
    extract_tool = next(t for t in tools if t.name == "browser_extract_tool")

    await extract_tool.ainvoke({"mode": "screenshot", "annotate": True})

    mock_session.extract_screenshot.assert_called_once_with(scale=1.0)


@pytest.mark.asyncio
async def test_browser_extract_screenshot_retina(mock_session: MagicMock) -> None:
    """Test browser_extract screenshot with 2x scale."""
    tools = create_browser_tools(mock_session)
    extract_tool = next(t for t in tools if t.name == "browser_extract_tool")

    await extract_tool.ainvoke({"mode": "screenshot", "scale": 2.0})

    mock_session.extract_screenshot.assert_called_once_with(scale=2.0)


@pytest.mark.asyncio
async def test_browser_extract_diff_fast_no_baseline(mock_session: MagicMock) -> None:
    """Test browser_extract diff_fast without baseline returns error."""
    tools = create_browser_tools(mock_session)
    extract_tool = next(t for t in tools if t.name == "browser_extract_tool")

    result = await extract_tool.ainvoke({"mode": "diff_fast"})

    assert "Error" in result
    assert "baseline" in result
    mock_session.compare_screenshots.assert_not_called()


@pytest.mark.asyncio
async def test_browser_extract_diff_fast_with_baseline(mock_session: MagicMock) -> None:
    """Test browser_extract diff_fast with baseline."""
    tools = create_browser_tools(mock_session)
    extract_tool = next(t for t in tools if t.name == "browser_extract_tool")

    result = await extract_tool.ainvoke({"mode": "diff_fast", "baseline": "base64data"})

    assert "similarity" in result.lower() or "different" in result.lower()
    mock_session.compare_screenshots.assert_called_once_with("base64data", strategy="fast", similarity_threshold=0.9)


@pytest.mark.asyncio
async def test_browser_extract_diff_accurate_no_baseline(mock_session: MagicMock) -> None:
    """Test browser_extract diff_accurate without baseline returns error."""
    tools = create_browser_tools(mock_session)
    extract_tool = next(t for t in tools if t.name == "browser_extract_tool")

    result = await extract_tool.ainvoke({"mode": "diff_accurate"})

    assert "Error" in result
    assert "baseline" in result
    mock_session.compare_screenshots.assert_not_called()


@pytest.mark.asyncio
async def test_browser_extract_diff_accurate_with_baseline(mock_session: MagicMock) -> None:
    """Test browser_extract diff_accurate with baseline."""
    tools = create_browser_tools(mock_session)
    extract_tool = next(t for t in tools if t.name == "browser_extract_tool")

    await extract_tool.ainvoke({"mode": "diff_accurate", "baseline": "base64data"})

    mock_session.compare_screenshots.assert_called_once_with(
        "base64data", strategy="accurate", color_tolerance=0.1, mismatch_threshold=5.0, include_aa=True
    )
