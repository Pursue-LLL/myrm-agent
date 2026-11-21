"""Layer 3: the CDP audit that observes the requests a page makes and logs the ones outside the allowlist."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist

_CdpEventHandler = Callable[[dict[str, object]], None]

# =============================================================================
# CDP audit (_schedule_cdp_audit, _log_task_exception) - Layer 3
# =============================================================================


def test_schedule_cdp_audit_creates_task() -> None:
    """Test _schedule_cdp_audit schedules a background task that runs install."""
    from unittest.mock import patch

    from myrm_agent_harness.toolkits.browser import domain_filter
    from myrm_agent_harness.toolkits.browser.domain_filter import _schedule_cdp_audit

    page = MagicMock()
    allowlist = DomainAllowlist(patterns=("example.com",))

    install_called = False

    async def fake_install(page: object, allowlist: object) -> None:
        nonlocal install_called
        install_called = True

    loop = asyncio.new_event_loop()
    try:
        with patch.object(
            domain_filter,
            "_install_cdp_audit",
            new=fake_install,
        ):
            with patch("asyncio.get_running_loop", return_value=loop):
                _schedule_cdp_audit(page, allowlist)
            pending = asyncio.all_tasks(loop)
            loop.run_until_complete(asyncio.gather(*pending))
        assert install_called
        assert not domain_filter._cdp_audit_tasks
    finally:
        loop.close()


def test_schedule_cdp_audit_no_running_loop() -> None:
    """Test _schedule_cdp_audit handles no running loop gracefully."""
    from unittest.mock import patch

    from myrm_agent_harness.toolkits.browser.domain_filter import _schedule_cdp_audit

    page = MagicMock()
    allowlist = DomainAllowlist(patterns=("example.com",))

    with patch("asyncio.get_running_loop", side_effect=RuntimeError("No running loop")):
        _schedule_cdp_audit(page, allowlist)


def test_log_task_exception_with_exception() -> None:
    """Test _log_task_exception logs task exceptions."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _log_task_exception

    task = MagicMock()
    task.cancelled = MagicMock(return_value=False)
    task.exception = MagicMock(return_value=RuntimeError("Task failed"))

    _log_task_exception(task)


def test_log_task_exception_cancelled_task() -> None:
    """Test _log_task_exception skips cancelled tasks."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _log_task_exception

    task = MagicMock()
    task.cancelled = MagicMock(return_value=True)

    _log_task_exception(task)

    task.exception.assert_not_called()


def test_log_task_exception_no_exception() -> None:
    """Test _log_task_exception skips tasks without exceptions."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _log_task_exception

    task = MagicMock()
    task.cancelled = MagicMock(return_value=False)
    task.exception = MagicMock(return_value=None)

    _log_task_exception(task)


# =============================================================================
# _install_cdp_audit detailed tests
# =============================================================================


@pytest.mark.asyncio
async def test_install_cdp_audit_enables_network() -> None:
    """Test _install_cdp_audit enables Network domain."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _install_cdp_audit

    page = MagicMock()
    mock_cdp = AsyncMock()
    mock_cdp.send = AsyncMock()
    mock_cdp.on = MagicMock()
    page.context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    allowlist = DomainAllowlist(patterns=("example.com",))

    await _install_cdp_audit(page, allowlist)

    mock_cdp.send.assert_called_with("Network.enable")
    mock_cdp.on.assert_called_once()


@pytest.mark.asyncio
async def test_install_cdp_audit_ws_violation_logging() -> None:
    """Test CDP audit logs WebSocket violations."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _install_cdp_audit

    page = MagicMock()
    mock_cdp = AsyncMock()
    mock_cdp.send = AsyncMock()

    ws_handler: _CdpEventHandler | None = None

    def capture_on(event: str, handler: _CdpEventHandler) -> None:
        nonlocal ws_handler
        if event == "Network.webSocketCreated":
            ws_handler = handler

    mock_cdp.on = capture_on
    page.context.new_cdp_session = AsyncMock(return_value=mock_cdp)

    allowlist = DomainAllowlist(patterns=("example.com",))

    await _install_cdp_audit(page, allowlist)

    assert ws_handler is not None

    ws_handler({"url": "wss://evil.com/socket"})


@pytest.mark.asyncio
async def test_install_cdp_audit_exception_handling() -> None:
    """Test _install_cdp_audit handles exceptions gracefully."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _install_cdp_audit

    page = MagicMock()
    page.context.new_cdp_session = AsyncMock(side_effect=RuntimeError("CDP failed"))

    allowlist = DomainAllowlist(patterns=("example.com",))

    await _install_cdp_audit(page, allowlist)
