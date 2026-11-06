"""Per-domain approval belongs to browser navigation: a fetch neither grants a domain nor is let through by one.

Approving a navigation can grant its domain for the session, and a later navigation to it then runs without a card.
A fetch is not asked about its domain, so its card offers no domain and a domain granted to the browser never lets
a fetch run without the approval its own rules ask for. A granted domain is the host a browser dials: a URL that only
names it behind a backslash has no canonical host, is denied before any card is built and so is never let through by
the grant.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, ToolCall

from myrm_agent_harness.agent.middlewares.approval._batch_decisions import apply_approval_decisions
from myrm_agent_harness.agent.middlewares.approval._batch_review import (
    _get_runtime_domains,
    register_security_reviewer,
    reset_runtime_domains,
)
from myrm_agent_harness.agent.middlewares.approval._interrupt_payload import build_interrupt_payload
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.security.types import PermissionAction, PermissionRule, SecurityConfig

_SHELL_FIELDS_PATH = (
    "myrm_agent_harness.toolkits.code_execution.security.command_explainer.extract.build_shell_approval_fields"
)

_NAVIGATE = ToolCall(type="tool_call", name="browser_navigate_tool", args={"url": "https://example.com/a"}, id="nav")
_SPOOFED = ToolCall(
    type="tool_call", name="browser_navigate_tool", args={"url": "https://other.test\\@example.com/a"}, id="spoofed"
)
_FETCH = ToolCall(type="tool_call", name="web_fetch_tool", args={"urls": ["https://example.com/a"]}, id="fetch")
_ALLOW_DOMAIN = [{"type": "approve", "extensions": {"allowDomain": True}}]
_FETCH_ASKS = SecurityConfig(ruleset=(PermissionRule("net_fetch", "*", PermissionAction.ASK),))


@pytest.fixture(autouse=True)
def _isolation() -> Iterator[None]:
    """Reset the process-wide approval state that decides what a batch asks."""
    import myrm_agent_harness.agent.security.approval_flow as approval_flow
    from myrm_agent_harness.agent.middlewares.approval import get_approval_rate_limiter, reset_denial_counter
    from myrm_agent_harness.agent.security.guards.taint_tracker import reset_taint_tracker

    def reset() -> None:
        approval_flow._allowlist = approval_flow.Allowlist()
        reset_taint_tracker()
        reset_denial_counter()
        get_approval_rate_limiter().reset(None)
        register_security_reviewer(None)
        reset_runtime_domains()

    reset()
    yield
    reset()


async def _approve_with_domain(call: ToolCall, permission: str) -> None:
    await apply_approval_decisions(
        _ALLOW_DOMAIN,
        AIMessage(content="", tool_calls=[call]),
        [],
        [(0, call, permission, "needs approval", None)],
        [0],
        {},
        SecurityConfig(domain_hitl_enabled=True),
    )


class TestGrantingADomain:
    async def test_approving_a_navigation_grants_its_domain_for_the_session(self) -> None:
        await _approve_with_domain(_NAVIGATE, "browser_navigate")

        assert _get_runtime_domains() == {"example.com"}

    async def test_approving_a_fetch_grants_no_domain(self) -> None:
        await _approve_with_domain(_FETCH, "net_fetch")

        assert _get_runtime_domains() == set()


class TestGrantedDomainInABatch:
    async def test_a_granted_domain_lets_a_navigation_through_without_a_card(self) -> None:
        _get_runtime_domains().add("example.com")

        approved, _denied, pending = await evaluate_tool_batch(
            [_NAVIGATE], SecurityConfig(domain_hitl_enabled=True), False, "/tmp", "session", {}
        )

        assert [call["id"] for _, call in approved] == ["nav"]
        assert pending == []

    async def test_a_backslash_url_naming_a_granted_domain_is_denied_and_never_asked_about(self) -> None:
        _get_runtime_domains().add("example.com")

        approved, denied, pending = await evaluate_tool_batch(
            [_SPOOFED], SecurityConfig(domain_hitl_enabled=True), False, "/tmp", "session", {}
        )

        assert approved == []
        assert pending == []
        assert [(call["id"], "parser-confusing" in reason) for _, call, reason in denied] == [("spoofed", True)]

    async def test_a_granted_domain_does_not_let_a_fetch_through(self) -> None:
        _get_runtime_domains().add("example.com")

        approved, _denied, pending = await evaluate_tool_batch([_FETCH], _FETCH_ASKS, False, "/tmp", "session", {})

        assert approved == []
        assert [entry[1]["id"] for entry in pending] == ["fetch"]


class TestApprovalCard:
    def test_a_navigation_card_offers_its_domain_and_carries_the_ptc_fields(self) -> None:
        extra_ctx = {"ptc_tool_name_full": "custom_navigate", "ptc_annotations": ["a1"]}

        with patch(_SHELL_FIELDS_PATH, return_value={"shellPreview": None}):
            payload, indices = build_interrupt_payload(
                [(0, _NAVIGATE, "browser_navigate", "Domain check", extra_ctx)], "session-1"
            )

        request = payload["actionRequests"][0]
        assert indices == [0]
        assert request["action"] == "custom_navigate"
        assert request["ptc_annotations"] == ["a1"]
        assert request["domains"] == ("example.com",)
        assert payload["reviewConfigs"][0]["domainApproval"] is True

    def test_a_card_offers_the_host_in_the_spelling_a_browser_dials(self) -> None:
        spelled = ToolCall(
            type="tool_call", name="browser_navigate_tool", args={"url": "HTTPS://Example.COM./a"}, id="spelled"
        )

        with patch(_SHELL_FIELDS_PATH, return_value={"shellPreview": None}):
            payload, _ = build_interrupt_payload([(0, spelled, "browser_navigate", "Domain check", None)], "session-1")

        assert payload["actionRequests"][0]["domains"] == ("example.com",)

    def test_a_fetch_card_offers_no_domain(self) -> None:
        with patch(_SHELL_FIELDS_PATH, return_value={}):
            payload, _ = build_interrupt_payload([(0, _FETCH, "net_fetch", "needs approval", None)], "session-1")

        assert "domains" not in payload["actionRequests"][0]
        assert "domainApproval" not in payload["reviewConfigs"][0]
