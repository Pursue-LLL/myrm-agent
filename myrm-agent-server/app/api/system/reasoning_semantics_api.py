"""
[INPUT]: Raw provider usage payloads, model identifiers, custom cost rates, and invariant verification targets.
[OUTPUT]: NormalizedTokensResponse, InvariantCheckResponse verdicts, and provider policy catalogs.
[POS]: myrm-agent/myrm-agent-server/app/api/system/reasoning_semantics_api.py
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.reasoning_semantics import (
    InvariantCheckResult,
    NormalizedTokenUsageSnapshot,
    ProviderReasoningNormalizer,
    ReasoningInclusionPolicy,
    ReasoningInvariantGuard,
)

router = APIRouter(tags=["reasoning-semantics"])

_normalizer = ProviderReasoningNormalizer()
_guard = ReasoningInvariantGuard()


# --- Pydantic Schemas ---

class RawUsagePayload(BaseModel):
    prompt_tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    thinking_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class NormalizeTokensRequest(BaseModel):
    provider_or_model: str
    raw_usage: RawUsagePayload
    prompt_cost_per_1k: float = Field(default=0.003, ge=0.0)
    completion_cost_per_1k: float = Field(default=0.015, ge=0.0)
    raw_reported_total: Optional[int] = Field(default=None, ge=0)


class NormalizedTokensResponse(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    visible_content_tokens: int
    total_tokens: int
    cost_usd: float
    is_zero_double_counted: bool
    raw_provider: str
    policy_applied: str
    normalized_at: str


class VerifyInvariantRequest(BaseModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    raw_provider: str = "generic-model"
    policy_applied: str = "INCLUDED_IN_COMPLETION"
    raw_reported_total: Optional[int] = Field(default=None, ge=0)


class InvariantCheckResponse(BaseModel):
    is_valid: bool
    violation_type: Optional[str]
    diagnostic_warning: Optional[str]
    corrected_snapshot: Optional[NormalizedTokensResponse]


class ProviderPolicyItemResponse(BaseModel):
    provider_keyword: str
    policy: str
    description: str


# --- Converters ---

def _convert_snapshot(snap: NormalizedTokenUsageSnapshot) -> NormalizedTokensResponse:
    return NormalizedTokensResponse(
        prompt_tokens=snap.prompt_tokens,
        completion_tokens=snap.completion_tokens,
        reasoning_tokens=snap.reasoning_tokens,
        visible_content_tokens=snap.visible_content_tokens,
        total_tokens=snap.total_tokens,
        cost_usd=snap.cost_usd,
        is_zero_double_counted=snap.is_zero_double_counted,
        raw_provider=snap.raw_provider,
        policy_applied=snap.policy_applied.value,
        normalized_at=snap.normalized_at,
    )


# --- HTTP Endpoints ---

@router.post(
    "/reasoning-semantics/normalize",
    response_model=NormalizedTokensResponse,
    summary="按提供方口径归一化 Token 统计，严防推理 Token 二次重复累加与双重计费",
)
def normalize_token_usage(payload: NormalizeTokensRequest) -> NormalizedTokensResponse:
    # Convert pydantic RawUsagePayload to flat dict
    usage_dict: Dict[str, int] = {}
    if payload.raw_usage.prompt_tokens is not None:
        usage_dict["prompt_tokens"] = payload.raw_usage.prompt_tokens
    if payload.raw_usage.input_tokens is not None:
        usage_dict["input_tokens"] = payload.raw_usage.input_tokens
    if payload.raw_usage.completion_tokens is not None:
        usage_dict["completion_tokens"] = payload.raw_usage.completion_tokens
    if payload.raw_usage.output_tokens is not None:
        usage_dict["output_tokens"] = payload.raw_usage.output_tokens
    if payload.raw_usage.reasoning_tokens is not None:
        usage_dict["reasoning_tokens"] = payload.raw_usage.reasoning_tokens
    if payload.raw_usage.thinking_tokens is not None:
        usage_dict["thinking_tokens"] = payload.raw_usage.thinking_tokens
    if payload.raw_usage.total_tokens is not None:
        usage_dict["total_tokens"] = payload.raw_usage.total_tokens

    snapshot = _normalizer.normalize(
        provider_or_model=payload.provider_or_model,
        raw_usage=usage_dict,
        prompt_cost_per_1k=payload.prompt_cost_per_1k,
        completion_cost_per_1k=payload.completion_cost_per_1k,
    )

    # Optional runtime guard check if caller provided explicit reported total
    if payload.raw_reported_total is not None:
        guard_result = _guard.verify_and_guard(
            snapshot,
            raw_reported_total=payload.raw_reported_total,
        )
        if not guard_result.is_valid and guard_result.corrected_snapshot:
            snapshot = guard_result.corrected_snapshot

    return _convert_snapshot(snapshot)


@router.post(
    "/reasoning-semantics/verify-invariant",
    response_model=InvariantCheckResponse,
    summary="校验 Token 快照是否破坏不变量契约 (总量多加 reasoning 或 reasoning 溢出)",
)
def verify_token_invariant(payload: VerifyInvariantRequest) -> InvariantCheckResponse:
    policy_enum = (
        ReasoningInclusionPolicy.STANDALONE_OUTPUT
        if payload.policy_applied == "STANDALONE_OUTPUT"
        else ReasoningInclusionPolicy.INCLUDED_IN_COMPLETION
    )
    now_str = datetime.now(timezone.utc).isoformat()
    snap = NormalizedTokenUsageSnapshot(
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        reasoning_tokens=payload.reasoning_tokens,
        visible_content_tokens=max(0, payload.completion_tokens - payload.reasoning_tokens),
        total_tokens=payload.total_tokens,
        cost_usd=payload.cost_usd,
        is_zero_double_counted=True,
        raw_provider=payload.raw_provider,
        policy_applied=policy_enum,
        normalized_at=now_str,
    )

    result = _guard.verify_and_guard(
        snapshot=snap,
        raw_reported_total=payload.raw_reported_total,
    )

    corrected_dto = (
        _convert_snapshot(result.corrected_snapshot)
        if result.corrected_snapshot
        else None
    )

    return InvariantCheckResponse(
        is_valid=result.is_valid,
        violation_type=result.violation_type,
        diagnostic_warning=result.diagnostic_warning,
        corrected_snapshot=corrected_dto,
    )


@router.get(
    "/reasoning-semantics/policies",
    response_model=List[ProviderPolicyItemResponse],
    summary="获取已知大模型提供商的推理 Token 统计归一化策略表",
)
def list_provider_policies() -> List[ProviderPolicyItemResponse]:
    descriptions = {
        "openai": "OpenAI 官方规范 (o1/o3/gpt-4o): completion_tokens 包含 reasoning_tokens，严禁二次叠加",
        "anthropic": "Anthropic 规范 (Claude 3.7 Sonnet Thinking): output_tokens 包含 thinking_tokens",
        "deepseek": "DeepSeek-R1 规范: completion_tokens 已包含 reasoning_tokens，从属子集关系",
        "perplexity": "Perplexity 规范: completion_tokens 已包含 reasoning_tokens",
        "vllm_standalone": "第三方或部分自建 vLLM 网关: completion_tokens 仅代表 visible 内容，显式合并归一",
    }
    items: List[ProviderPolicyItemResponse] = []
    for k, p in _normalizer._PROVIDER_POLICY_MAP.items():
        items.append(
            ProviderPolicyItemResponse(
                provider_keyword=k,
                policy=p.value,
                description=descriptions.get(k, "默认包含归一化"),
            )
        )
    return items
