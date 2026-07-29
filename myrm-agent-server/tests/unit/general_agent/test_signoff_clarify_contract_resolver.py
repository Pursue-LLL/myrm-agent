"""Unit tests for signoff clarify contract resolver in converter."""

from __future__ import annotations

import pytest

from app.services.agent.params.converter import _resolve_signoff_clarify_contract
from app.services.agent.params.models import AgentRequest


def test_resolve_signoff_clarify_contract_from_camel_case_engine_params() -> None:
    request = AgentRequest(
        message_id="m1",
        chat_id="c1",
        query="hi",
        engine_params={"signoffClarifyContract": True},
    )
    assert _resolve_signoff_clarify_contract(request) is True


def test_resolve_signoff_clarify_contract_from_snake_case_engine_params() -> None:
    request = AgentRequest(
        message_id="m1",
        chat_id="c1",
        query="hi",
        engine_params={"signoff_clarify_contract": True},
    )
    assert _resolve_signoff_clarify_contract(request) is True


def test_resolve_signoff_clarify_contract_from_pool_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "1")
    request = AgentRequest(message_id="m1", chat_id="c1", query="hi")
    assert _resolve_signoff_clarify_contract(request) is True


def test_resolve_signoff_clarify_contract_false_without_flag_or_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYRM_E2E_SIGNOFF_CLARIFY_POOL", raising=False)
    request = AgentRequest(message_id="m1", chat_id="c1", query="hi")
    assert _resolve_signoff_clarify_contract(request) is False
