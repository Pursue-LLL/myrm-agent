"""Tests for desktop_interact fill_credential action in DesktopSession.

Covers:
- fill_credential resolves password from vault and dispatches as 'fill'
- fill_credential resolves TOTP token (label ending with '-totp')
- fill_credential returns error when vault label is missing
- fill_credential returns error when credential has no password
- fill_credential success message contains [CREDENTIAL_FILLED] marker
- fill_credential does NOT appear in invoke_element args (converted to 'fill')
- the vault secret reaches backend.type_text through the real bbox fallback
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxFailure, AxInvokeResult
from myrm_agent_harness.toolkits.computer_use.types import ActionResult

# The native route refused the fill, which proves nothing was typed; only then may the coordinate path type it.
_UNSUPPORTED = AxInvokeResult.failed(AxFailure.UNSUPPORTED, "AX failed")


@pytest.fixture
def mock_backend():
    return MagicMock()


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.screenshot_delay = 0.0
    return config


def _setup_session_with_ref(session: DesktopSession, bbox: BBox | None = None) -> tuple[str, ElementRef]:
    """Give the session a fresh snapshot holding one text field; returns the field's @dref id and element."""
    session._last_snapshot_time = time.time()
    meta = SnapshotMeta(ref_count=1, app_name="Login", window_title="Sign in", scope="foreground")
    field = ElementRef(
        ref_id="c0", role="textField", name="Username", bbox=bbox or BBox(0, 0, 100, 30), backend_key="key0"
    )
    (ref_id,) = session._refs.adopt({"c0": field}, meta)
    return ref_id, session._refs.resolve(ref_id).element


@pytest.mark.asyncio
async def test_fill_credential_resolves_password(mock_backend, mock_config):
    """fill_credential should resolve the vault label to a password and dispatch as 'fill'."""
    session = DesktopSession(backend=mock_backend, config=mock_config)
    ref_id, elem = _setup_session_with_ref(session)

    with (
        patch("myrm_agent_harness.toolkits.computer_use.desktop_session.interact.invoke_element") as mock_invoke,
        patch("myrm_agent_harness.core.security.credential_vault.get_global_credential_vault") as mock_get_vault,
    ):
        vault = MagicMock()
        vault.get_password.return_value = "s3cret_p@ss"
        mock_get_vault.return_value = vault
        mock_invoke.return_value.success = True
        session.desktop_snapshot = AsyncMock(return_value="Updated tree")

        result = await session.desktop_interact(ref=ref_id, action="fill_credential", text="my-login")

    vault.get_password.assert_called_once_with("my-login")
    mock_invoke.assert_called_once()
    call_args = mock_invoke.call_args
    assert call_args[0][:4] == (mock_backend, elem, "fill", "s3cret_p@ss")
    assert "CREDENTIAL_FILLED" in result
    assert "my-login" in result


@pytest.mark.asyncio
async def test_fill_credential_resolves_totp(mock_backend, mock_config):
    """Label ending with '-totp' should resolve via get_totp_token."""
    session = DesktopSession(backend=mock_backend, config=mock_config)
    ref_id, elem = _setup_session_with_ref(session)

    with (
        patch("myrm_agent_harness.toolkits.computer_use.desktop_session.interact.invoke_element") as mock_invoke,
        patch("myrm_agent_harness.core.security.credential_vault.get_global_credential_vault") as mock_get_vault,
    ):
        vault = MagicMock()
        vault.get_totp_token.return_value = "123456"
        mock_get_vault.return_value = vault
        mock_invoke.return_value.success = True
        session.desktop_snapshot = AsyncMock(return_value="Updated tree")

        result = await session.desktop_interact(ref=ref_id, action="fill_credential", text="my-login-totp")

    vault.get_totp_token.assert_called_once_with("my-login-totp")
    mock_invoke.assert_called_once()
    call_args = mock_invoke.call_args
    assert call_args[0][:4] == (mock_backend, elem, "fill", "123456")
    assert "CREDENTIAL_FILLED" in result


@pytest.mark.asyncio
async def test_fill_credential_missing_label_returns_error(mock_backend, mock_config):
    """Vault KeyError should return a user-friendly error message."""
    session = DesktopSession(backend=mock_backend, config=mock_config)
    ref_id, _ = _setup_session_with_ref(session)

    with patch("myrm_agent_harness.core.security.credential_vault.get_global_credential_vault") as mock_get_vault:
        vault = MagicMock()
        vault.get_password.side_effect = KeyError("Credential label 'unknown' not found in vault.")
        mock_get_vault.return_value = vault

        result = await session.desktop_interact(ref=ref_id, action="fill_credential", text="unknown")

    assert "Failed to retrieve credential" in result
    assert "unknown" in result


@pytest.mark.asyncio
async def test_fill_credential_no_password_returns_error(mock_backend, mock_config):
    """Vault ValueError (no password configured) should return a user-friendly error."""
    session = DesktopSession(backend=mock_backend, config=mock_config)
    ref_id, _ = _setup_session_with_ref(session)

    with patch("myrm_agent_harness.core.security.credential_vault.get_global_credential_vault") as mock_get_vault:
        vault = MagicMock()
        vault.get_password.side_effect = ValueError("Credential 'aws' does not have a password configured.")
        mock_get_vault.return_value = vault

        result = await session.desktop_interact(ref=ref_id, action="fill_credential", text="aws")

    assert "Failed to retrieve credential" in result
    assert "aws" in result


@pytest.mark.asyncio
async def test_fill_credential_success_message_with_multimodal_blocks(mock_backend, mock_config):
    """fill_credential with multimodal follow_up should prepend CREDENTIAL_FILLED marker."""
    session = DesktopSession(backend=mock_backend, config=mock_config)
    ref_id, _ = _setup_session_with_ref(session)

    block = MagicMock()
    block.text = "tree text"

    with (
        patch("myrm_agent_harness.toolkits.computer_use.desktop_session.interact.invoke_element") as mock_invoke,
        patch("myrm_agent_harness.core.security.credential_vault.get_global_credential_vault") as mock_get_vault,
    ):
        vault = MagicMock()
        vault.get_password.return_value = "pass123"
        mock_get_vault.return_value = vault
        mock_invoke.return_value.success = True
        session.desktop_snapshot = AsyncMock(return_value=[block])

        result = await session.desktop_interact(ref=ref_id, action="fill_credential", text="my-cred")

    assert isinstance(result, list)
    assert "CREDENTIAL_FILLED" in block.text


@pytest.mark.asyncio
async def test_fill_credential_ax_fail_falls_back_to_bbox(mock_backend, mock_config):
    """When AX invoke fails, fill_credential should fall back to bbox with resolved credentials."""
    session = DesktopSession(backend=mock_backend, config=mock_config)
    ref_id, elem = _setup_session_with_ref(session)

    with (
        patch("myrm_agent_harness.toolkits.computer_use.desktop_session.interact.invoke_element") as mock_invoke,
        patch("myrm_agent_harness.toolkits.computer_use.desktop_session.interact.try_bbox_click") as mock_bbox,
        patch("myrm_agent_harness.core.security.credential_vault.get_global_credential_vault") as mock_get_vault,
    ):
        vault = MagicMock()
        vault.get_password.return_value = "secret"
        mock_get_vault.return_value = vault
        mock_invoke.return_value = _UNSUPPORTED
        mock_bbox.return_value.success = True
        session.desktop_snapshot = AsyncMock(return_value="Updated tree")

        result = await session.desktop_interact(ref=ref_id, action="fill_credential", text="login")

    mock_bbox.assert_called_once_with(session, elem, "fill", "secret", None)
    assert "CREDENTIAL_FILLED" in result


@pytest.mark.asyncio
async def test_fill_credential_secret_reaches_backend_type_text(mock_backend, mock_config):
    """End to end through the real bbox fallback: the vault secret is what `backend.type_text` receives."""
    mock_backend.click = AsyncMock(return_value=ActionResult(success=True))
    mock_backend.type_text = AsyncMock(return_value=ActionResult(success=True))
    session = DesktopSession(backend=mock_backend, config=mock_config)
    ref_id, _ = _setup_session_with_ref(session, bbox=BBox(x=10, y=20, width=100, height=30))

    with (
        patch("myrm_agent_harness.toolkits.computer_use.desktop_session.interact.invoke_element") as mock_invoke,
        patch("myrm_agent_harness.core.security.credential_vault.get_global_credential_vault") as mock_get_vault,
    ):
        vault = MagicMock()
        vault.get_password.return_value = "p\u00e4ss-\u5bc6\u7801"
        mock_get_vault.return_value = vault
        mock_invoke.return_value = _UNSUPPORTED
        session.desktop_snapshot = AsyncMock(return_value="Updated tree")

        result = await session.desktop_interact(ref=ref_id, action="fill_credential", text="login")

    mock_backend.type_text.assert_awaited_once_with("p\u00e4ss-\u5bc6\u7801")
    assert "CREDENTIAL_FILLED" in result
    assert "p\u00e4ss" not in result


@pytest.mark.asyncio
async def test_fill_credential_both_ax_and_bbox_fail(mock_backend, mock_config):
    """When both AX and bbox fail, should return combined error message."""
    session = DesktopSession(backend=mock_backend, config=mock_config)
    ref_id, _ = _setup_session_with_ref(session)

    with (
        patch("myrm_agent_harness.toolkits.computer_use.desktop_session.interact.invoke_element") as mock_invoke,
        patch("myrm_agent_harness.toolkits.computer_use.desktop_session.interact.try_bbox_click") as mock_bbox,
        patch("myrm_agent_harness.core.security.credential_vault.get_global_credential_vault") as mock_get_vault,
    ):
        vault = MagicMock()
        vault.get_password.return_value = "secret"
        mock_get_vault.return_value = vault
        mock_invoke.return_value = _UNSUPPORTED
        mock_bbox.return_value.success = False
        mock_bbox.return_value.error = "no bbox"

        result = await session.desktop_interact(ref=ref_id, action="fill_credential", text="login")

    assert "desktop_interact failed" in result
    assert "AX failed" in result
    assert "no bbox" in result
