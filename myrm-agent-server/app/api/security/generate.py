"""Security Policy NL Generation API.

Provides a single endpoint that accepts natural language security policy
descriptions and returns generated SecurityConfig JSON with validation
and human-readable explanations.

[INPUT]
- myrm_agent_harness.agent.security.policy_generator (build_messages, parse, validate, explain)
- litellm for LLM calls
- User's configured model via config loader

[OUTPUT]
- router: FastAPI APIRouter for POST /security/generate-policy

[POS]
Business-layer bridge between frontend NL input and harness-level policy generation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.agent.security.policy_generator import (
    PolicyParseError,
    build_messages,
    explain_policy,
    parse_policy_response,
    validate_generated_policy,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security-policy-generator"])

if TYPE_CHECKING:
    from app.core.types import ModelConfig


class GeneratePolicyRequest(BaseModel):
    """Request body for NL policy generation."""

    text: str = Field(..., min_length=2, max_length=2000, description="Natural language policy description")
    current_config: dict[str, object] | None = Field(None, description="Current SecurityConfig for context-aware generation")
    model_selection: dict[str, str] | None = Field(None, description="Optional model override: {providerId, model}")


class PolicyWarningResponse(BaseModel):
    """A single validation warning."""

    message: str
    severity: str
    field: str


class GeneratePolicyResponse(BaseModel):
    """Response from NL policy generation."""

    generated_config: dict[str, object]
    explanation_zh: str
    explanation_en: str
    warnings: list[PolicyWarningResponse]
    is_valid: bool


@router.post("/generate-policy", response_model=GeneratePolicyResponse)
async def generate_policy(req: GeneratePolicyRequest) -> GeneratePolicyResponse:
    """Generate security policy from natural language description.

    Calls LLM to convert NL input into structured SecurityConfig,
    then validates and explains the result.
    """
    from litellm import acompletion

    model_cfg = await _resolve_model(req.model_selection)

    messages = build_messages(req.text, req.current_config)

    try:
        llm_kwargs: dict[str, object] = {
            "model": model_cfg.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1500,
            "timeout": 30,
            "api_key": model_cfg.api_key,
        }
        if model_cfg.base_url:
            llm_kwargs["api_base"] = model_cfg.base_url

        response = await acompletion(**llm_kwargs)  # type: ignore[arg-type]
        raw_output = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.error("Policy generation LLM call failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"LLM call failed: {type(exc).__name__}: {exc}",
        ) from exc

    try:
        generated = parse_policy_response(raw_output)
    except PolicyParseError as exc:
        logger.warning("Policy generation parse failed: %s", exc)
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse LLM response: {exc}",
        ) from exc

    is_valid, warnings = validate_generated_policy(generated, req.current_config)
    explanation_zh = explain_policy(generated, locale="zh")
    explanation_en = explain_policy(generated, locale="en")

    return GeneratePolicyResponse(
        generated_config=generated,
        explanation_zh=explanation_zh,
        explanation_en=explanation_en,
        warnings=[PolicyWarningResponse(message=w.message, severity=w.severity, field=w.field) for w in warnings],
        is_valid=is_valid,
    )


async def _resolve_model(selection: dict[str, str] | None) -> "ModelConfig":
    """Resolve LLM model config for policy generation.

    Uses user-provided selection, or falls back to the user's default model.
    Returns full ModelConfig with api_key for litellm auth.
    """
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.model_resolver import _fallback_model_from_providers, _to_litellm_model
    from app.core.types import ModelConfig

    configs = await load_user_configs()

    if selection:
        provider_id = selection.get("providerId", "")
        model_name = selection.get("model", "")
        if provider_id and model_name:
            litellm_model = _to_litellm_model(provider_id, model_name, None)
            fallback = _fallback_model_from_providers(configs.providers_dict)
            return ModelConfig(model=litellm_model, api_key=fallback.api_key, base_url=fallback.base_url)

    try:
        return _fallback_model_from_providers(configs.providers_dict)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No available LLM model: {exc}",
        ) from exc
