from app.ai_agents.general_agent.llm_factory import _inject_low_reasoning_effort
from app.core.types import ModelConfig


def test_inject_low_reasoning_effort_merges_without_overwriting_existing() -> None:
    cfg = ModelConfig(
        model="openai/gpt-4o-mini",
        api_key="key",
        model_kwargs={"temperature": 0.2},
    )
    updated = _inject_low_reasoning_effort(cfg)
    assert updated.model_kwargs == {"temperature": 0.2, "reasoning_effort": "low"}
    assert updated is not cfg


def test_inject_low_reasoning_effort_is_idempotent() -> None:
    cfg = ModelConfig(
        model="openai/gpt-4o-mini",
        api_key="key",
        model_kwargs={"reasoning_effort": "low"},
    )
    assert _inject_low_reasoning_effort(cfg) is cfg
