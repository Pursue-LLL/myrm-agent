"""Interactor input actions: type, fill, press, focus, select, upload_file, check and uncheck."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.session.interactor import Interactor

# =============================================================================
# Action: type
# =============================================================================


@pytest.mark.asyncio
async def test_interact_type(interactor: Interactor) -> None:
    """Test type action."""
    mock_locator = AsyncMock()
    mock_locator.get_attribute.return_value = "text"

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("type", "e0", "Hello World")

        assert result == "Typed 'Hello World' into e0"
        mock_locator.type.assert_called_once()
        args, kwargs = mock_locator.type.call_args
        assert args[0] == "Hello World"
        assert kwargs["timeout"] >= 10_000
        assert "delay" in kwargs


# =============================================================================
# Action: fill
# =============================================================================


@pytest.mark.asyncio
async def test_interact_fill(interactor: Interactor) -> None:
    """Test fill action."""
    mock_locator = AsyncMock()
    mock_locator.get_attribute.return_value = "text"

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("fill", "e0", "test@example.com")

        assert result == "Filled e0 with 'test@example.com'"
        mock_locator.fill.assert_called_once_with("test@example.com", timeout=10_000)


# =============================================================================
# Action: press
# =============================================================================


@pytest.mark.asyncio
async def test_interact_press(interactor: Interactor) -> None:
    """Test press action."""
    mock_locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("press", "e0", "Enter")

        assert result == "Pressed 'Enter' on e0"
        mock_locator.press.assert_called_once_with("Enter", timeout=10_000)


# =============================================================================
# Action: focus
# =============================================================================


@pytest.mark.asyncio
async def test_interact_focus(interactor: Interactor) -> None:
    """Test focus action."""
    mock_locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("focus", "e0")

        assert result == "Focused e0"
        mock_locator.focus.assert_called_once_with(timeout=10_000)


# =============================================================================
# Action: select
# =============================================================================


@pytest.mark.asyncio
async def test_interact_select(interactor: Interactor) -> None:
    """Test select action."""
    mock_locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("select", "e0", "option1")

        assert result == "Selected 'option1' in e0"
        mock_locator.select_option.assert_called_once_with("option1", timeout=10_000)


@pytest.mark.asyncio
async def test_interact_select_multi_value(interactor: Interactor) -> None:
    """Multi-select recordings join values with ';' — each option is selected."""
    mock_locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("select", "e0", "en; zh")

        assert result == "Selected 'en; zh' in e0"
        mock_locator.select_option.assert_called_once_with(["en", "zh"], timeout=10_000)


# =============================================================================
# Action: upload_file
# =============================================================================


@pytest.mark.asyncio
async def test_interact_upload_file(interactor: Interactor) -> None:
    """Test upload_file action."""
    mock_locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("upload_file", "e0", "/tmp/file.txt")

        assert result == "Uploaded file to e0: /tmp/file.txt"
        mock_locator.set_input_files.assert_called_once_with("/tmp/file.txt", timeout=10_000)


# =============================================================================
# Action: check
# =============================================================================


@pytest.mark.asyncio
async def test_interact_check(interactor: Interactor) -> None:
    """Test check action."""
    mock_locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("check", "e0")

        assert result == "Checked e0"
        mock_locator.check.assert_called_once_with(timeout=10_000)


# =============================================================================
# Action: uncheck
# =============================================================================


@pytest.mark.asyncio
async def test_interact_uncheck(interactor: Interactor) -> None:
    """Test uncheck action."""
    mock_locator = AsyncMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("uncheck", "e0")

        assert result == "Unchecked e0"
        mock_locator.uncheck.assert_called_once_with(timeout=10_000)
