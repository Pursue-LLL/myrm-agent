"""Unit tests for signoff pool LLM selection short-circuit."""

from __future__ import annotations

import pytest

from app.ai_agents.general_agent.llm_factory import select_tool_capable_model_cfg
from app.core.types import ModelConfig


def test_select_tool_capable_skips_scan_on_signoff_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "1")
    cfg = ModelConfig(model="openai-like/agnes-2.0-flash", api_key="k")
    selected, source = select_tool_capable_model_cfg(cfg, providers_dict={"providers": []})
    assert selected.model == cfg.model
    assert source == "main"
