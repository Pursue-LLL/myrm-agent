"""Tests for what a credential the vault filled leaves behind: the control holds it, the model never reads it back.

A control that shows the filled value, alone or next to other text, has it masked in every capture the session
registers (the follow-up snapshot, a later snapshot, the inspector), and a reply that quotes a backend error never
carries the value.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.desktop_session.secrecy import FilledSecrets
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxFailure, AxInvokeResult
from myrm_agent_harness.toolkits.computer_use.types import ActionResult, ComputerUseConfig, ScreenInfo

_PACKAGE = "myrm_agent_harness.toolkits.computer_use.desktop_session"
_CAPTURE = f"{_PACKAGE}.snapshot.capture_snapshot"
_INVOKE = f"{_PACKAGE}.interact.invoke_element"
_BBOX = f"{_PACKAGE}.interact.try_bbox_click"
_VAULT = "myrm_agent_harness.core.security.credential_vault.get_global_credential_vault"

SECRET = "hunter2-p@ss"
_Capture = tuple[SnapshotMeta, dict[str, ElementRef]]


def _login_form(*, password_shows: str = "", username_shows: str = "alice") -> _Capture:
    """A capture of a sign-in form as a platform script returns it; the password box is an ordinary text field."""
    meta = SnapshotMeta(ref_count=2, app_name="Portal", window_title="Sign in", scope="foreground", pid=100)
    refs = {
        "d0": ElementRef("d0", "AXTextField", "Username", BBox(0, 0, 100, 20), "position-0", value=username_shows),
        "d1": ElementRef("d1", "AXTextField", "Password", BBox(0, 30, 100, 20), "position-1", value=password_shows),
    }
    return meta, refs


def _screens(*captures: _Capture) -> AbstractContextManager[MagicMock | AsyncMock]:
    """The platform script answers each capture in turn."""
    return patch(_CAPTURE, side_effect=list(captures))


def _vault_holding(*, password: str = SECRET, totp: str = "123456") -> MagicMock:
    vault = MagicMock()
    vault.get_password.return_value = password
    vault.get_totp_token.return_value = totp
    return vault


@pytest.fixture
def session() -> DesktopSession:
    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
    return DesktopSession(backend=backend, config=ComputerUseConfig(screenshot_delay=0.0))


@pytest.fixture
def screenshot() -> AsyncMock:
    return AsyncMock(return_value=ActionResult(success=True, screenshot_base64="", screenshot_size=(10, 10)))


async def _fill(session: DesktopSession, label: str = "portal-login") -> str:
    """Fill the password box from the vault, the native route delivering it."""
    with patch(_INVOKE, return_value=AxInvokeResult.delivered("filled")), patch(_VAULT, return_value=_vault_holding()):
        return str(await session.desktop_interact(ref="d1", action="fill_credential", text=label))


class TestTheFilledValueIsNeverShownBack:
    async def test_the_follow_up_snapshot_reports_the_control_as_redacted(self, session: DesktopSession) -> None:
        with _screens(_login_form(), _login_form(password_shows=SECRET)):
            await session.desktop_snapshot()
            reply = await _fill(session)

        assert "[CREDENTIAL_FILLED]" in reply
        assert SECRET not in reply
        assert '~ @d1 AXTextField "Password" value="[REDACTED]" changed=[value]' in reply

    async def test_a_later_full_snapshot_is_redacted_too(self, session: DesktopSession, screenshot: AsyncMock) -> None:
        shown = _login_form(password_shows=SECRET)
        with _screens(_login_form(), shown, shown), patch.object(session, "take_screenshot", screenshot):
            await session.desktop_snapshot()
            await _fill(session)
            full = str(await session.desktop_snapshot(include_screenshot=True))

        assert SECRET not in full
        assert '@d1 AXTextField "Password" value="[REDACTED]"' in full

    async def test_the_registry_that_the_inspector_exports_holds_the_masked_value(
        self, session: DesktopSession
    ) -> None:
        with _screens(_login_form(), _login_form(password_shows=SECRET)):
            await session.desktop_snapshot()
            await _fill(session)

        assert session.ref_registry.resolve("d1").element.value == "[REDACTED]"

    async def test_a_retried_fill_that_typed_after_the_old_value_is_masked_too(self, session: DesktopSession) -> None:
        # Typing at the caret (Windows SendKeys, the coordinate fallback) leaves what the control held in front.
        with _screens(_login_form(), _login_form(password_shows=SECRET + SECRET)):
            await session.desktop_snapshot()
            reply = await _fill(session)

        assert SECRET not in reply
        assert 'value="[REDACTED][REDACTED]"' in reply

    async def test_the_text_around_a_secret_stays_readable(self, session: DesktopSession) -> None:
        with _screens(_login_form(), _login_form(password_shows=f"user: {SECRET}!")):
            await session.desktop_snapshot()
            reply = await _fill(session)

        assert 'value="user: [REDACTED]!"' in reply

    async def test_a_one_time_code_is_masked_like_a_password(self, session: DesktopSession) -> None:
        with _screens(_login_form(), _login_form(password_shows="123456")):
            await session.desktop_snapshot()
            reply = await _fill(session, label="portal-totp")

        assert "123456" not in reply
        assert 'value="[REDACTED]"' in reply


class TestOnlyWhatTheVaultFilledIsMasked:
    async def test_other_values_stay_readable(self, session: DesktopSession, screenshot: AsyncMock) -> None:
        shown = _login_form(password_shows=SECRET)
        with _screens(_login_form(), shown, shown), patch.object(session, "take_screenshot", screenshot):
            await session.desktop_snapshot()
            await _fill(session)
            full = str(await session.desktop_snapshot(include_screenshot=True))

        assert '@d0 AXTextField "Username" value="alice"' in full

    async def test_text_the_model_typed_itself_is_not_masked(self, session: DesktopSession) -> None:
        with (
            _screens(_login_form(), _login_form(username_shows="typed-by-model")),
            patch(_INVOKE, return_value=AxInvokeResult.delivered("filled")),
        ):
            await session.desktop_snapshot()
            reply = str(await session.desktop_interact(ref="d0", action="fill", text="typed-by-model"))

        assert 'value="typed-by-model"' in reply
        assert "[REDACTED]" not in reply

    async def test_an_empty_secret_masks_nothing(self, session: DesktopSession) -> None:
        with (
            _screens(_login_form(), _login_form(username_shows="")),
            patch(_INVOKE, return_value=AxInvokeResult.delivered("filled")),
            patch(_VAULT, return_value=_vault_holding(password="")),
        ):
            await session.desktop_snapshot()
            reply = str(await session.desktop_interact(ref="d1", action="fill_credential", text="portal-login"))

        assert "[REDACTED]" not in reply
        assert '~ @d0 AXTextField "Username" changed=[value]' in reply


class TestFilledSecrets:
    def test_nothing_is_redacted_before_a_secret_is_remembered(self) -> None:
        secrets = FilledSecrets()

        assert secrets.redact("abc") == "abc"
        assert (
            secrets.mask({"d0": ElementRef("d0", "AXTextField", "x", BBox(0, 0, 1, 1), "k", value="abc")})["d0"].value
            == "abc"
        )

    def test_an_empty_secret_redacts_nothing(self) -> None:
        secrets = FilledSecrets()
        secrets.remember("")

        assert secrets.redact("abc") == "abc"

    @pytest.mark.parametrize("remembered", [("abc", "abcdef"), ("abcdef", "abc")])
    def test_a_secret_that_contains_another_is_replaced_whole_in_either_order(
        self, remembered: tuple[str, str]
    ) -> None:
        secrets = FilledSecrets()
        for secret in remembered:
            secrets.remember(secret)

        assert secrets.redact("x abcdef y abc") == "x [REDACTED] y [REDACTED]"

    def test_a_masked_capture_leaves_the_untouched_elements_as_they_were(self) -> None:
        secrets = FilledSecrets()
        secrets.remember(SECRET)
        plain = ElementRef("d0", "AXTextField", "Username", BBox(0, 0, 1, 1), "k0", value="alice")
        holding = ElementRef("d1", "AXTextField", "Password", BBox(0, 0, 1, 1), "k1", value=SECRET)

        masked = secrets.mask({"d0": plain, "d1": holding})

        assert masked["d0"] is plain
        assert masked["d1"].value == "[REDACTED]"
        assert holding.value == SECRET


class TestAReplyThatQuotesABackendErrorNeverCarriesTheSecret:
    @pytest.mark.parametrize("failure", [AxFailure.UNKNOWN, AxFailure.STALE])
    async def test_a_native_failure_that_is_not_retried(self, session: DesktopSession, failure: AxFailure) -> None:
        native = AxInvokeResult.failed(failure, f"UIA call failed while typing {SECRET}")
        with _screens(_login_form()), patch(_INVOKE, return_value=native), patch(_VAULT, return_value=_vault_holding()):
            await session.desktop_snapshot()
            reply = str(await session.desktop_interact(ref="d1", action="fill_credential", text="portal-login"))

        assert SECRET not in reply
        assert "[REDACTED]" in reply

    async def test_a_native_refusal_followed_by_a_failed_coordinate_fallback(self, session: DesktopSession) -> None:
        native = AxInvokeResult.failed(AxFailure.UNSUPPORTED, f"no editable text for {SECRET}")
        failed_click = ActionResult(success=False, error=f"typing {SECRET} failed")
        with (
            _screens(_login_form()),
            patch(_INVOKE, return_value=native),
            patch(_BBOX, AsyncMock(return_value=failed_click)),
            patch(_VAULT, return_value=_vault_holding()),
        ):
            await session.desktop_snapshot()
            reply = str(await session.desktop_interact(ref="d1", action="fill_credential", text="portal-login"))

        assert "desktop_interact failed" in reply
        assert SECRET not in reply
        assert "no editable text for [REDACTED]" in reply
        assert "typing [REDACTED] failed" in reply

    async def test_an_error_of_an_action_that_filled_no_secret_is_left_as_it_is(self, session: DesktopSession) -> None:
        native = AxInvokeResult.failed(AxFailure.UNKNOWN, "UIA call failed")
        with _screens(_login_form()), patch(_INVOKE, return_value=native):
            await session.desktop_snapshot()
            reply = str(await session.desktop_interact(ref="d0", action="fill", text="alice"))

        assert "UIA call failed" in reply
        assert "[REDACTED]" not in reply
