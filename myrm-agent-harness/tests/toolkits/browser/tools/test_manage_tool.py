"""browser_manage: tabs, history, logs, dialogs and saved sessions, and the actions it refuses."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.tools import create_browser_tools


@pytest.mark.asyncio
async def test_browser_manage_close(mock_session: MagicMock) -> None:
    """Test browser_manage close action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "close"})

    assert "closed" in result.lower()
    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_browser_manage_evaluate_success(mock_session: MagicMock) -> None:
    """Test browser_manage evaluate action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "evaluate", "value": "2+2"})

    assert "42" in result
    mock_session.evaluate.assert_called_once_with("2+2")


@pytest.mark.asyncio
async def test_browser_manage_evaluate_no_value(mock_session: MagicMock) -> None:
    """Test browser_manage evaluate without value returns error."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "evaluate"})

    assert "Error" in result
    assert "required" in result
    mock_session.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_browser_manage_new_tab_with_url(mock_session: MagicMock) -> None:
    """Test browser_manage new_tab with URL."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "new_tab", "value": "https://example.com"})

    assert "tab1" in result
    mock_session.new_tab.assert_called_once_with("https://example.com")


@pytest.mark.asyncio
async def test_browser_manage_new_tab_blank(mock_session: MagicMock) -> None:
    """Test browser_manage new_tab without URL."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "new_tab"})

    assert "tab1" in result
    mock_session.new_tab.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_browser_manage_switch_tab(mock_session: MagicMock) -> None:
    """Test browser_manage switch_tab action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "switch_tab", "value": "tab1"})

    assert "Switched" in result
    mock_session.switch_tab.assert_called_once_with("tab1")


@pytest.mark.asyncio
async def test_browser_manage_list_tabs_with_tabs(mock_session: MagicMock) -> None:
    """Test browser_manage list_tabs with open tabs."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "list_tabs"})

    assert "tab0" in result
    assert "tab1" in result
    mock_session.list_tabs_with_info.assert_called_once()


@pytest.mark.asyncio
async def test_browser_manage_list_tabs_empty(mock_session: MagicMock) -> None:
    """Test browser_manage list_tabs with no tabs."""
    mock_session.list_tabs = MagicMock(return_value=[])
    mock_session.list_tabs_with_info = MagicMock(return_value=[])
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "list_tabs"})

    assert "No open tabs" in result
    mock_session.list_tabs_with_info.assert_called_once()


@pytest.mark.asyncio
async def test_browser_manage_close_tab(mock_session: MagicMock) -> None:
    """Test browser_manage close_tab action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "close_tab", "value": "tab1"})

    assert "Closed" in result
    mock_session.close_tab.assert_called_once_with("tab1")


@pytest.mark.asyncio
async def test_browser_manage_back(mock_session: MagicMock) -> None:
    """Test browser_manage back action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "back"})

    assert "back" in result.lower()
    mock_session.go_back.assert_called_once()


@pytest.mark.asyncio
async def test_browser_manage_forward(mock_session: MagicMock) -> None:
    """Test browser_manage forward action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "forward"})

    assert "forward" in result.lower()
    mock_session.go_forward.assert_called_once()


@pytest.mark.asyncio
async def test_browser_manage_save_pdf(mock_session: MagicMock) -> None:
    """Test browser_manage save_pdf action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "save_pdf"})

    assert "PDF" in result
    mock_session.save_pdf.assert_called_once()


@pytest.mark.asyncio
async def test_browser_manage_resize_success(mock_session: MagicMock) -> None:
    """Test browser_manage resize action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "resize", "value": "1920x1080"})

    assert "Resized" in result
    mock_session.resize.assert_called_once_with(1920, 1080)


@pytest.mark.asyncio
async def test_browser_manage_resize_invalid_format(mock_session: MagicMock) -> None:
    """Test browser_manage resize with invalid format."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "resize", "value": "invalid"})

    assert "Error" in result
    assert "WIDTHxHEIGHT" in result
    mock_session.resize.assert_not_called()


@pytest.mark.asyncio
async def test_browser_manage_wait_for_load(mock_session: MagicMock) -> None:
    """Test browser_manage wait_for_load action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "wait_for_load"})

    assert "loaded" in result.lower()
    mock_session.wait_for_load.assert_called_once()


@pytest.mark.asyncio
async def test_browser_manage_console_log(mock_session: MagicMock) -> None:
    """Test browser_manage console_log action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "console_log"})

    assert "Console" in result
    mock_session.get_console_log.assert_called_once()


@pytest.mark.asyncio
async def test_browser_manage_network_log(mock_session: MagicMock) -> None:
    """Test browser_manage network_log action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "network_log"})

    assert "Network" in result
    mock_session.get_network_log.assert_called_once()


@pytest.mark.asyncio
async def test_browser_manage_dialog_response_accept(mock_session: MagicMock) -> None:
    """Test browser_manage dialog_response accept."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "dialog_response", "value": "accept"})

    assert "Dialog" in result
    mock_session.set_dialog_response.assert_called_once_with(True, "")


@pytest.mark.asyncio
async def test_browser_manage_dialog_response_dismiss(mock_session: MagicMock) -> None:
    """Test browser_manage dialog_response dismiss."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    await manage_tool.ainvoke({"action": "dialog_response", "value": "dismiss"})

    mock_session.set_dialog_response.assert_called_once_with(False, "")


@pytest.mark.asyncio
async def test_browser_manage_dialog_response_with_prompt(mock_session: MagicMock) -> None:
    """Test browser_manage dialog_response with prompt text."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    await manage_tool.ainvoke({"action": "dialog_response", "value": "accept:my input"})

    mock_session.set_dialog_response.assert_called_once_with(True, "my input")


@pytest.mark.asyncio
async def test_browser_manage_save_session_domain_only(mock_session: MagicMock) -> None:
    """Test browser_manage save_session with domain only."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "save_session", "value": "example.com"})

    assert "Saved" in result
    mock_session.save_session.assert_called_once_with("example.com")


@pytest.mark.asyncio
async def test_browser_manage_save_session_with_label(mock_session: MagicMock) -> None:
    """Test browser_manage save_session with domain and label."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "save_session", "value": "example.com:my-session"})

    assert "Saved" in result
    mock_session.save_session.assert_called_once_with("example.com:my-session")


@pytest.mark.asyncio
async def test_browser_manage_save_session_no_domain(mock_session: MagicMock) -> None:
    """Test browser_manage save_session without domain returns error."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "save_session"})

    assert "Error" in result
    assert "domain" in result
    mock_session.save_session.assert_not_called()


@pytest.mark.asyncio
async def test_browser_manage_restore_session_success(mock_session: MagicMock) -> None:
    """Test browser_manage restore_session."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "restore_session", "value": "example.com"})

    assert "Restored" in result
    mock_session.restore_session.assert_called_once_with("example.com")


@pytest.mark.asyncio
async def test_browser_manage_restore_session_no_domain(mock_session: MagicMock) -> None:
    """Test browser_manage restore_session without domain returns error."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "restore_session"})

    assert "Error" in result
    assert "domain" in result
    mock_session.restore_session.assert_not_called()


@pytest.mark.asyncio
async def test_browser_manage_list_sessions(mock_session: MagicMock) -> None:
    """Test browser_manage list_sessions action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "list_sessions"})

    assert "Sessions" in result
    mock_session.list_sessions.assert_called_once()


@pytest.mark.asyncio
async def test_browser_manage_delete_session_success(mock_session: MagicMock) -> None:
    """Test browser_manage delete_session."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "delete_session", "value": "example.com"})

    assert "Deleted" in result
    mock_session.delete_session.assert_called_once_with("example.com")


@pytest.mark.asyncio
async def test_browser_manage_delete_session_no_domain(mock_session: MagicMock) -> None:
    """Test browser_manage delete_session without domain returns error."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "delete_session"})

    assert "Error" in result
    assert "domain" in result
    mock_session.delete_session.assert_not_called()


@pytest.mark.asyncio
async def test_browser_manage_has_no_wait_for_user(mock_session: MagicMock) -> None:
    """There is no wait_for_user tool; use browser_ask_human_tool instead."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "wait_for_user"})

    assert "Unknown action" in result
    assert "wait_for_user" in result


@pytest.mark.asyncio
async def test_browser_manage_unknown_action(mock_session: MagicMock) -> None:
    """Test browser_manage with unknown action."""
    tools = create_browser_tools(mock_session)
    manage_tool = next(t for t in tools if t.name == "browser_manage_tool")

    result = await manage_tool.ainvoke({"action": "invalid_action"})

    assert "Unknown action" in result
    assert "invalid_action" in result
