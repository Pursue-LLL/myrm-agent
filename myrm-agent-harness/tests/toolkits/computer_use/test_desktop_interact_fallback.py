"""Tests for what desktop_interact does after a native action failed: the coordinate click only follows a failure
that proves nothing reached the element, an outcome that is stale or unknown is reported, never repeated, and a click
delivered for a text entry is gated like any other click."""

from __future__ import annotations

import time
from typing import NamedTuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxFailure, AxInvokeResult
from myrm_agent_harness.toolkits.computer_use.types import (
    ActionResult,
    ComputerUseConfig,
    DesktopInteractAction,
    ScreenInfo,
)

_PACKAGE = "myrm_agent_harness.toolkits.computer_use.desktop_session"
_INVOKE = f"{_PACKAGE}.interact.invoke_element"
_BBOX = f"{_PACKAGE}.interact.try_bbox_click"
_VAULT = "myrm_agent_harness.core.security.credential_vault.get_global_credential_vault"


class Outcome(NamedTuple):
    """The tool reply and the collaborators the action may have reached."""

    reply: str
    native: MagicMock
    coordinate_click: AsyncMock
    follow_up: AsyncMock


@pytest.fixture
def backend() -> MagicMock:
    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
    backend.click = AsyncMock(return_value=ActionResult(success=True))
    backend.type_text = AsyncMock(return_value=ActionResult(success=True))
    return backend


def _session_holding(backend: MagicMock, *, app: str = "Mail", name: str = "Send") -> tuple[DesktopSession, str]:
    """A session whose model has just seen one element of `app`; returns it and the element's @dref id."""
    session = DesktopSession(backend=backend, config=ComputerUseConfig(screenshot_delay=0.0))
    meta = SnapshotMeta(ref_count=1, app_name=app, window_title="Inbox", scope="target" if app else "foreground")
    element = ElementRef(ref_id="c0", role="AXButton", name=name, bbox=BBox(10, 20, 100, 30), backend_key="3")
    (ref_id,) = session._refs.adopt({"c0": element}, meta)
    session._last_snapshot_time = time.time()
    return session, ref_id


async def _interact(
    session: DesktopSession,
    ref_id: str,
    native_result: AxInvokeResult,
    *,
    action: DesktopInteractAction = "click",
    text: str = "",
) -> Outcome:
    with (
        patch(_INVOKE, return_value=native_result) as native,
        patch(_BBOX, AsyncMock(return_value=ActionResult(success=True))) as coordinate_click,
        patch.object(session, "desktop_snapshot", AsyncMock(return_value="follow-up")) as follow_up,
        patch.object(session, "_capture_guard_screenshot", AsyncMock(return_value=("", (0, 0)))),
    ):
        reply = str(await session.desktop_interact(ref=ref_id, action=action, text=text))
    return Outcome(reply, native, coordinate_click, follow_up)


class TestAnUnsupportedActionFallsBackToTheCoordinateClick:
    async def test_the_element_is_clicked_by_its_coordinates(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend)

        outcome = await _interact(session, ref_id, AxInvokeResult.failed(AxFailure.UNSUPPORTED, "no such action"))

        assert f"Action 'click' on @{ref_id} succeeded." in outcome.reply
        assert outcome.native.call_count == 1
        outcome.coordinate_click.assert_awaited_once()
        outcome.follow_up.assert_awaited_once()


class TestAnOutcomeThatIsNotKnownToBeUndeliveredIsNeverRepeated:
    async def test_a_stale_element_is_not_clicked_at_its_old_coordinates(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend)

        outcome = await _interact(session, ref_id, AxInvokeResult.failed(AxFailure.STALE, "Stale element index 3"))

        assert outcome.reply.startswith(f"desktop_interact stopped for @{ref_id}: the element is no longer where")
        assert "(Stale element index 3)" in outcome.reply
        assert "desktop_snapshot_tool(scope='target', app_name='Mail')" in outcome.reply
        assert outcome.native.call_count == 1
        outcome.coordinate_click.assert_not_called()
        outcome.follow_up.assert_not_called()

    async def test_an_unknown_outcome_is_reported_and_not_retried(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend)

        outcome = await _interact(session, ref_id, AxInvokeResult.failed(AxFailure.UNKNOWN, "AX invoke timed out"))

        assert outcome.reply.startswith(f"desktop_interact result unknown for @{ref_id}: AX invoke timed out.")
        assert "may or may not have been delivered, so it was not retried" in outcome.reply
        assert "desktop_snapshot_tool(scope='target', app_name='Mail')" in outcome.reply
        assert "duplicate its effect" in outcome.reply
        assert outcome.native.call_count == 1
        outcome.coordinate_click.assert_not_called()
        outcome.follow_up.assert_not_called()

    async def test_a_failure_without_a_class_is_treated_as_unknown(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend)

        outcome = await _interact(session, ref_id, AxInvokeResult(success=False, error="odd"))

        assert "result unknown" in outcome.reply
        outcome.coordinate_click.assert_not_called()

    async def test_the_hint_reads_the_foreground_when_the_snapshot_named_no_application(
        self, backend: MagicMock
    ) -> None:
        session, ref_id = _session_holding(backend, app="")

        outcome = await _interact(session, ref_id, AxInvokeResult.failed(AxFailure.UNKNOWN, "AX invoke timed out"))

        assert "desktop_snapshot_tool(scope='foreground')" in outcome.reply

    async def test_a_credential_is_not_typed_after_an_unknown_outcome(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend, name="Password")

        with (
            patch(_INVOKE, return_value=AxInvokeResult.failed(AxFailure.UNKNOWN, "AX invoke timed out")),
            patch(_VAULT) as vault,
            patch.object(session, "desktop_snapshot", AsyncMock(return_value="follow-up")),
        ):
            vault.return_value.get_password.return_value = "s3cret"
            reply = str(await session.desktop_interact(ref=ref_id, action="fill_credential", text="login"))

        assert "result unknown" in reply
        backend.click.assert_not_called()
        backend.type_text.assert_not_called()


class TestAClickDeliveredForATextEntryIsGatedLikeAnyClick:
    """The coordinate fallback clicks the element before it types, so the verb's name says nothing about what the
    control receives once the native route has declined."""

    _NO_EDITABLE_TEXT = AxInvokeResult.failed(AxFailure.UNSUPPORTED, "element exposes no editable text interface")

    async def test_the_user_is_asked_before_a_text_entry_becomes_a_click(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend, name="Delete Account")

        with patch("langgraph.types.interrupt", return_value={"decision": "approve"}) as ask:
            outcome = await _interact(session, ref_id, self._NO_EDITABLE_TEXT, action="fill", text="hello")

        ask.assert_called_once()
        assert ask.call_args[0][0]["tool_input"] == {"action": "click", "ref": ref_id, "text": "hello"}
        assert f"Action 'fill' on @{ref_id} succeeded." in outcome.reply
        outcome.coordinate_click.assert_awaited_once()

    async def test_a_refusal_keeps_the_click_from_happening(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend, name="Delete Account")

        with patch("langgraph.types.interrupt", return_value={"decision": "reject"}):
            outcome = await _interact(session, ref_id, self._NO_EDITABLE_TEXT, action="type", text="hello")

        assert outcome.reply.startswith("[BLOCKED] User rejected this action")
        assert outcome.native.call_count == 1
        outcome.coordinate_click.assert_not_called()
        outcome.follow_up.assert_not_called()

    async def test_a_credential_label_not_the_secret_goes_to_the_approval(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend, name="Delete Account")

        with (
            patch("langgraph.types.interrupt", return_value={"decision": "reject"}) as ask,
            patch(_VAULT) as vault,
        ):
            vault.return_value.get_password.return_value = "s3cret"
            outcome = await _interact(session, ref_id, self._NO_EDITABLE_TEXT, action="fill_credential", text="login")

        assert "s3cret" not in str(ask.call_args)
        assert "s3cret" not in outcome.reply
        outcome.coordinate_click.assert_not_called()

    async def test_nothing_is_asked_when_the_native_route_entered_the_text(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend, name="Delete Account")

        with patch("langgraph.types.interrupt") as ask:
            outcome = await _interact(
                session, ref_id, AxInvokeResult.delivered("AX fill succeeded"), action="fill", text="hello"
            )

        ask.assert_not_called()
        assert f"Action 'fill' on @{ref_id} succeeded." in outcome.reply
        outcome.coordinate_click.assert_not_called()

    async def test_nothing_is_asked_about_a_harmless_control(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend, name="Send")

        with patch("langgraph.types.interrupt") as ask:
            outcome = await _interact(session, ref_id, self._NO_EDITABLE_TEXT, action="fill", text="hello")

        ask.assert_not_called()
        outcome.coordinate_click.assert_awaited_once()

    async def test_an_activation_is_asked_about_once_not_again_at_the_fallback(self, backend: MagicMock) -> None:
        session, ref_id = _session_holding(backend, name="Delete Account")

        with patch("langgraph.types.interrupt", return_value={"decision": "approve"}) as ask:
            outcome = await _interact(session, ref_id, self._NO_EDITABLE_TEXT, action="click")

        ask.assert_called_once()
        outcome.coordinate_click.assert_awaited_once()


class TestTheStaleReferenceHintNamesTheApplicationTheModelWorkedIn:
    async def test_a_background_application_is_read_by_name(self, backend: MagicMock) -> None:
        session, _ = _session_holding(backend, app="Notes")

        reply = str(await session.desktop_interact(ref="d99", action="click"))

        assert "desktop_snapshot_tool(scope='target', app_name='Notes')" in reply

    async def test_the_foreground_is_read_when_nothing_was_registered(self, backend: MagicMock) -> None:
        session = DesktopSession(backend=backend, config=ComputerUseConfig(screenshot_delay=0.0))

        reply = str(await session.desktop_interact(ref="d99", action="click"))

        assert "desktop_snapshot_tool(scope='foreground')" in reply
