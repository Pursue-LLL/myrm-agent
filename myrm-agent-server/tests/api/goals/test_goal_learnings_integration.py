"""Integration test for goal learnings extraction using REAL LLM calls.

Tests the full pipeline:
  extract_goal_learnings -> real LLM -> structured parsing -> quality filtering

Requires:
  - BASIC_API_KEY, BASIC_MODEL, BASIC_BASE_URL environment variables
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv(override=False)

_MAX_RETRIES = 2

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("BASIC_API_KEY"),
        reason="BASIC_API_KEY not set — skipping real LLM integration tests",
    ),
]


def _build_real_llm():
    """Build a real LLM instance from env vars for integration testing."""
    from dotenv import dotenv_values

    env = dotenv_values()
    api_key = env.get("BASIC_API_KEY") or os.getenv("BASIC_API_KEY", "")
    base_url = env.get("BASIC_BASE_URL") or os.getenv("BASIC_BASE_URL", "")
    raw_model = env.get("BASIC_MODEL") or os.getenv("BASIC_MODEL", "")

    # Strip provider prefix for direct OpenAI-compatible call
    model_name = raw_model.split("/", 1)[-1] if "/" in raw_model else raw_model

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url if base_url else None,
        temperature=0,
        max_tokens=4096,
    )


def _build_realistic_goal_messages() -> list[dict[str, str]]:
    """Simulate a realistic multi-turn goal execution trace."""
    return [
        {"role": "user", "content": "Implement dark mode toggle in the settings page. Use the existing theme system."},
        {
            "role": "assistant",
            "content": "I'll implement the dark mode toggle. Let me first check the existing theme system.\n\nLooking at `src/theme/ThemeProvider.tsx`, I can see it uses CSS variables with a `data-theme` attribute on the root element. The available themes are defined in `tailwind.config.ts`.\n\nI found that the toggle should be added to `src/pages/Settings/AppearanceSection.tsx`.",
        },
        {"role": "user", "content": "Good, proceed with the implementation."},
        {
            "role": "assistant",
            "content": "I've implemented the dark mode toggle:\n\n1. Added a `ThemeToggle` component in `src/components/ThemeToggle.tsx`\n2. Used the existing `useTheme()` hook from ThemeProvider\n3. Added it to AppearanceSection\n4. Stored preference in localStorage via the existing `useLocalStorage` hook\n\nNote: I initially tried to use `window.matchMedia` for system preference detection, but discovered that the existing ThemeProvider already handles this via `prefers-color-scheme` media query. So I just needed to add a 'system' option alongside 'light' and 'dark'.\n\nAlso important: the Tailwind config uses `darkMode: 'class'` strategy, so the `data-theme` attribute must be synced with the class. The ThemeProvider already does this.",
        },
        {"role": "user", "content": "Does it work with the existing color tokens?"},
        {
            "role": "assistant",
            "content": "Yes! I verified that all color tokens in `src/theme/tokens.css` have both light and dark variants defined under `:root` and `[data-theme='dark']` selectors respectively. The toggle works seamlessly because it only changes the `data-theme` attribute, which triggers the CSS variable swap automatically.\n\nOne gotcha I encountered: the `--color-surface-elevated` token was missing a dark variant, which caused the dropdown menus to appear with a white background in dark mode. I added the missing definition: `--color-surface-elevated: var(--gray-800)`.",
        },
    ]


class TestGoalLearningsIntegrationReal:
    """Integration tests using real LLM for goal learnings extraction."""

    async def test_extract_goal_learnings_real_llm(self):
        """Full pipeline: real LLM extracts actionable learnings from goal trace."""
        from myrm_agent_harness.api.hooks import (
            create_extraction_llm_func,
        )
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            extract_goal_learnings,
        )

        llm = _build_real_llm()
        llm_func = create_extraction_llm_func(llm)
        messages = _build_realistic_goal_messages()

        # Retry up to _MAX_RETRIES to handle LLM non-deterministic output
        last_error: Exception | None = None
        learnings = []
        for attempt in range(_MAX_RETRIES + 1):
            try:
                learnings = await extract_goal_learnings(
                    messages=messages,
                    goal_objective="Implement dark mode toggle in the settings page",
                    llm_func=llm_func,
                )
                if learnings:
                    break
            except Exception as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    continue
                raise

        assert len(learnings) >= 1, (
            f"Expected at least 1 learning after {_MAX_RETRIES + 1} attempts, got 0. Last error: {last_error}"
        )

        for learning in learnings:
            assert learning.memory_type == "semantic"
            assert len(learning.content) > 20, f"Learning too short: {learning.content}"
            assert learning.confidence >= 0.7
            assert learning.importance >= 0.6

        all_content = " ".join(learning.content.lower() for learning in learnings)
        has_relevant_content = any(
            keyword in all_content for keyword in ["theme", "dark", "token", "css", "tailwind", "provider"]
        )
        assert has_relevant_content, f"Learnings should reference theme/dark mode concepts. Got: {all_content[:200]}"

        print(f"\n{'=' * 60}")
        print(f"Extracted {len(learnings)} learnings:")
        for i, learning in enumerate(learnings, 1):
            print(f"  [{i}] (conf={learning.confidence}, imp={learning.importance}) {learning.content}")
        print(f"{'=' * 60}")

    async def test_extract_learnings_quality_filtering(self):
        """Verify that low-quality conversations yield fewer/no learnings."""
        from myrm_agent_harness.api.hooks import (
            create_extraction_llm_func,
        )
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            extract_goal_learnings,
        )

        llm = _build_real_llm()
        llm_func = create_extraction_llm_func(llm)

        trivial_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there! How can I help?"},
            {"role": "user", "content": "Nothing, thanks"},
            {"role": "assistant", "content": "Alright, have a good day!"},
        ]

        learnings = await extract_goal_learnings(
            messages=trivial_messages,
            goal_objective="Just chatting",
            llm_func=llm_func,
        )

        # Trivial conversation should yield very few or no learnings
        assert len(learnings) <= 1, f"Trivial chat should yield 0-1 learnings, got {len(learnings)}"
        print(f"\nTrivial conversation yielded {len(learnings)} learnings (expected 0-1)")
