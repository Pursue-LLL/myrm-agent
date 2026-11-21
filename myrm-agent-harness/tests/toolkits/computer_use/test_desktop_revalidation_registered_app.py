"""Tests for the re-read of desktop_interact after an approval delay: the application the element belongs to is read
again, the ids the model holds keep naming the same elements, and gates and delivery act on that one capture."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.dref.errors import AXTreeEmptyError, DRefStaleError
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta, SnapshotScope
from myrm_agent_harness.toolkits.computer_use.types import ComputerUseConfig, ScreenInfo

_PACKAGE = "myrm_agent_harness.toolkits.computer_use.desktop_session"
_SNAPSHOT_CAPTURE = f"{_PACKAGE}.snapshot.capture_snapshot"
_REVALIDATION_CAPTURE = f"{_PACKAGE}.guards.capture_snapshot"
_INVOKE = f"{_PACKAGE}.interact.invoke_element"


def _capture(
    *names: str,
    app: str = "Mail",
    pid: int = 100,
    scope: SnapshotScope = "foreground",
    window_title: str = "Inbox",
    app_id: str = "",
    top: int = 0,
) -> tuple[SnapshotMeta, dict[str, ElementRef]]:
    """A raw capture as a platform script returns it: buttons laid out top to bottom starting at `top`.

    Ids and locators are positions inside the capture.
    """
    meta = SnapshotMeta(
        ref_count=len(names), app_name=app, window_title=window_title, scope=scope, app_id=app_id, pid=pid
    )
    refs = {
        f"d{i}": ElementRef(
            ref_id=f"d{i}",
            role="AXButton",
            name=name,
            bbox=BBox(0, top + 40 * i, 100, 30),
            backend_key=f"position-{i}",
        )
        for i, name in enumerate(names)
    }
    return meta, refs


def _registered_ids(session: DesktopSession) -> list[str]:
    """The ids the model holds, in capture order."""
    return list(session.ref_registry.all_refs())


@pytest.fixture
def session() -> DesktopSession:
    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
    return DesktopSession(backend=backend, config=ComputerUseConfig(screenshot_delay=0.0))


async def _look(session: DesktopSession, capture: tuple[SnapshotMeta, dict[str, ElementRef]]) -> None:
    """The model takes a snapshot, then needs longer than the revalidation threshold to answer."""
    with patch(_SNAPSHOT_CAPTURE, return_value=capture):
        await session.desktop_snapshot()
    session._last_snapshot_time = time.time() - 10.0


async def _click_after_the_delay(
    session: DesktopSession, ref: str, rereads: tuple[SnapshotMeta, dict[str, ElementRef]]
) -> tuple[str, MagicMock]:
    """Click `ref` while the screen is read again as `rereads`; returns the tool result and the delivery mock."""
    with (
        patch(_REVALIDATION_CAPTURE, return_value=rereads),
        patch(_INVOKE) as invoke,
        patch.object(session, "desktop_snapshot", AsyncMock(return_value="follow-up")),
    ):
        invoke.return_value.success = True
        result = await session.desktop_interact(ref=ref, action="click")
    return str(result), invoke


class TestWhichApplicationIsReRead:
    async def test_a_background_application_is_read_again_by_name_not_the_foreground(
        self, session: DesktopSession
    ) -> None:
        await _look(session, _capture("Reply", "Forward", app="Notes", scope="target"))
        forward_id = _registered_ids(session)[1]
        rereads = _capture("Banner", "Reply", "Forward", app="Notes", scope="target")

        with (
            patch(_REVALIDATION_CAPTURE, return_value=rereads) as capture,
            patch(_INVOKE) as invoke,
            patch.object(session, "desktop_snapshot", AsyncMock(return_value="follow-up")) as follow_up,
        ):
            invoke.return_value.success = True
            result = await session.desktop_interact(ref=forward_id, action="click")

        capture.assert_called_once_with(session._backend, "target", "Notes")
        acted_on = invoke.call_args.args[1]
        assert (acted_on.name, acted_on.backend_key) == ("Forward", "position-2")
        assert invoke.call_args.kwargs["app_name"] == "Notes"
        assert f"Action 'click' on @{forward_id} succeeded." in str(result)
        follow_up.assert_awaited_once_with(scope="target", app_name="Notes", include_screenshot=False)

    async def test_a_capture_of_another_application_is_dropped_and_the_registry_is_left_alone(
        self, session: DesktopSession
    ) -> None:
        await _look(session, _capture("Reply", app="Mail"))
        reply_id = _registered_ids(session)[0]
        generation = session.ref_registry.generation

        result, invoke = await _click_after_the_delay(session, reply_id, _capture("Reply", app="Safari"))

        assert "is no longer found" in result
        invoke.assert_not_called()
        assert session.ref_registry.generation == generation
        assert session.ref_registry.meta is not None
        assert session.ref_registry.meta.app_name == "Mail"
        assert session.ref_registry.resolve(reply_id).element.name == "Reply"

    async def test_a_restarted_application_is_not_the_application_the_element_was_read_from(
        self, session: DesktopSession
    ) -> None:
        await _look(session, _capture("Reply", pid=100))
        reply_id = _registered_ids(session)[0]

        result, invoke = await _click_after_the_delay(session, reply_id, _capture("Reply", pid=555))

        assert "is no longer found" in result
        invoke.assert_not_called()
        assert session.ref_registry.resolve(reply_id).meta.pid == 100

    async def test_the_reference_may_carry_the_at_sign(self, session: DesktopSession) -> None:
        await _look(session, _capture("Reply"))

        result, invoke = await _click_after_the_delay(session, "@d0", _capture("Reply"))

        assert "Re-validation failed" not in result
        invoke.assert_called_once()

    async def test_an_application_without_a_readable_window_refuses_the_action(self, session: DesktopSession) -> None:
        await _look(session, _capture("Reply"))

        with (
            patch(_REVALIDATION_CAPTURE, side_effect=AXTreeEmptyError("target window not found")),
            patch(_INVOKE) as invoke,
        ):
            result = await session.desktop_interact(ref="d0", action="click")

        assert "is no longer found" in str(result)
        invoke.assert_not_called()
        assert session.ref_registry.resolve("d0").element.name == "Reply"

    async def test_an_error_of_the_re_read_refuses_the_action(self, session: DesktopSession) -> None:
        await _look(session, _capture("Reply"))

        with patch(_REVALIDATION_CAPTURE, side_effect=RuntimeError("no window")), patch(_INVOKE) as invoke:
            result = await session.desktop_interact(ref="d0", action="click")

        assert "Could not re-verify screen state (no window)" in str(result)
        invoke.assert_not_called()


class TestTheElementIsFollowedAcrossTheDelay:
    async def test_a_layout_shift_still_acts_on_the_approved_element_with_its_new_locator(
        self, session: DesktopSession
    ) -> None:
        await _look(session, _capture("Reply", "Forward"))
        forward_id = _registered_ids(session)[1]

        result, invoke = await _click_after_the_delay(session, forward_id, _capture("Banner", "Reply", "Forward"))

        acted_on = invoke.call_args.args[1]
        assert (acted_on.name, acted_on.backend_key) == ("Forward", "position-2")
        assert f"Action 'click' on @{forward_id} succeeded." in result

    @pytest.mark.parametrize(
        ("names", "index", "name"),
        [
            (("Reply", "", "", "OK", "OK"), 0, "Reply"),
            (("Reply", "", "", "OK", "OK"), 2, ""),
            (("Reply", "", "", "OK", "OK"), 4, "OK"),
        ],
        ids=["named", "unnamed", "twin"],
    )
    async def test_an_unchanged_screen_keeps_every_element_addressable(
        self, session: DesktopSession, names: tuple[str, ...], index: int, name: str
    ) -> None:
        await _look(session, _capture(*names))
        remembered = _registered_ids(session)[index]

        result, invoke = await _click_after_the_delay(session, remembered, _capture(*names))

        assert f"Action 'click' on @{remembered} succeeded." in result
        acted_on = invoke.call_args.args[1]
        assert (acted_on.ref_id, acted_on.name, acted_on.backend_key) == (remembered, name, f"position-{index}")

    async def test_a_layout_shift_retires_an_unnamed_element_while_a_named_one_continues(
        self, session: DesktopSession
    ) -> None:
        await _look(session, _capture("Reply", "", ""))
        reply_id, _, second_icon = _registered_ids(session)

        result, invoke = await _click_after_the_delay(session, second_icon, _capture("Reply", "", "", top=15))

        assert "is no longer found" in result
        invoke.assert_not_called()
        with pytest.raises(DRefStaleError):
            session.ref_registry.resolve(second_icon)
        assert session.ref_registry.resolve(reply_id).element.backend_key == "position-0"

    async def test_a_renamed_element_is_not_acted_on(self, session: DesktopSession) -> None:
        await _look(session, _capture("Inbox (3)", "Reply"))
        inbox_id = _registered_ids(session)[0]

        result, invoke = await _click_after_the_delay(session, inbox_id, _capture("Inbox (4)", "Reply"))

        assert "is no longer found" in result
        invoke.assert_not_called()


class TestTheNextSnapshotTellsWhatChangedWhileTheModelWasAway:
    _ROWS = ("Reply", "Delete", "Archive", "Move", "Flag")

    async def test_after_a_refusal_the_snapshot_reports_the_element_that_went_away(
        self, session: DesktopSession
    ) -> None:
        await _look(session, _capture(*self._ROWS))
        delete_id = _registered_ids(session)[1]
        without_delete = _capture("Reply", "Archive", "Move", "Flag")

        result, _ = await _click_after_the_delay(session, delete_id, without_delete)
        with patch(_SNAPSHOT_CAPTURE, return_value=without_delete):
            snapshot = await session.desktop_snapshot()

        assert "is no longer found" in result
        assert "Desktop diff (1 change vs previous snapshot, app: Mail)" in str(snapshot)
        assert f"- @{delete_id} (removed, no longer valid)" in str(snapshot)

    async def test_after_an_action_the_snapshot_also_reports_what_appeared_before_it(
        self, session: DesktopSession
    ) -> None:
        await _look(session, _capture(*self._ROWS))
        reply_id = _registered_ids(session)[0]
        with_banner = _capture(*self._ROWS, "Banner")

        with (
            patch(_REVALIDATION_CAPTURE, return_value=with_banner),
            patch(_SNAPSHOT_CAPTURE, return_value=with_banner),
            patch(_INVOKE) as invoke,
        ):
            invoke.return_value.success = True
            result = await session.desktop_interact(ref=reply_id, action="click")

        assert f"Action 'click' on @{reply_id} succeeded." in str(result)
        assert '+ @d5 AXButton "Banner"' in str(result)


class TestGatesAndDeliveryShareOneCapture:
    async def test_the_gates_see_the_page_the_element_is_on_after_the_re_read(self, session: DesktopSession) -> None:
        mirror = {"app": "iPhone Mirroring", "app_id": "com.apple.ScreenContinuity"}
        session._adopt_capture(*_capture("Connect", window_title="iPhone (Pursue's iPhone)", **mirror))
        session._last_snapshot_time = time.time() - 10.0
        connect_id = _registered_ids(session)[0]

        result, invoke = await _click_after_the_delay(
            session, connect_id, _capture("Connect", window_title="Click Connect to Start", **mirror)
        )

        assert result.startswith("Safety:")
        assert "must NOT automatically click connect" in result
        invoke.assert_not_called()

    async def test_the_approval_is_asked_for_the_application_the_model_looked_at(self, session: DesktopSession) -> None:
        await _look(session, _capture("Reply", app="Mail", window_title="Inbox", app_id="com.apple.mail"))
        reply_id = _registered_ids(session)[0]
        session._last_snapshot_time = time.time()

        with (
            patch.object(session, "check_app_approval", AsyncMock(return_value=None)) as approval,
            patch(_INVOKE) as invoke,
            patch.object(session, "desktop_snapshot", AsyncMock(return_value="follow-up")),
        ):
            invoke.return_value.success = True
            await session.desktop_interact(ref=reply_id, action="click")

        approval.assert_awaited_once_with(
            app_name="Mail",
            window_title="Inbox",
            app_id="com.apple.mail",
            operation=f"desktop_interact(click, @{reply_id})",
        )

    async def test_an_element_is_not_acted_on_after_another_application_took_the_registry_during_the_approval(
        self, session: DesktopSession
    ) -> None:
        await _look(session, _capture("Reply", app="Mail"))
        reply_id = _registered_ids(session)[0]
        session._last_snapshot_time = time.time()

        async def another_snapshot_lands(**_: object) -> None:
            session._adopt_capture(*_capture("Reply", app="Safari"))

        with (
            patch.object(session, "check_app_approval", AsyncMock(side_effect=another_snapshot_lands)),
            patch(_INVOKE) as invoke,
        ):
            result = await session.desktop_interact(ref=reply_id, action="click")

        assert "stale" in str(result)
        invoke.assert_not_called()
