"""The scripted browser session the tool tests run against."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.utils.runtime.user_control import UserControl


@pytest.fixture
def mock_session() -> MagicMock:
    """Mock BrowserSession for tools testing."""
    session = MagicMock()
    session.user_control = UserControl()
    session.observed_generation = session.user_control.generation

    session.navigate = AsyncMock(return_value="Navigated to Example Page (https://example.com, status=200)")
    active_page = MagicMock()
    active_page.url = "https://example.com"
    active_page.title = AsyncMock(return_value="Example Page")
    session.get_active_page = MagicMock(return_value=active_page)
    session.inspect = AsyncMock(return_value="Total refs: 25\nRegions: main, form\nRecommended: #main")
    session.snapshot = AsyncMock(return_value=('- button "Click" [ref=e0]', {"ref_count": 1}))
    session.interact = AsyncMock(return_value="Clicked element e0")
    session.extract_text = AsyncMock(return_value="Page text content")
    session.extract_screenshot = AsyncMock(return_value="data:image/jpeg;base64,abc123")

    comparison_result = MagicMock()
    comparison_result.to_llm_message = MagicMock(return_value="Similarity: 95%")
    session.compare_screenshots = AsyncMock(return_value=comparison_result)
    session.close = AsyncMock()
    session.download_enabled = False
    session.evaluate = AsyncMock(return_value="42")
    session.new_tab = AsyncMock(return_value="tab1")
    session.switch_tab = AsyncMock(return_value="Switched to tab1")
    session.list_tabs = MagicMock(return_value=["tab0", "tab1"])
    session.list_tabs_with_info = MagicMock(
        return_value=[
            {"tab_id": "tab0", "domain": "example.com", "active": True},
            {"tab_id": "tab1", "domain": "other.com", "active": False},
        ]
    )
    session.close_tab = AsyncMock(return_value="Closed tab1")
    session.go_back = AsyncMock(return_value="Navigated back")
    session.go_forward = AsyncMock(return_value="Navigated forward")
    session.save_pdf = AsyncMock(return_value="Saved PDF to /tmp/page.pdf")
    session.resize = AsyncMock(return_value="Resized to 1920x1080")
    session.wait_for_load = AsyncMock(return_value="Page loaded")
    session.active_tab_crashed = MagicMock(return_value=False)
    session.get_console_log = MagicMock(return_value="Console: log message")
    session.get_network_log = MagicMock(return_value="Network: GET /api")
    session.set_dialog_response = AsyncMock(return_value="Dialog configured: accept")
    session.save_session = AsyncMock(return_value="Saved session for example.com")
    session.restore_session = AsyncMock(return_value="Restored session for example.com")
    session.list_sessions = AsyncMock(return_value="Sessions: example.com, github.com")
    session.delete_session = AsyncMock(return_value="Deleted session for example.com")

    dialog_manager = MagicMock()
    dialog_manager.format_for_snapshot = MagicMock(return_value="")
    session._dialog_manager = dialog_manager

    return session
