"""Tests for frustration signal → skill evolution routing.

Unit tests for the FrustrationDetector detection + routing pipeline.
Integration tests require LITE_MODEL environment variable for real LLM calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def frustration_messages_verbosity() -> list[dict[str, str]]:
    """User frustrated by verbosity."""
    return [
        {"role": "user", "content": "How do I reverse a list in Python?"},
        {"role": "assistant", "content": "Here's a detailed 10-paragraph explanation..."},
        {"role": "user", "content": "just give me the answer, stop explaining everything"},
    ]


@pytest.fixture()
def frustration_messages_style_zh() -> list[dict[str, str]]:
    """Chinese user frustrated by excessive comments."""
    return [
        {"role": "user", "content": "帮我写一个排序函数"},
        {"role": "assistant", "content": "# 这是排序函数\ndef sort(arr):\n    # 排序逻辑\n    ..."},
        {"role": "user", "content": "以后都别加这么多注释了，我能看懂代码"},
    ]


@pytest.fixture()
def frustration_messages_format() -> list[dict[str, str]]:
    """User frustrated by markdown formatting."""
    return [
        {"role": "user", "content": "Show me the API response structure"},
        {"role": "assistant", "content": "| Field | Type |\n|---|---|\n..."},
        {"role": "user", "content": "no markdown tables please, plain text only"},
    ]


@pytest.fixture()
def neutral_messages() -> list[dict[str, str]]:
    """Normal conversation without frustration."""
    return [
        {"role": "user", "content": "How do I create a class in Python?"},
        {"role": "assistant", "content": "You can define a class using the class keyword..."},
        {"role": "user", "content": "Thanks, that makes sense!"},
    ]


# ---------------------------------------------------------------------------
# Unit: Frustration Detection
# ---------------------------------------------------------------------------


class TestFrustrationDetectionUnit:
    """Pure unit tests for frustration detection (no LLM)."""

    def test_detects_verbosity_frustration(self, frustration_messages_verbosity: list) -> None:
        from myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector import (
            FrustrationCategory,
            detect_frustration,
        )

        result = detect_frustration(frustration_messages_verbosity)
        assert result is not None
        assert result.category == FrustrationCategory.VERBOSITY

    def test_detects_style_frustration_chinese(self, frustration_messages_style_zh: list) -> None:
        from myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector import (
            FrustrationCategory,
            detect_frustration,
        )

        result = detect_frustration(frustration_messages_style_zh)
        assert result is not None
        assert result.category == FrustrationCategory.STYLE

    def test_detects_format_frustration(self, frustration_messages_format: list) -> None:
        from myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector import (
            FrustrationCategory,
            detect_frustration,
        )

        result = detect_frustration(frustration_messages_format)
        assert result is not None
        assert result.category == FrustrationCategory.FORMAT

    def test_no_detection_on_neutral(self, neutral_messages: list) -> None:
        from myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector import (
            detect_frustration,
        )

        assert detect_frustration(neutral_messages) is None


# ---------------------------------------------------------------------------
# Unit: Routing Logic
# ---------------------------------------------------------------------------


class TestFrustrationRoutingUnit:
    """Unit tests for the routing callback with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_skips_when_no_frustration(self, neutral_messages: list) -> None:
        from app.ai_agents.general_agent.frustration_routing import make_frustration_skill_routing_callback

        mock_llm = AsyncMock(return_value="YES")
        cb = make_frustration_skill_routing_callback(
            agent_id="test-agent",
            skill_ids=["skill-1"],
            llm_func=mock_llm,
        )
        await cb(neutral_messages, "chat-1")
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_skills_bound(self, frustration_messages_verbosity: list) -> None:
        from app.ai_agents.general_agent.frustration_routing import make_frustration_skill_routing_callback

        mock_llm = AsyncMock(return_value="YES")
        cb = make_frustration_skill_routing_callback(
            agent_id="test-agent",
            skill_ids=[],
            llm_func=mock_llm,
        )
        await cb(frustration_messages_verbosity, "chat-1")
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_routes_to_relevant_skill(self, frustration_messages_verbosity: list) -> None:
        from app.ai_agents.general_agent.frustration_routing import (
            _run_frustration_routing,
        )

        mock_skill = MagicMock()
        mock_skill.name = "general-qa"
        mock_skill.description = "General Q&A skill"
        mock_skill.evolution_locked = False

        mock_llm = AsyncMock(side_effect=["YES", "Be concise. Skip explanations."])

        with (
            patch(
                "app.core.skills.store.service.skills_service.get_skill",
                new=AsyncMock(return_value=mock_skill),
            ),
            patch(
                "app.services.skills.growth_lifecycle.process_skill_review_result",
                new=AsyncMock(),
            ) as mock_process,
            patch(
                "app.services.event.app_event_bus.get_event_bus",
            ) as mock_bus,
        ):
            mock_bus.return_value.publish = MagicMock()

            await _run_frustration_routing(
                frustration_messages_verbosity,
                agent_id="test-agent",
                skill_ids=["skill-general-qa"],
                llm_func=mock_llm,
                chat_id="chat-123",
            )

            mock_process.assert_called_once()
            call_args = mock_process.call_args[0][0]
            assert call_args["type"] == "skill_patch"
            assert call_args["source"] == "frustration_signal"
            assert "[PREFERENCE]" in call_args["content"]

            mock_bus.return_value.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_locked_skill(self, frustration_messages_verbosity: list) -> None:
        from app.ai_agents.general_agent.frustration_routing import (
            _run_frustration_routing,
        )

        mock_skill = MagicMock()
        mock_skill.name = "locked-skill"
        mock_skill.description = "A locked skill"
        mock_skill.evolution_locked = True

        mock_llm = AsyncMock(return_value="YES")

        with patch(
            "app.core.skills.store.service.skills_service.get_skill",
            new=AsyncMock(return_value=mock_skill),
        ):
            await _run_frustration_routing(
                frustration_messages_verbosity,
                agent_id="test-agent",
                skill_ids=["skill-locked"],
                llm_func=mock_llm,
                chat_id="chat-123",
            )
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_llm_says_not_relevant(self, frustration_messages_verbosity: list) -> None:
        from app.ai_agents.general_agent.frustration_routing import (
            _run_frustration_routing,
        )

        mock_skill = MagicMock()
        mock_skill.name = "database-ops"
        mock_skill.description = "Database operations skill"
        mock_skill.evolution_locked = False

        mock_llm = AsyncMock(return_value="NO")

        with patch(
            "app.core.skills.store.service.skills_service.get_skill",
            new=AsyncMock(return_value=mock_skill),
        ):
            await _run_frustration_routing(
                frustration_messages_verbosity,
                agent_id="test-agent",
                skill_ids=["skill-db"],
                llm_func=mock_llm,
                chat_id="chat-123",
            )
            assert mock_llm.call_count == 1
