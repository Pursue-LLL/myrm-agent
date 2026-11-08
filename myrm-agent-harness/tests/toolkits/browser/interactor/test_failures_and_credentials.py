"""Interactor failure reporting and credential entry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from patchright.async_api import Page

from myrm_agent_harness.toolkits.browser.session.interactor import Interactor
from myrm_agent_harness.toolkits.browser.snapshot import RefInfo

# =============================================================================
# Failure reporting
# =============================================================================


@pytest.mark.asyncio
async def test_interact_exception_tab_closed():
    page = AsyncMock(spec=Page)
    page.is_closed.return_value = True
    interactor = Interactor(page, {"e0": RefInfo(role="button", name="B", nth=0)})

    with (
        patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator") as mock_resolve,
        patch("myrm_agent_harness.toolkits.browser.session.interactor.logger.warning") as mock_warn,
    ):
        mock_loc = AsyncMock()
        mock_loc.click.side_effect = Exception("TargetClosedError")
        mock_resolve.return_value = mock_loc

        res = await interactor.interact("click", "e0")

    assert "The browser tab was closed or detached" in res
    mock_warn.assert_called_once_with("Browser interaction target closed: TargetClosedError")


@pytest.mark.asyncio
async def test_interact_target_closed_on_open_page_is_reraised_with_one_warning():
    page = AsyncMock(spec=Page)
    page.is_closed.return_value = False
    interactor = Interactor(page, {"e0": RefInfo(role="button", name="B", nth=0)})

    with (
        patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator") as mock_resolve,
        patch("myrm_agent_harness.toolkits.browser.session.interactor.logger.warning") as mock_warn,
    ):
        mock_loc = AsyncMock()
        mock_loc.click.side_effect = Exception("TargetClosedError")
        mock_resolve.return_value = mock_loc

        with pytest.raises(Exception, match="TargetClosedError"):
            await interactor.interact("click", "e0")

    mock_warn.assert_called_once_with("Browser interaction failed: %s", "TargetClosedError")


@pytest.mark.asyncio
async def test_interact_timeout_is_reraised_with_one_warning(mock_page: MagicMock, ref_info: RefInfo) -> None:
    """A timeout is logged once and re-raised for the caller, never answered as a message."""
    interactor = Interactor(mock_page, {"e0": ref_info})
    locator = AsyncMock()
    locator.click.side_effect = Exception("Timeout 30000 ms exceeded")
    with (
        patch(
            "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
            return_value=locator,
        ),
        patch("myrm_agent_harness.toolkits.browser.session.interactor.logger.warning") as mock_warn,
        pytest.raises(Exception, match="Timeout"),
    ):
        await interactor.interact("click", "e0", "")

    mock_warn.assert_called_once_with("Browser interaction failed: %s", "Timeout 30000 ms exceeded")


@pytest.mark.asyncio
async def test_interact_type_exception():
    page = AsyncMock(spec=Page)
    interactor = Interactor(page, {"e0": RefInfo(role="button", name="B", nth=0)})

    with patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator") as mock_resolve:
        mock_loc = AsyncMock()
        mock_loc.get_attribute.side_effect = Exception("error")
        mock_resolve.return_value = mock_loc

        res = await interactor.interact("type", "e0", "test")
        assert "Typed 'test'" in res


@pytest.mark.asyncio
async def test_interact_fill_exception():
    page = AsyncMock(spec=Page)
    interactor = Interactor(page, {"e0": RefInfo(role="button", name="B", nth=0)})

    with patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator") as mock_resolve:
        mock_loc = AsyncMock()
        mock_loc.get_attribute.side_effect = Exception("error")
        mock_resolve.return_value = mock_loc

        res = await interactor.interact("fill", "e0", "test")
        assert "Filled" in res


# =============================================================================
# Credential entry
# =============================================================================


@pytest.mark.asyncio
async def test_interact_password_blocked():
    page = AsyncMock(spec=Page)
    interactor = Interactor(page, {"e0": RefInfo(role="textbox", name="Password", nth=0)})

    with patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator") as mock_resolve:
        mock_loc = AsyncMock()
        mock_loc.get_attribute.return_value = "password"
        mock_resolve.return_value = mock_loc

        with pytest.raises(
            ValueError,
            match="SecurityError: Plain text typing into a password field is strictly forbidden",
        ):
            await interactor.interact("type", "e0", "mysecret")

        with pytest.raises(
            ValueError,
            match="SecurityError: Plain text filling into a password field is strictly forbidden",
        ):
            await interactor.interact("fill", "e0", "mysecret")


@pytest.mark.asyncio
async def test_interact_fill_credential():
    page = AsyncMock(spec=Page)
    interactor = Interactor(page, {"e0": RefInfo(role="textbox", name="Password", nth=0)})

    with patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator") as mock_resolve:
        mock_loc = AsyncMock()
        mock_resolve.return_value = mock_loc

        with patch(
            "myrm_agent_harness.core.security.credential_vault.CredentialVault.get_password",
            return_value="secret123",
        ):
            res = await interactor.interact("fill_credential", "e0", "github-personal")
            assert "Filled credential 'github-personal'" in res
            mock_loc.fill.assert_called_once_with("secret123", timeout=10000)


@pytest.mark.asyncio
async def test_interact_fill_credential_totp():
    page = AsyncMock(spec=Page)
    interactor = Interactor(page, {"e0": RefInfo(role="textbox", name="Code", nth=0)})

    with patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator") as mock_resolve:
        mock_loc = AsyncMock()
        mock_resolve.return_value = mock_loc

        with patch(
            "myrm_agent_harness.core.security.credential_vault.CredentialVault.get_totp_token",
            return_value="123456",
        ):
            res = await interactor.interact("fill_credential", "e0", "github-personal-totp")
            assert "Filled credential 'github-personal-totp'" in res
            mock_loc.fill.assert_called_once_with("123456", timeout=10000)


@pytest.mark.asyncio
async def test_interact_fill_credential_vault_error(mock_page: MagicMock) -> None:
    """Vault lookup failure surfaces as a clear ValueError."""
    interactor = Interactor(mock_page, {"e0": RefInfo(role="textbox", name="Code", nth=0)})

    with patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator") as mock_resolve:
        mock_resolve.return_value = AsyncMock()
        with (
            patch(
                "myrm_agent_harness.core.security.credential_vault.CredentialVault.get_password",
                side_effect=Exception("vault locked"),
            ),
            pytest.raises(ValueError, match="Failed to retrieve credential"),
        ):
            await interactor.interact("fill_credential", "e0", "github-personal")
