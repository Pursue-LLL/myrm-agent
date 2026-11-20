"""Tests BrowserSessionPageMixin.evaluate wiring for enforce_js_eval_guard."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist
from myrm_agent_harness.toolkits.browser.domain_filter.agent_world import agent_world_expression
from myrm_agent_harness.toolkits.browser.domain_filter.context_lists import DomainListPolicy, bind_domain_lists
from myrm_agent_harness.toolkits.browser.session.browser_session_page_mixin import (
    BrowserSessionPageMixin,
)


class _EvalSession(BrowserSessionPageMixin):
    async def _ensure_components(self) -> None:
        return None


@pytest.mark.asyncio
async def test_evaluate_returns_guard_block_without_page_evaluate() -> None:
    session = _EvalSession()
    session._tab_controller = MagicMock()

    with patch(
        "myrm_agent_harness.toolkits.browser.tools.semantic_dom_hitl.enforce_js_eval_guard",
        new=AsyncMock(return_value="[BLOCKED] rejected"),
    ) as guard_mock:
        result = await session.evaluate("document.forms[0].submit()")

    assert result == "[BLOCKED] rejected"
    guard_mock.assert_awaited_once_with(
        session=session,
        tool_name="browser_manage_tool",
        expression="document.forms[0].submit()",
    )
    session._tab_controller.get_active_page.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_runs_page_evaluate_when_guard_passes() -> None:
    session = _EvalSession()
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=42)
    session._tab_controller = MagicMock()
    session._tab_controller.get_active_page.return_value = page

    with patch(
        "myrm_agent_harness.toolkits.browser.tools.semantic_dom_hitl.enforce_js_eval_guard",
        new=AsyncMock(return_value=None),
    ):
        result = await session.evaluate("document.title")

    assert result == "42"
    page.evaluate.assert_awaited_once_with("document.title")


@pytest.mark.asyncio
async def test_evaluate_runs_the_expression_behind_the_contexts_allowlist_after_the_guard_saw_the_original() -> None:
    session = _EvalSession()
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=42)
    bind_domain_lists(page.context, DomainListPolicy(DomainAllowlist.from_strings(("example.com",))))
    session._tab_controller = MagicMock()
    session._tab_controller.get_active_page.return_value = page

    with patch(
        "myrm_agent_harness.toolkits.browser.tools.semantic_dom_hitl.enforce_js_eval_guard",
        new=AsyncMock(return_value=None),
    ) as guard_mock:
        result = await session.evaluate("document.title")

    assert result == "42"
    assert guard_mock.await_args.kwargs["expression"] == "document.title"
    ((handed_to_page,), _) = page.evaluate.await_args
    assert handed_to_page == agent_world_expression(page.context, "document.title")
    assert handed_to_page != "document.title"
