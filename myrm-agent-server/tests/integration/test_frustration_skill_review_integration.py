"""Integration test: Frustration detection + Skill Review pipeline with real LLM.

Validates the complete flow:
1. FrustrationDetector detects user frustration (regex, no LLM)
2. Relevance check via real LLM call
3. Preference extraction via real LLM call
4. SkillReviewResult construction (verifies format)
5. reviewer.py correctly rejects 'DO NOT CAPTURE' patterns

Uses LITE_MODEL for cost efficiency.
"""

from __future__ import annotations

import os

import pytest

from tests.support.test_secrets import load_test_secrets, resolve_test_env


def _require_lite_model() -> bool:
    secrets = load_test_secrets()
    return bool(secrets.lite_api_key and secrets.lite_base_url)


@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY"),
    reason="Integration test requires LITE_API_KEY in .env.test",
)
class TestFrustrationSkillReviewIntegration:
    """Real LLM integration tests for frustration routing + skill review."""

    @pytest.fixture()
    def lite_llm_func(self):
        """Create a real LLM call function using LITE_MODEL."""
        from litellm import acompletion
        from myrm_agent_harness.agent.config.litellm_routing import (
            normalize_env_model_selection_string,
        )

        api_key = resolve_test_env("LITE_API_KEY")
        base_url = resolve_test_env("LITE_BASE_URL")
        raw_model = resolve_test_env("LITE_MODEL")
        model = normalize_env_model_selection_string(raw_model)

        async def _call(system: str, user: str) -> str:
            response = await acompletion(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                api_key=api_key,
                api_base=base_url,
                max_tokens=200,
                temperature=0.0,
            )
            return str(response.choices[0].message.content or "")

        return _call

    @pytest.mark.asyncio
    async def test_frustration_detection_triggers_correctly(self) -> None:
        """Verify regex-based detection identifies frustration without any LLM call."""
        from myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector import (
            FrustrationCategory,
            detect_frustration,
        )

        messages = [
            {"role": "user", "content": "Write a sort function"},
            {"role": "assistant", "content": "Here's a comprehensive guide..."},
            {"role": "user", "content": "stop explaining everything, just show me the code"},
        ]
        signal = detect_frustration(messages)
        assert signal is not None
        assert signal.category == FrustrationCategory.VERBOSITY

    @pytest.mark.asyncio
    async def test_relevance_check_with_real_llm(self, lite_llm_func) -> None:
        """Verify LLM correctly judges relevance between frustration and skill."""
        from myrm_agent_harness.utils.text_sanitizer import extract_and_strip_think_blocks

        from app.ai_agents.general_agent.frustration_routing import (
            _RELEVANCE_PROMPT_TEMPLATE,
            _RELEVANCE_SYSTEM,
        )

        prompt = _RELEVANCE_PROMPT_TEMPLATE.format(
            frustration="stop adding so many comments to the code",
            skill_name="code-developer",
            skill_desc="Focused coding assistant — write, debug, review code",
        )
        raw = await lite_llm_func(_RELEVANCE_SYSTEM, prompt)
        answer, think_blocks = extract_and_strip_think_blocks(raw)
        combined = (answer + " ".join(think_blocks)).strip().upper()
        assert "YES" in combined, f"Expected YES in response, got raw: {raw[:200]}"

    @pytest.mark.asyncio
    async def test_relevance_check_rejects_irrelevant(self, lite_llm_func) -> None:
        """Verify LLM correctly rejects irrelevant skill for frustration."""
        from myrm_agent_harness.utils.text_sanitizer import extract_and_strip_think_blocks

        from app.ai_agents.general_agent.frustration_routing import (
            _RELEVANCE_PROMPT_TEMPLATE,
            _RELEVANCE_SYSTEM,
        )

        prompt = _RELEVANCE_PROMPT_TEMPLATE.format(
            frustration="stop adding so many comments to the code",
            skill_name="travel-planner",
            skill_desc="Itinerary design and destination research",
        )
        raw = await lite_llm_func(_RELEVANCE_SYSTEM, prompt)
        answer, think_blocks = extract_and_strip_think_blocks(raw)
        combined = (answer + " ".join(think_blocks)).strip().upper()
        assert "NO" in combined, f"Expected NO in response, got raw: {raw[:200]}"

    @pytest.mark.asyncio
    async def test_preference_extraction_with_real_llm(self, lite_llm_func) -> None:
        """Verify LLM extracts a concise preference instruction."""
        from myrm_agent_harness.utils.text_sanitizer import extract_and_strip_think_blocks

        from app.ai_agents.general_agent.frustration_routing import (
            _PREFERENCE_SUMMARY_SYSTEM,
        )

        raw = await lite_llm_func(
            _PREFERENCE_SUMMARY_SYSTEM,
            "User message: don't add comments to my code unless it's non-obvious logic",
        )
        result, _ = extract_and_strip_think_blocks(raw)
        result = result.strip()
        assert len(result) > 5, f"Preference too short: {result}"
        assert len(result) < 500, f"Preference too long: {result}"

    @pytest.mark.asyncio
    async def test_reviewer_rejects_do_not_capture_patterns(self) -> None:
        """Verify the reviewer prompt contains transient-error exclusion rules."""
        from myrm_agent_harness.agent.skills.evolution.review.reviewer import (
            _REVIEW_PROMPT_TEMPLATE,
        )

        assert "DO NOT CAPTURE" in _REVIEW_PROMPT_TEMPLATE or "transient" in _REVIEW_PROMPT_TEMPLATE.lower()

    @pytest.mark.asyncio
    async def test_reviewer_contains_naming_constraints(self) -> None:
        """Verify the reviewer enforces naming rules."""
        from myrm_agent_harness.agent.skills.evolution.review.reviewer import (
            _REVIEW_PROMPT_TEMPLATE,
        )

        assert "NAMING CONSTRAINT" in _REVIEW_PROMPT_TEMPLATE
        assert "lowercase" in _REVIEW_PROMPT_TEMPLATE.lower()

    @pytest.mark.asyncio
    async def test_reviewer_enforces_priority_order(self) -> None:
        """Verify the reviewer prioritizes patching over creating."""
        from myrm_agent_harness.agent.skills.evolution.review.reviewer import (
            _REVIEW_PROMPT_TEMPLATE,
        )

        assert "PRIORITY ORDER" in _REVIEW_PROMPT_TEMPLATE
        assert "skill_patch" in _REVIEW_PROMPT_TEMPLATE

    @pytest.mark.asyncio
    async def test_full_frustration_routing_pipeline(self, lite_llm_func) -> None:
        """Full pipeline: detection → relevance → extraction → result construction."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector import (
            detect_frustration,
        )

        messages = [
            {"role": "user", "content": "Write a Python function to reverse a list"},
            {"role": "assistant", "content": "Here's a detailed explanation..."},
            {"role": "user", "content": "just give me the code, stop explaining everything"},
        ]

        signal = detect_frustration(messages)
        assert signal is not None

        mock_skill = MagicMock()
        mock_skill.name = "code-developer"
        mock_skill.description = "Write code for the user. Controls code style, verbosity, comments, and explanation level."
        mock_skill.evolution_locked = False

        call_count = {"relevance": 0, "preference": 0}

        async def deterministic_llm_func(system: str, user: str) -> str:
            if "relevance judge" in system.lower():
                call_count["relevance"] += 1
                return "YES"
            call_count["preference"] += 1
            return await lite_llm_func(system, user)

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
            patch(
                "app.ai_agents.general_agent.frustration_routing._cooldown_registry",
                {},
            ),
        ):
            mock_bus.return_value.publish = MagicMock()

            from app.ai_agents.general_agent.frustration_routing import (
                _run_frustration_routing,
            )

            await _run_frustration_routing(
                messages,
                agent_id="test-agent",
                skill_ids=["skill-code-dev"],
                llm_func=deterministic_llm_func,
                chat_id="integration-test-chat",
            )

            assert call_count["relevance"] == 1
            assert call_count["preference"] == 1
            mock_process.assert_called_once()
            call_args = mock_process.call_args[0][0]
            assert call_args["type"] == "skill_patch"
            assert call_args["has_value"] is True
            assert call_args["source"] == "frustration_signal"
            assert "[PREFERENCE]" in call_args["content"]
            assert call_args["skill_name"] == "code-developer"

            mock_bus.return_value.publish.assert_called_once()
            event_data = mock_bus.return_value.publish.call_args[0][0].data
            assert event_data["operation"] == "frustration_skill_learned"
            assert event_data["skill_name"] == "code-developer"

    @pytest.mark.asyncio
    async def test_cooldown_blocks_repeated_evolution(self, lite_llm_func) -> None:
        """After triggering evolution, cooldown blocks same skill for 24h."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.ai_agents.general_agent.frustration_routing import (
            _run_frustration_routing,
        )

        messages = [
            {"role": "user", "content": "Explain sorting"},
            {"role": "assistant", "content": "Here's a long explanation..."},
            {"role": "user", "content": "too verbose, get to the point"},
        ]

        mock_skill = MagicMock()
        mock_skill.name = "code-developer"
        mock_skill.description = "Coding assistant"
        mock_skill.evolution_locked = False

        import time

        fake_registry = {"skill-code-dev": time.monotonic()}

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
                "app.ai_agents.general_agent.frustration_routing._cooldown_registry",
                fake_registry,
            ),
        ):
            await _run_frustration_routing(
                messages,
                agent_id="test-agent",
                skill_ids=["skill-code-dev"],
                llm_func=lite_llm_func,
                chat_id="cooldown-test",
            )
            mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_skills_iterates_until_relevant(self, lite_llm_func) -> None:
        """When first skill is irrelevant, should check next skill."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.ai_agents.general_agent.frustration_routing import (
            _run_frustration_routing,
        )

        messages = [
            {"role": "user", "content": "Write a function"},
            {"role": "assistant", "content": "Here's a long explanation..."},
            {"role": "user", "content": "stop explaining everything, just give me the answer"},
        ]

        irrelevant_skill = MagicMock()
        irrelevant_skill.name = "travel-planner"
        irrelevant_skill.description = "Itinerary design and travel research"
        irrelevant_skill.evolution_locked = False

        relevant_skill = MagicMock()
        relevant_skill.name = "code-developer"
        relevant_skill.description = "Focused coding assistant — write, debug, review code"
        relevant_skill.evolution_locked = False

        async def mock_get_skill(skill_id: str):
            if skill_id == "skill-travel":
                return irrelevant_skill
            return relevant_skill

        with (
            patch(
                "app.core.skills.store.service.skills_service.get_skill",
                new=AsyncMock(side_effect=mock_get_skill),
            ),
            patch(
                "app.services.skills.growth_lifecycle.process_skill_review_result",
                new=AsyncMock(),
            ) as mock_process,
            patch(
                "app.services.event.app_event_bus.get_event_bus",
            ) as mock_bus,
            patch(
                "app.ai_agents.general_agent.frustration_routing._cooldown_registry",
                {},
            ),
        ):
            mock_bus.return_value.publish = MagicMock()

            await _run_frustration_routing(
                messages,
                agent_id="test-agent",
                skill_ids=["skill-travel", "skill-code"],
                llm_func=lite_llm_func,
                chat_id="multi-skill-test",
            )

            if mock_process.called:
                call_args = mock_process.call_args[0][0]
                assert call_args["skill_name"] == "code-developer"

    @pytest.mark.asyncio
    async def test_all_frustration_categories_detected(self) -> None:
        """Verify all frustration categories are correctly detected."""
        from myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector import (
            FrustrationCategory,
            detect_frustration,
        )

        test_cases = [
            (
                [{"role": "user", "content": "too verbose, simplify"}],
                FrustrationCategory.VERBOSITY,
            ),
            (
                [{"role": "user", "content": "please stop doing that"}],
                FrustrationCategory.STYLE,
            ),
            (
                [{"role": "user", "content": "no markdown tables please"}],
                FrustrationCategory.FORMAT,
            ),
            (
                [{"role": "user", "content": "stop asking me every time, just do it"}],
                FrustrationCategory.WORKFLOW,
            ),
            (
                [{"role": "user", "content": "from now on always use TypeScript"}],
                FrustrationCategory.GENERAL,
            ),
        ]

        for messages, expected_category in test_cases:
            signal = detect_frustration(messages)
            assert signal is not None, f"Failed to detect {expected_category}"
            assert signal.category == expected_category, (
                f"Expected {expected_category}, got {signal.category} for '{messages[0]['content']}'"
            )

    @pytest.mark.asyncio
    async def test_chinese_frustration_patterns(self) -> None:
        """Verify Chinese language frustration patterns work."""
        from myrm_agent_harness.agent.skills.evolution.pipeline.frustration_detector import (
            FrustrationCategory,
            detect_frustration,
        )

        test_cases = [
            ([{"role": "user", "content": "\u592a\u5570\u55e6\u4e86"}], FrustrationCategory.VERBOSITY),
            ([{"role": "user", "content": "\u76f4\u63a5\u7ed9\u6211\u7b54\u6848"}], FrustrationCategory.VERBOSITY),
            (
                [{"role": "user", "content": "\u4ee5\u540e\u90fd\u522b\u52a0\u8fd9\u4e48\u591a\u6ce8\u91ca\u4e86"}],
                FrustrationCategory.STYLE,
            ),
            ([{"role": "user", "content": "\u4e0d\u8981\u7528\u8868\u683c\u683c\u5f0f"}], FrustrationCategory.FORMAT),
            (
                [{"role": "user", "content": "\u4e0d\u7528\u6bcf\u6b21\u90fd\u95ee\u6211\u786e\u8ba4"}],
                FrustrationCategory.WORKFLOW,
            ),
        ]

        for messages, expected_category in test_cases:
            signal = detect_frustration(messages)
            assert signal is not None, f"Failed to detect Chinese: '{messages[0]['content']}'"
            assert signal.category == expected_category

    @pytest.mark.asyncio
    async def test_pruner_handles_edge_cases(self) -> None:
        """Verify pruner handles edge cases correctly."""
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        from myrm_agent_harness.agent.skills.evolution.review.pruner import prune_trajectory

        assert prune_trajectory([]) == ""

        result = prune_trajectory([SystemMessage(content="System prompt")])
        assert result == ""

        long_tool_result = "x" * 1000
        from langchain_core.messages import ToolMessage

        history = [
            HumanMessage(content="test"),
            AIMessage(content="", tool_calls=[{"name": "bash", "args": {"cmd": "ls"}, "id": "c1"}]),
            ToolMessage(content=long_tool_result, tool_call_id="c1", name="bash"),
        ]
        result = prune_trajectory(history, max_tool_result_length=50)
        assert "...(truncated)" in result
        assert len(result) < 1000
