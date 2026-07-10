"""Feature registration — registers all framework + business features at startup.

Called once during application lifespan before init_features().
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.features import registry
from myrm_agent_harness.core.features.types import (
    ExperimentalInfo,
    FeatureSpec,
    FeatureStage,
)

logger = logging.getLogger(__name__)


def register_all_features() -> None:
    """Register all known features (framework-level + business-level).

    Framework-level features represent core harness capabilities.
    Business-level features represent myrm-agent-server specific functionality.
    """
    for spec in _ALL_FEATURES:
        registry.register(spec)

    logger.info(
        "Registered %d features (%d experimental)",
        len(_ALL_FEATURES),
        sum(1 for s in _ALL_FEATURES if s.stage == FeatureStage.EXPERIMENTAL),
    )


_ALL_FEATURES: list[FeatureSpec] = [
    # === Framework-level (stable) ===
    FeatureSpec(
        id="shell_tool",
        key="shell_tool",
        stage=FeatureStage.STABLE,
        default_enabled=True,
        description="Enable the shell command execution tool",
    ),
    FeatureSpec(
        id="web_search",
        key="web_search",
        stage=FeatureStage.STABLE,
        default_enabled=True,
        description="Allow the agent to perform web searches",
    ),
    FeatureSpec(
        id="memory_system",
        key="memory_system",
        stage=FeatureStage.STABLE,
        default_enabled=True,
        description="Enable the agent memory system for cross-session context",
    ),
    FeatureSpec(
        id="code_execution",
        key="code_execution",
        stage=FeatureStage.STABLE,
        default_enabled=True,
        description="Enable sandboxed code execution capabilities",
    ),
    FeatureSpec(
        id="hooks",
        key="hooks",
        stage=FeatureStage.STABLE,
        default_enabled=True,
        description="Enable lifecycle hooks system",
    ),
    # === Business-level (stable) ===
    FeatureSpec(
        id="skill_management",
        key="skill_management",
        stage=FeatureStage.STABLE,
        default_enabled=True,
        description="Enable skill discovery, installation, and management",
    ),
    FeatureSpec(
        id="cron_jobs",
        key="cron_jobs",
        stage=FeatureStage.STABLE,
        default_enabled=True,
        description="Enable scheduled task automation",
    ),
    FeatureSpec(
        id="media_generation",
        key="media_generation",
        stage=FeatureStage.STABLE,
        default_enabled=True,
        description="Enable image and video generation capabilities",
    ),
    # === Experimental ===
    FeatureSpec(
        id="skill_optimization",
        key="skill_optimization",
        stage=FeatureStage.EXPERIMENTAL,
        default_enabled=False,
        description="Enable automatic skill quality optimization via shadow testing",
        experimental_info=ExperimentalInfo(
            name="Skill Optimization",
            description=("Automatically test and optimize skill quality through A/B shadow testing. May increase token usage."),
            announcement="NEW: Skill Optimization is now available as an experimental feature.",
        ),
    ),
    FeatureSpec(
        id="deep_research",
        key="deep_research",
        stage=FeatureStage.EXPERIMENTAL,
        default_enabled=False,
        description="Multi-step deep research with plan review, clarification, and wiki archiving",
        experimental_info=ExperimentalInfo(
            name="Deep Research",
            description=(
                "Execute structured multi-step research with automatic plan generation, "
                "HITL review gates, and wiki archiving. Requires search service configured."
            ),
            announcement="NEW: Deep Research is now available as an experimental feature.",
        ),
    ),
    FeatureSpec(
        id="companion_mode",
        key="companion_mode",
        stage=FeatureStage.EXPERIMENTAL,
        default_enabled=False,
        description="Enable AI companion personality and conversational mode",
        experimental_info=ExperimentalInfo(
            name="Companion Mode",
            description=(
                "Enable a conversational AI companion with customizable "
                "personality. More casual and interactive interaction style."
            ),
        ),
    ),
    FeatureSpec(
        id="voice_interaction",
        key="voice_interaction",
        stage=FeatureStage.EXPERIMENTAL,
        default_enabled=False,
        description="Enable voice input/output for agent interaction",
        experimental_info=ExperimentalInfo(
            name="Voice Interaction",
            description=(
                "Use speech-to-text and text-to-speech for hands-free agent interaction. Requires microphone permission."
            ),
        ),
    ),
    FeatureSpec(
        id="consensus",
        key="consensus",
        stage=FeatureStage.EXPERIMENTAL,
        default_enabled=False,
        description="Enable multi-model consensus reasoning for higher-quality answers",
        experimental_info=ExperimentalInfo(
            name="Consensus Mode",
            description=(
                "Use multiple AI models to independently reason about a question, "
                "then synthesize their answers into a single high-quality response. "
                "Increases token usage proportional to the number of reference models."
            ),
        ),
    ),
    FeatureSpec(
        id="goals_system",
        key="goals_system",
        stage=FeatureStage.EXPERIMENTAL,
        default_enabled=True,
        description="Enable unified long-term goal tracking and context defense system",
        experimental_info=ExperimentalInfo(
            name="Unified Goals System",
            description=(
                "Track, resume and stash long-term goals across multiple sessions with intelligent context continuation defense."
            ),
        ),
    ),
]
