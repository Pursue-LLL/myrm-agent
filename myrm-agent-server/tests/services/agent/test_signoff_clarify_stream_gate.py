"""Unit tests for H2e signoff clarify stream gate."""

from __future__ import annotations

import pytest

from app.ai_agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.signoff_clarify_stream_gate import (
    apply_signoff_clarify_stream_gate,
)


def _params(*, signoff: bool = False) -> GeneralAgentParams:
    return GeneralAgentParams(
        query="test",
        model_cfg=ModelConfig(model="test/model", api_key="k"),
        chat_id="chat-1",
        message_id="msg-1",
        signoff_clarify_contract=signoff,
    )


def test_stream_gate_noop_without_contract_or_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYRM_E2E_SIGNOFF_CLARIFY_POOL", raising=False)
    params = _params(signoff=False)
    ctx = apply_signoff_clarify_stream_gate(params, {"execution_mode": "pooled"})
    assert ctx == {"execution_mode": "pooled"}
    assert params.signoff_clarify_contract is False


def test_stream_gate_activates_from_request_flag() -> None:
    params = _params(signoff=True)
    ctx = apply_signoff_clarify_stream_gate(params, None)
    assert ctx["signoff_clarify_contract"] is True
    assert params.signoff_clarify_contract is True
    assert params.enable_structured_clarify is True


def test_stream_gate_activates_from_pool_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "1")
    params = _params(signoff=False)
    ctx = apply_signoff_clarify_stream_gate(params, None)
    assert ctx["signoff_clarify_contract"] is True
    assert params.signoff_clarify_contract is True
    assert params.enable_structured_clarify is True
