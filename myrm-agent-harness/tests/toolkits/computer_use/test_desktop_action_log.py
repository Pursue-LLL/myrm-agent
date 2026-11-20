"""Tests for the structured log lines of the desktop tools: one line per desktop_interact call on every way out,
one per refused or withheld vision screenshot, and in neither an element, a text, a value, an application or a
window title."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import NamedTuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.desktop_session.action_log import InteractTrace
from myrm_agent_harness.toolkits.computer_use.dref.errors import AXTreeEmptyError
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxFailure, AxInvokeResult
from myrm_agent_harness.toolkits.computer_use.types import (
    ActionResult,
    ComputerUseConfig,
    DesktopInteractAction,
    ScreenContext,
    ScreenInfo,
)

_PACKAGE = "myrm_agent_harness.toolkits.computer_use.desktop_session"
_LOGGER = f"{_PACKAGE}.action_log"
_INVOKE = f"{_PACKAGE}.interact.invoke_element"
_BBOX = f"{_PACKAGE}.interact.try_bbox_click"
_REREAD = f"{_PACKAGE}.guards.capture_snapshot"
_VAULT = "myrm_agent_harness.core.security.credential_vault.get_global_credential_vault"

_APP = "Contoso Mail"
_TITLE = "Quarterly Inbox"
_ELEMENT = "Account 4242"
_TEXT = "hunter2-value"

_NO_ACTION = AxInvokeResult.failed(AxFailure.UNSUPPORTED, "no such action")


class Run(NamedTuple):
    """The tool reply and the native call it may have made."""

    reply: str
    native: MagicMock


@pytest.fixture(autouse=True)
def _capture_the_action_log(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_LOGGER)


@pytest.fixture
def backend() -> MagicMock:
    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
    return backend


def _meta(app: str = _APP) -> SnapshotMeta:
    return SnapshotMeta(ref_count=1, app_name=app, window_title=_TITLE, scope="target")


def _element(name: str = _ELEMENT) -> ElementRef:
    return ElementRef(ref_id="c0", role="AXButton", name=name, bbox=BBox(10, 20, 100, 30), backend_key="3")


def _session_holding(backend: MagicMock, *, name: str = _ELEMENT, delay: float = 0.0) -> tuple[DesktopSession, str]:
    """A session whose model has just seen one element; returns it and the element's @dref id."""
    session = DesktopSession(backend=backend, config=ComputerUseConfig(screenshot_delay=delay))
    (ref_id,) = session._refs.adopt({"c0": _element(name)}, _meta())
    session._last_snapshot_time = time.time()
    return session, ref_id


async def _interact(
    session: DesktopSession,
    ref_id: str,
    native: AxInvokeResult,
    *,
    action: DesktopInteractAction = "click",
    text: str = "",
    bbox: ActionResult | None = None,
) -> Run:
    with (
        patch(_INVOKE, return_value=native) as invoke,
        patch(_BBOX, AsyncMock(return_value=bbox or ActionResult(success=True))),
        patch.object(session, "desktop_snapshot", AsyncMock(return_value="follow-up")),
        patch.object(session, "_capture_guard_screenshot", AsyncMock(return_value=("", (0, 0)))),
    ):
        return Run(str(await session.desktop_interact(ref=ref_id, action=action, text=text)), invoke)


def _lines(caplog: pytest.LogCaptureFixture) -> list[dict[str, str]]:
    """The action log lines as field maps; `event` is the word after the tag."""
    lines = []
    for record in caplog.records:
        if record.name == _LOGGER:
            tag, event, *fields = record.getMessage().split()
            assert tag == "[DESKTOP]"
            lines.append({"event": event, **dict(field.split("=", 1) for field in fields)})
    return lines


def _the_line(caplog: pytest.LogCaptureFixture) -> dict[str, str]:
    lines = _lines(caplog)
    assert len(lines) == 1, lines
    return lines[0]


def _logged_text(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(record.getMessage() for record in caplog.records if record.name == _LOGGER)


class TestHowTheCallEnded:
    async def test_a_line_names_the_verb_and_how_long_the_call_took(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session, ref_id = _session_holding(backend, delay=0.05)

        await _interact(session, ref_id, AxInvokeResult.delivered("toggled"), action="toggle")

        line = _the_line(caplog)
        assert line["event"] == "interact"
        assert line["verb"] == "toggle"
        assert 40 <= int(line["duration_ms"]) < 10_000

    @pytest.mark.parametrize(
        ("native", "bbox", "outcome", "fallback"),
        [
            pytest.param(AxInvokeResult.delivered("ok"), None, "delivered", "False", id="native-delivered"),
            pytest.param(_NO_ACTION, None, "delivered", "True", id="coordinate-click-delivered"),
            pytest.param(
                _NO_ACTION, ActionResult(success=False, error="off-screen"), "unsupported", "True", id="no-route-left"
            ),
            pytest.param(AxInvokeResult.failed(AxFailure.STALE, "gone"), None, "stale", "False", id="stale"),
            pytest.param(AxInvokeResult.failed(AxFailure.UNKNOWN, "timed out"), None, "unknown", "False", id="unknown"),
            pytest.param(AxInvokeResult(success=False, error="odd"), None, "unknown", "False", id="unclassified"),
        ],
    )
    async def test_the_outcome_and_whether_the_coordinate_click_was_tried(
        self,
        backend: MagicMock,
        caplog: pytest.LogCaptureFixture,
        native: AxInvokeResult,
        bbox: ActionResult | None,
        outcome: str,
        fallback: str,
    ) -> None:
        session, ref_id = _session_holding(backend)

        await _interact(session, ref_id, native, bbox=bbox)

        line = _the_line(caplog)
        assert (line["outcome"], line["fallback"], line["revalidated"]) == (outcome, fallback, "False")


class TestARefusalIsOneOutcome:
    """Whatever stops a call before anything reaches the element is a refusal: one class, one line."""

    async def test_a_locked_screen(self, backend: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        backend.is_screen_locked.return_value = True
        session, ref_id = _session_holding(backend)

        run = await _interact(session, ref_id, AxInvokeResult.delivered("ok"))

        run.native.assert_not_called()
        assert _the_line(caplog)["outcome"] == "refused"

    async def test_a_denied_application(self, backend: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        session, ref_id = _session_holding(backend)

        with patch.object(
            session, "check_app_approval", AsyncMock(return_value=ActionResult(success=False, error="declined"))
        ):
            run = await _interact(session, ref_id, AxInvokeResult.delivered("ok"))

        assert run.reply.startswith("Control denied")
        run.native.assert_not_called()
        assert _the_line(caplog)["outcome"] == "refused"

    async def test_a_reference_the_registry_no_longer_holds(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session, _ = _session_holding(backend)

        run = await _interact(session, "d99", AxInvokeResult.delivered("ok"))

        run.native.assert_not_called()
        assert _the_line(caplog)["outcome"] == "refused"

    async def test_a_control_the_user_rejects(self, backend: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        session, ref_id = _session_holding(backend, name="Delete Account")

        with patch("langgraph.types.interrupt", return_value={"decision": "reject"}):
            run = await _interact(session, ref_id, AxInvokeResult.delivered("ok"))

        run.native.assert_not_called()
        assert _the_line(caplog)["outcome"] == "refused"

    async def test_a_click_the_user_rejects_after_the_native_route_declined_a_text_entry(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session, ref_id = _session_holding(backend, name="Delete Account")

        with patch("langgraph.types.interrupt", return_value={"decision": "reject"}):
            await _interact(session, ref_id, _NO_ACTION, action="type", text="hello")

        line = _the_line(caplog)
        assert (line["outcome"], line["fallback"]) == ("refused", "False")

    async def test_a_credential_the_vault_cannot_give(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session, ref_id = _session_holding(backend)

        with patch(_VAULT) as vault:
            vault.return_value.get_password.side_effect = KeyError("no such label")
            run = await _interact(session, ref_id, AxInvokeResult.delivered("ok"), action="fill_credential", text="x")

        assert run.reply.startswith("Failed to retrieve credential")
        run.native.assert_not_called()
        assert _the_line(caplog)["outcome"] == "refused"


class TestTheApprovalReread:
    async def test_a_reread_that_still_holds_is_flagged_on_a_delivered_call(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session, ref_id = _session_holding(backend)
        session._last_snapshot_time = 0.0

        with patch(_REREAD, return_value=(_meta(), {"c0": _element()})):
            await _interact(session, ref_id, AxInvokeResult.delivered("ok"))

        line = _the_line(caplog)
        assert (line["outcome"], line["revalidated"]) == ("delivered", "True")

    async def test_a_reread_that_refuses_is_flagged_on_a_refused_call(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session, ref_id = _session_holding(backend)
        session._last_snapshot_time = 0.0

        with patch(_REREAD, side_effect=AXTreeEmptyError("no window")):
            run = await _interact(session, ref_id, AxInvokeResult.delivered("ok"))

        run.native.assert_not_called()
        line = _the_line(caplog)
        assert (line["outcome"], line["revalidated"]) == ("refused", "True")

    async def test_a_recent_snapshot_needs_no_reread(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session, ref_id = _session_holding(backend)

        with patch(_REREAD) as reread:
            await _interact(session, ref_id, AxInvokeResult.delivered("ok"))

        reread.assert_not_called()
        assert _the_line(caplog)["revalidated"] == "False"


class TestACallThatDoesNotReturn:
    @pytest.mark.parametrize("error", [RuntimeError("boom"), asyncio.CancelledError()], ids=["error", "cancelled"])
    async def test_it_is_aborted_when_it_ends_before_a_verdict(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture, error: BaseException
    ) -> None:
        session, ref_id = _session_holding(backend)

        with (
            patch.object(session, "_ensure_not_user_takeover", AsyncMock(side_effect=error)),
            pytest.raises(type(error)),
        ):
            await session.desktop_interact(ref=ref_id, action="click")

        assert _the_line(caplog)["outcome"] == "aborted"

    async def test_it_stays_delivered_when_only_the_follow_up_fails(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session, ref_id = _session_holding(backend)

        with (
            patch(_INVOKE, return_value=AxInvokeResult.delivered("ok")),
            patch.object(session, "desktop_snapshot", AsyncMock(side_effect=RuntimeError("follow-up failed"))),
            pytest.raises(RuntimeError),
        ):
            await session.desktop_interact(ref=ref_id, action="click")

        assert _the_line(caplog)["outcome"] == "delivered"


class TestNothingTheScreenOrTheModelSaid:
    async def test_a_line_carries_no_element_text_application_or_window(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session, ref_id = _session_holding(backend)

        await _interact(session, ref_id, AxInvokeResult.delivered("typed"), action="fill", text=_TEXT)

        logged = _logged_text(caplog)
        assert logged
        for private in (_ELEMENT, _TEXT, _APP, _TITLE):
            assert private not in logged

    async def test_a_filled_credential_leaves_neither_its_label_nor_its_value(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session, ref_id = _session_holding(backend)

        with patch(_VAULT) as vault:
            vault.return_value.get_password.return_value = "s3cret-value"
            await _interact(
                session, ref_id, AxInvokeResult.delivered("ok"), action="fill_credential", text="bank-login-label"
            )

        logged = _logged_text(caplog)
        assert _the_line(caplog)["verb"] == "fill_credential"
        assert "s3cret-value" not in logged
        assert "bank-login-label" not in logged

    def test_a_verb_outside_the_vocabulary_is_logged_as_other(self, caplog: pytest.LogCaptureFixture) -> None:
        with InteractTrace("click\n[DESKTOP] forged line"):
            pass

        assert _the_line(caplog)["verb"] == "other"


class TestARefusedVisionScreenshot:
    async def test_a_locked_screen_is_counted(self, backend: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        backend.is_screen_locked.return_value = True
        session = DesktopSession(backend=backend, config=ComputerUseConfig())

        await session.desktop_vision_capture()

        assert _the_line(caplog) == {"event": "vision_capture", "outcome": "refused", "reason": "screen"}

    async def test_a_sensitive_application_is_counted_without_naming_it(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session = DesktopSession(backend=backend, config=ComputerUseConfig())
        identity = {"app_name": "1Password", "window_title": "", "app_id": ""}

        with patch(f"{_PACKAGE}.vision.inspect_backend", return_value=identity):
            await session.desktop_vision_capture()

        assert _the_line(caplog) == {"event": "vision_capture", "outcome": "refused", "reason": "sensitive_app"}
        assert "1Password" not in _logged_text(caplog)

    async def test_a_screenshot_that_is_taken_is_not_counted(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        session = DesktopSession(backend=backend, config=ComputerUseConfig())
        identity = {"app_name": "Notes", "window_title": "", "app_id": ""}

        with (
            patch(f"{_PACKAGE}.vision.inspect_backend", return_value=identity),
            patch.object(session, "_capture_response", AsyncMock(return_value="shot")),
        ):
            assert await session.desktop_vision_capture() == "shot"

        assert _lines(caplog) == []

    @pytest.mark.parametrize(("front", "counted"), [("1Password", True), ("Notes", False)])
    def test_a_frame_is_counted_only_when_it_is_withheld_and_without_naming_the_application(
        self, backend: MagicMock, caplog: pytest.LogCaptureFixture, front: str, counted: bool
    ) -> None:
        backend.screen_context.return_value = ScreenContext(active_window=front, mouse_x=0, mouse_y=0)
        session = DesktopSession(backend=backend, config=ComputerUseConfig())
        frame = ActionResult(success=True, screenshot_base64="img", screenshot_size=(1, 1))

        session._build_multimodal_response(frame, "Done.")

        assert "1Password" not in _logged_text(caplog)
        expected = [{"event": "vision_capture", "outcome": "refused", "reason": "sensitive_frame"}]
        assert _lines(caplog) == (expected if counted else [])
