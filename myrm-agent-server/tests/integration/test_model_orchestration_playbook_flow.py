"""Integration test for Model Orchestration Playbook, Dynamic Routing & Real LLM Task Flow Loop."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model
from myrm_agent_harness.toolkits.llms.routing.complexity_router import (
    DEFAULT_REASONING_KEYWORDS,
    DEFAULT_SIMPLE_INDICATORS,
    DEFAULT_STANDARD_KEYWORDS,
    RoutingTier,
    _rule_based_classify,
)

from app.services.agent.moa_preset_resolver import (
    MOA_PRESET_DEFAULT_ID,
    MOA_PRESET_REVIEW_ID,
    VALID_MOA_PRESET_IDS,
    apply_moa_preset_activation,
)

# Load test secrets from .env.test
test_env_path = Path(__file__).resolve().parents[2] / ".env.test"
if test_env_path.exists():
    load_dotenv(test_env_path)


@pytest.mark.integration
def test_complexity_router_tier_classification() -> None:
    """Verify 3-Tier Dynamic Routing classification across Simple, Standard, and Reasoning tiers."""
    # Simple tier: greeting (e.g. "hello")
    tier_simple = _rule_based_classify(
        "hello",
        has_image=False,
        standard_keywords=DEFAULT_STANDARD_KEYWORDS,
        reasoning_keywords=DEFAULT_REASONING_KEYWORDS,
        simple_indicators=DEFAULT_SIMPLE_INDICATORS,
    )
    assert tier_simple == RoutingTier.SIMPLE

    # Standard tier: multi-step coding / debug
    tier_std = _rule_based_classify(
        "debug this authentication error in database module",
        has_image=False,
        standard_keywords=DEFAULT_STANDARD_KEYWORDS,
        reasoning_keywords=DEFAULT_REASONING_KEYWORDS,
        simple_indicators=DEFAULT_SIMPLE_INDICATORS,
    )
    assert tier_std == RoutingTier.STANDARD

    # Reasoning tier: formal math proof / complex architectural system design
    tier_reasoning = _rule_based_classify(
        "prove the theorem and derive the equation step by step",
        has_image=False,
        standard_keywords=DEFAULT_STANDARD_KEYWORDS,
        reasoning_keywords=DEFAULT_REASONING_KEYWORDS,
        simple_indicators=DEFAULT_SIMPLE_INDICATORS,
    )
    assert tier_reasoning == RoutingTier.REASONING


@pytest.mark.integration
def test_moa_preset_resolver_configuration() -> None:
    """Verify MoA consensus preset resolution (default vs review)."""
    assert MOA_PRESET_DEFAULT_ID in VALID_MOA_PRESET_IDS
    assert MOA_PRESET_REVIEW_ID in VALID_MOA_PRESET_IDS

    engine_params = {
        "moa_overlay": {
            "enabled": True,
            "reference_model_selections": [
                {"providerId": "minimax", "model": "MiniMax-M3"}
            ],
        }
    }

    # Activate review preset
    activated = apply_moa_preset_activation(engine_params, MOA_PRESET_REVIEW_ID)
    assert activated is not None
    overlay = activated.get("moa_overlay")
    assert isinstance(overlay, dict)
    assert overlay.get("enabled") is True
    assert overlay.get("reference_reasoning_effort") == "high"


@pytest.mark.integration
def test_real_llm_orchestration_task_flow() -> None:
    """Execute real LLM Task Flow with real credentials from .env.test."""
    real_api_key = os.getenv("BASIC_API_KEY")
    real_base_url = os.getenv("BASIC_BASE_URL")
    real_model_name = os.getenv("BASIC_MODEL")
    if not (real_api_key and real_base_url and real_model_name):
        pytest.skip("No real LLM credentials configured in environment/.env.test")

    real_llm = create_litellm_model(
        real_model_name,
        api_key=real_api_key,
        base_url=real_base_url,
    )

    task_prompt = "你是系统架构师，请用极简的一句话概括'大脑负责规划、双手负责工具调用'的优势。"
    response = real_llm.invoke(task_prompt)
    assert response is not None
    assert hasattr(response, "content")
    assert len(response.content) > 5
