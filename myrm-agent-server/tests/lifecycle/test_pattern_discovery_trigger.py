"""Tests for the pattern discovery trigger (LLM injection + graceful degradation)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.lifecycle import pattern_discovery_trigger


def _make_report(*, skipped: bool = False, pattern_count: int = 1) -> SimpleNamespace:
    if skipped:
        return SimpleNamespace(
            skipped=True,
            skip_reason="memory system not yet mature enough",
            has_patterns=False,
            patterns=[],
            duration_ms=10.0,
        )
    patterns = [
        SimpleNamespace(
            title=f"Pattern {i}",
            description="description",
            evidence_summary="evidence",
            durability="established",
            confidence=0.85,
            actionable_suggestion="suggestion",
        )
        for i in range(pattern_count)
    ]
    return SimpleNamespace(
        skipped=False,
        skip_reason=None,
        has_patterns=True,
        patterns=patterns,
        memory_count=120,
        insight_count=5,
        duration_ms=100.0,
        meta_observation="User tends to plan work on weekday mornings.",
    )


class TestBuildPlatformLLM:
    @pytest.mark.asyncio
    async def test_returns_chat_model_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            AsyncMock(
                return_value={
                    "model": "gpt-4o",
                    "api_key": "sk-test",
                    "api_base": "https://api.test.com",
                }
            ),
        )

        llm = await pattern_discovery_trigger._build_platform_llm()

        assert llm is not None
        assert llm.model == "gpt-4o"
        assert llm.api_key == "sk-test"
        assert llm.api_base == "https://api.test.com"
        assert llm.temperature == 0

    @pytest.mark.asyncio
    async def test_returns_none_when_model_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            AsyncMock(return_value={"model": "", "api_key": "sk-test"}),
        )

        llm = await pattern_discovery_trigger._build_platform_llm()

        assert llm is None

    @pytest.mark.asyncio
    async def test_returns_none_when_api_key_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            AsyncMock(return_value={"model": "gpt-4o", "api_key": ""}),
        )

        llm = await pattern_discovery_trigger._build_platform_llm()

        assert llm is None

    @pytest.mark.asyncio
    async def test_returns_none_when_config_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _raise() -> dict[str, object]:
            raise RuntimeError("config incomplete")

        monkeypatch.setattr(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            _raise,
        )

        llm = await pattern_discovery_trigger._build_platform_llm()

        assert llm is None


class TestRunPatternDiscoveryCycle:
    @pytest.mark.asyncio
    async def test_skips_when_llm_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            pattern_discovery_trigger,
            "_build_platform_llm",
            AsyncMock(return_value=None),
        )
        run_discovery = AsyncMock()
        monkeypatch.setattr(
            "myrm_agent_harness.toolkits.memory.strategies.pattern_discovery.run_pattern_discovery",
            run_discovery,
        )

        await pattern_discovery_trigger.run_pattern_discovery_cycle()

        run_discovery.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_records_event_when_patterns_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = MagicMock()
        monkeypatch.setattr(pattern_discovery_trigger, "_build_platform_llm", AsyncMock(return_value=llm))
        manager = AsyncMock()
        monkeypatch.setattr(
            "app.lifecycle.memory_guardian_ops.create_guardian_memory_manager",
            AsyncMock(return_value=manager),
        )
        report = _make_report(pattern_count=2)
        monkeypatch.setattr(
            "myrm_agent_harness.toolkits.memory.strategies.pattern_discovery.run_pattern_discovery",
            AsyncMock(return_value=report),
        )
        record_event = AsyncMock()
        monkeypatch.setattr(pattern_discovery_trigger, "record_pattern_discovery_event", record_event)

        await pattern_discovery_trigger.run_pattern_discovery_cycle()

        record_event.assert_awaited_once_with(report)

    @pytest.mark.asyncio
    async def test_skips_when_harness_gate_not_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = MagicMock()
        monkeypatch.setattr(pattern_discovery_trigger, "_build_platform_llm", AsyncMock(return_value=llm))
        manager = AsyncMock()
        monkeypatch.setattr(
            "app.lifecycle.memory_guardian_ops.create_guardian_memory_manager",
            AsyncMock(return_value=manager),
        )
        report = _make_report(skipped=True)
        monkeypatch.setattr(
            "myrm_agent_harness.toolkits.memory.strategies.pattern_discovery.run_pattern_discovery",
            AsyncMock(return_value=report),
        )
        record_event = AsyncMock()
        monkeypatch.setattr(pattern_discovery_trigger, "record_pattern_discovery_event", record_event)

        await pattern_discovery_trigger.run_pattern_discovery_cycle()

        record_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_is_non_fatal_on_unexpected_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            pattern_discovery_trigger,
            "_build_platform_llm",
            AsyncMock(side_effect=RuntimeError("boom")),
        )

        await pattern_discovery_trigger.run_pattern_discovery_cycle()


class TestRunPatternDiscoveryOnce:
    @pytest.mark.asyncio
    async def test_returns_skipped_when_llm_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            pattern_discovery_trigger,
            "_build_platform_llm",
            AsyncMock(return_value=None),
        )

        result = await pattern_discovery_trigger.run_pattern_discovery_once()

        assert result == {"triggered": True, "skipped": True, "reason": "no platform default model configured"}

    @pytest.mark.asyncio
    async def test_returns_patterns_when_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = MagicMock()
        monkeypatch.setattr(pattern_discovery_trigger, "_build_platform_llm", AsyncMock(return_value=llm))
        manager = AsyncMock()
        monkeypatch.setattr(
            "app.lifecycle.memory_guardian_ops.create_guardian_memory_manager",
            AsyncMock(return_value=manager),
        )
        report = _make_report(pattern_count=3)
        monkeypatch.setattr(
            "myrm_agent_harness.toolkits.memory.strategies.pattern_discovery.run_pattern_discovery",
            AsyncMock(return_value=report),
        )
        record_event = AsyncMock()
        monkeypatch.setattr(pattern_discovery_trigger, "record_pattern_discovery_event", record_event)

        result = await pattern_discovery_trigger.run_pattern_discovery_once()

        assert result == {
            "triggered": True,
            "skipped": False,
            "pattern_count": 3,
            "duration_ms": 100.0,
            "meta_observation": "User tends to plan work on weekday mornings.",
        }
        record_event.assert_awaited_once_with(report)

    @pytest.mark.asyncio
    async def test_returns_skip_reason_when_gate_not_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = MagicMock()
        monkeypatch.setattr(pattern_discovery_trigger, "_build_platform_llm", AsyncMock(return_value=llm))
        manager = AsyncMock()
        monkeypatch.setattr(
            "app.lifecycle.memory_guardian_ops.create_guardian_memory_manager",
            AsyncMock(return_value=manager),
        )
        report = _make_report(skipped=True)
        monkeypatch.setattr(
            "myrm_agent_harness.toolkits.memory.strategies.pattern_discovery.run_pattern_discovery",
            AsyncMock(return_value=report),
        )

        result = await pattern_discovery_trigger.run_pattern_discovery_once()

        assert result == {
            "triggered": True,
            "skipped": True,
            "reason": "memory system not yet mature enough",
        }