"""Integration test for Model Orchestration Playbook, Dynamic Routing & Real LLM Task Flow Loop."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model
from myrm_agent_harness.toolkits.llms.routing.complexity_router import ComplexityRouter, RoutingTier

from app.services.agent.moa_preset_resolver import MOA_PRESET_DEFAULT_ID, MOA_PRESET_REVIEW_ID, resolve_moa_preset_overrides

# Load test secrets from .env.test
test_env_path = Path(__file__).resolve().parents[2] / ".env.test"
if test_env_path.exists():
    load_dotenv(test_env_path)


@pytest.mark.integration
def test_complexity_router_tier_classification() -> None:
    """Verify 3-Tier Dynamic Routing classification across Simple, Standard, and Reasoning tiers."""
    router = ComplexityRouter()

    # Simple tier: greeting / lookup
    tier_simple = router.route("你好，请问今天天气怎么样？")
    assert tier_simple == RoutingTier.SIMPLE

    # Standard tier: multi-step coding / refactoring
    tier_std = router.route("请帮我重构这个 Python 函数并为它编写单元测试，需要包含边界条件。")
    assert tier_std == RoutingTier.STANDARD

    # Reasoning tier: formal math proof / complex architectural system design
    tier_reasoning = router.route("请证明对于任意素数 p > 3，p^2 - 1 必然能被 24 整除，并给出严谨的形式化推导步骤。")
    assert tier_reasoning == RoutingTier.REASONING


@pytest.mark.integration
def test_moa_preset_resolver_configuration() -> None:
    """Verify MoA consensus preset resolution (default vs review)."""
    default_overrides = resolve_moa_preset_overrides(MOA_PRESET_DEFAULT_ID)
    assert default_overrides is not None
    assert "moa_reference_models" in default_overrides or "enable_moa" in default_overrides

    review_overrides = resolve_moa_preset_overrides(MOA_PRESET_REVIEW_ID)
    assert review_overrides is not None


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
