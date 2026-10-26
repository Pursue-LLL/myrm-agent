"""ComputerSession consults the process-wide user control: a held control stops every desktop action."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.computer_use.session import ComputerSession
from myrm_agent_harness.toolkits.computer_use.types import ActionResult, ScreenInfo
from myrm_agent_harness.utils.runtime import cancellation
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, OperationCancelledError, set_cancel_token
from myrm_agent_harness.utils.runtime.user_control import UserControl, UserControlTimeoutError


@pytest.fixture
def mock_backend() -> MagicMock:
    backend = MagicMock()
    backend.screen_info.return_value = ScreenInfo(
        width=1920,
        height=1080,
        dpi_scale=1.0,
    )
    backend.screenshot = AsyncMock(return_value=b"")
    backend.click = AsyncMock(return_value=ActionResult(success=True))
    backend.type_text = AsyncMock(return_value=ActionResult(success=True))
    backend.key = AsyncMock(return_value=ActionResult(success=True))
    backend.mouse_move = AsyncMock(return_value=ActionResult(success=True))
    backend.scroll = AsyncMock(return_value=ActionResult(success=True))
    backend.drag = AsyncMock(return_value=ActionResult(success=True))
    return backend


@pytest.fixture
def session(mock_backend: MagicMock) -> ComputerSession:
    session = ComputerSession(backend=mock_backend)
    session.user_control = UserControl()
    session.take_screenshot = AsyncMock(  # type: ignore[method-assign]
        return_value=MagicMock(screenshot_base64="", screenshot_size=(1, 1))
    )
    return session


class TestComputerSessionUserControl:
    @pytest.mark.asyncio
    async def test_nothing_waits_while_nobody_holds_control(self, session: ComputerSession) -> None:
        await session._ensure_not_user_takeover(timeout=0.05)

    @pytest.mark.asyncio
    async def test_holding_past_the_timeout_refuses_and_stays_locked(self, session: ComputerSession) -> None:
        session.user_control.acquire()

        with pytest.raises(UserControlTimeoutError, match="action was not run"):
            await session._ensure_not_user_takeover(timeout=0.05)

        assert session.user_control.held is True

    @pytest.mark.asyncio
    async def test_a_mutation_waits_for_the_person_and_runs_once_control_returns(
        self, session: ComputerSession, mock_backend: MagicMock
    ) -> None:
        session.user_control.acquire()
        typing = asyncio.create_task(session.type_text("stray input"))

        await asyncio.sleep(0.05)
        assert not typing.done()
        mock_backend.type_text.assert_not_called()

        session.user_control.release()
        await asyncio.wait_for(typing, timeout=2.0)

        mock_backend.type_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stopping_the_run_ends_a_mutation_that_waits_for_the_person(
        self, session: ComputerSession, mock_backend: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cancellation, "_POLL_INTERVAL_S", 0.02)
        monkeypatch.setattr(cancellation, "_ABORT_GRACE_S", 0.2)
        session.user_control.acquire()
        token = CancellationToken("req")
        set_cancel_token(token)
        try:
            asyncio.get_running_loop().call_later(0.05, token.cancel)
            with pytest.raises(OperationCancelledError):
                await asyncio.wait_for(session.type_text("stray input"), timeout=3.0)
        finally:
            set_cancel_token(None)

        mock_backend.type_text.assert_not_called()
        assert session.user_control.held is True
