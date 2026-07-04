"""Tests for web fetch escalation binding."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.web_fetch.binding import open_web_fetch_escalation_context, resolve_browser_launch_mode


def test_resolve_browser_launch_mode_extension() -> None:
    from myrm_agent_harness.toolkits.browser.pool.config import LaunchMode

    assert resolve_browser_launch_mode("extension") == LaunchMode.EXTENSION


def test_resolve_browser_launch_mode_invalid() -> None:
    assert resolve_browser_launch_mode("not-a-mode") is None
    assert resolve_browser_launch_mode(None) is None


@pytest.mark.asyncio
async def test_open_web_fetch_escalation_context_binds_contextvar() -> None:
    from myrm_agent_harness.toolkits.browser.pool.config import LaunchMode
    from myrm_agent_harness.toolkits.web_fetch.escalation.context import (
        get_bound_browser_launch_mode,
        get_bound_escalation_providers,
    )
    from myrm_agent_harness.toolkits.web_fetch.escalation.protocols import EscalationFetchResult

    class _Provider:
        provider_id = "stub"

        async def fetch_url(self, url: str, *, max_chars: int = 0) -> EscalationFetchResult:
            return EscalationFetchResult(url=url, content="ok", provider_id="stub")

    with patch(
        "app.services.web_fetch.binding.build_escalation_providers",
        new=AsyncMock(return_value=[_Provider()]),
    ):
        async with open_web_fetch_escalation_context(session_id="s1", browser_source="extension"):
            assert get_bound_escalation_providers() is not None
            assert get_bound_browser_launch_mode() == LaunchMode.EXTENSION

    assert get_bound_escalation_providers() is None
    assert get_bound_browser_launch_mode() is None
