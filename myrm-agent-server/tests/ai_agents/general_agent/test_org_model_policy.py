"""Tests for _enforce_org_model_policy in factory.py."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.ai_agents.general_agent.factory import (
    OrgModelPolicyViolation,
    _enforce_org_model_policy,
)


def _make_agent_wrapper(
    *,
    model: str = "openai/gpt-4o-mini",
    lite_model: str | None = None,
    fallback_model: str | None = None,
    safety_fallback_model: str | None = None,
    reasoning_model: str | None = None,
) -> SimpleNamespace:
    def _cfg(m: str | None) -> SimpleNamespace | None:
        return SimpleNamespace(model=m) if m else None

    return SimpleNamespace(
        model_cfg=_cfg(model),
        lite_model_cfg=_cfg(lite_model),
        fallback_model_cfg=_cfg(fallback_model),
        safety_fallback_model_cfg=_cfg(safety_fallback_model),
        reasoning_model_cfg=_cfg(reasoning_model),
    )


def _mock_config_service(return_value):
    """Patch ConfigService inside factory module (lazy-imported)."""
    mock_svc = AsyncMock()
    mock_svc.get = AsyncMock(return_value=return_value)
    return patch(
        "app.services.config.service.ConfigService",
        return_value=mock_svc,
    )


def _make_record(patterns: list[str]) -> SimpleNamespace:
    return SimpleNamespace(value={"allowed_patterns": patterns})


@pytest.mark.asyncio
async def test_no_policy_is_noop() -> None:
    wrapper = _make_agent_wrapper()
    with _mock_config_service(None):
        await _enforce_org_model_policy(wrapper)


@pytest.mark.asyncio
async def test_empty_patterns_is_noop() -> None:
    wrapper = _make_agent_wrapper()
    with _mock_config_service(_make_record([])):
        await _enforce_org_model_policy(wrapper)


@pytest.mark.asyncio
async def test_allowed_model_passes() -> None:
    wrapper = _make_agent_wrapper(model="openai/gpt-4o-mini")
    with _mock_config_service(_make_record(["openai/*"])):
        await _enforce_org_model_policy(wrapper)


@pytest.mark.asyncio
async def test_disallowed_model_raises() -> None:
    wrapper = _make_agent_wrapper(model="anthropic/claude-4-opus")
    with _mock_config_service(_make_record(["openai/*"])):
        with pytest.raises(OrgModelPolicyViolation) as exc_info:
            await _enforce_org_model_policy(wrapper)
        assert "anthropic/claude-4-opus" in str(exc_info.value)


@pytest.mark.asyncio
async def test_multiple_models_all_allowed() -> None:
    wrapper = _make_agent_wrapper(
        model="openai/gpt-4o",
        lite_model="openai/gpt-4o-mini",
        fallback_model="deepseek/deepseek-chat",
    )
    with _mock_config_service(_make_record(["openai/*", "deepseek/*"])):
        await _enforce_org_model_policy(wrapper)


@pytest.mark.asyncio
async def test_one_disallowed_among_multiple_raises() -> None:
    wrapper = _make_agent_wrapper(
        model="openai/gpt-4o",
        lite_model="anthropic/claude-3-haiku",
    )
    with _mock_config_service(_make_record(["openai/*"])):
        with pytest.raises(OrgModelPolicyViolation) as exc_info:
            await _enforce_org_model_policy(wrapper)
        assert "anthropic/claude-3-haiku" in str(exc_info.value)


@pytest.mark.asyncio
async def test_config_service_exception_is_fail_open() -> None:
    """When ConfigService raises, policy enforcement is skipped (fail-open)."""
    wrapper = _make_agent_wrapper(model="anthropic/claude-4-opus")
    mock_svc = AsyncMock()
    mock_svc.get = AsyncMock(side_effect=RuntimeError("DB unavailable"))
    with patch(
        "app.services.config.service.ConfigService",
        return_value=mock_svc,
    ):
        await _enforce_org_model_policy(wrapper)


@pytest.mark.asyncio
async def test_duplicate_models_deduped() -> None:
    """Same model across slots should be checked only once (set dedup)."""
    wrapper = _make_agent_wrapper(
        model="openai/gpt-4o-mini",
        lite_model="openai/gpt-4o-mini",
        fallback_model="openai/gpt-4o-mini",
    )
    with _mock_config_service(_make_record(["openai/*"])):
        await _enforce_org_model_policy(wrapper)


@pytest.mark.asyncio
async def test_exact_match_pattern() -> None:
    """Exact pattern (non-glob) should match exactly."""
    wrapper = _make_agent_wrapper(model="openai/gpt-4o-mini")
    with _mock_config_service(_make_record(["openai/gpt-4o-mini"])):
        await _enforce_org_model_policy(wrapper)


@pytest.mark.asyncio
async def test_exact_match_pattern_rejects_similar() -> None:
    """Exact pattern should reject models that don't match exactly."""
    wrapper = _make_agent_wrapper(model="openai/gpt-4o")
    with _mock_config_service(_make_record(["openai/gpt-4o-mini"])):
        with pytest.raises(OrgModelPolicyViolation):
            await _enforce_org_model_policy(wrapper)


@pytest.mark.asyncio
async def test_violation_carries_metadata() -> None:
    """OrgModelPolicyViolation exposes model_name and allowed_patterns."""
    wrapper = _make_agent_wrapper(model="xai/grok-3")
    patterns = ["openai/*", "anthropic/*"]
    with _mock_config_service(_make_record(patterns)):
        with pytest.raises(OrgModelPolicyViolation) as exc_info:
            await _enforce_org_model_policy(wrapper)
        assert exc_info.value.model_name == "xai/grok-3"
        assert exc_info.value.allowed_patterns == patterns


@pytest.mark.asyncio
async def test_none_model_cfg_slots_skipped() -> None:
    """None cfg slots should not contribute to model set."""
    wrapper = _make_agent_wrapper(
        model="openai/gpt-4o",
        lite_model=None,
        fallback_model=None,
    )
    with _mock_config_service(_make_record(["openai/*"])):
        await _enforce_org_model_policy(wrapper)
