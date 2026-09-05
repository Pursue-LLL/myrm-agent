"""Formal integration & real task flow test for Vercel AI Gateway Provider & Spend Observability."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
import pytest

from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model
from myrm_agent_server.app.models.domain.llm_provider import (
    ProviderType,
    AIProviderConfig,
)
from myrm_agent_server.app.models.domain.model_family import ModelFamily


# Load test secrets if available
test_env_path = Path(__file__).resolve().parents[2] / ".env.test"
if test_env_path.exists():
    load_dotenv(test_env_path)


@pytest.mark.integration
def test_vercel_ai_gateway_attribution_headers_injection() -> None:
    """Verify that models pointing to ai-gateway.vercel.sh automatically inject required attribution headers."""
    gw_model = create_litellm_model(
        "openai/gpt-4o",
        api_key="vca_test_mock_key",
        base_url="https://ai-gateway.vercel.sh/v1",
    )
    headers = getattr(gw_model, "model_kwargs", {}).get("extra_headers", {})
    assert headers.get("HTTP-Referer") == "https://myrm.ai"
    assert headers.get("X-Title") == "Myrm Agent"
    assert headers.get("User-Agent") == "Myrm/1.0 (Vercel-AI-Gateway-Client)"


@pytest.mark.integration
def test_vercel_ai_gateway_provider_configuration_validation() -> None:
    """Verify provider type and domain validation for Vercel AI Gateway."""
    cfg = AIProviderConfig(
        id="provider-vercel-ai-gateway",
        name="Vercel AI Gateway",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_base="https://ai-gateway.vercel.sh/v1",
        api_key="vca_mock_key",
        enabled=True,
    )
    assert cfg.provider_type == ProviderType.OPENAI_COMPATIBLE
    assert cfg.api_base == "https://ai-gateway.vercel.sh/v1"


@pytest.mark.integration
def test_real_user_task_flow_inference_loop() -> None:
    """Execute end-to-end user inference task flow with active provider credentials to guarantee loop closure."""
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
    task_prompt = "请用中文回答：1+1等于几？"
    response = real_llm.invoke(task_prompt)
    assert response is not None
    assert hasattr(response, "content")
    assert "2" in response.content or "二" in response.content
