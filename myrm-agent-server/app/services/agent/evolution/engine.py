"""Asynchronous Skill Self-Evolution Engine.

[INPUT]
- app.services.chat.chat_service::ChatService
- myrm_agent_harness.toolkits.llms::llm_manager
- app.core.types::ModelConfig

[OUTPUT]
- trigger_skill_evolution: async function to trigger background evolution

[POS]
Business-layer implementation of the Skill Self-Evolution Engine.
Runs asynchronously in the background after a successful agent interaction.
Analyzes the chat history to detect successful complex patterns and automatically
generates reusable SKILL.md definitions, saving them to the local persistent volume.
"""

import asyncio
import logging

from myrm_agent_harness.toolkits.llms import llm_manager

from app.core.types import ModelConfig
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)


async def _run_evolution_task(
    chat_id: str,
    model_cfg: ModelConfig,
    conversation_text: str | None = None,
) -> None:
    """Background task to analyze chat and generate a skill."""
    logger.info(f"🧠 Starting asynchronous skill evolution for chat {chat_id}")
    try:
        if not conversation_text:
            from app.platform_utils import get_session_factory

            session_factory = get_session_factory()

            async with session_factory() as _db:
                messages = await ChatService.get_all_messages(chat_id)

                if len(messages) < 4:
                    logger.debug(f"Chat {chat_id} too short for skill evolution ({len(messages)} messages)")
                    return

                conversation_text = ""
                for msg in messages[-10:]:
                    role = "User" if msg.role == "user" else "Assistant"
                    conversation_text += f"[{role}]: {msg.content}\n\n"

        # Initialize the LLM (using the same model config as the main agent, or a dedicated reasoning model)
        llm = await llm_manager.get_llm_from_config(model_cfg, streaming=False, api_keys=getattr(model_cfg, "api_keys", None))

        # We delegate the actual extraction and validation to the Harness engine
        import platform
        import sys
        from pathlib import Path

        from myrm_agent_harness.agent.skills.evolution.core.engine import (
            SkillEvolutionEngine,
        )
        from myrm_agent_harness.agent.skills.evolution.core.types import (
            EnvironmentFingerprint,
        )
        from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

        from app.config.settings import settings as _settings

        db_path = Path(_settings.database.state_dir) / "skills.db"
        store = SkillStore(db_path=db_path)

        # Capture environment fingerprint for the capsule
        env_fingerprint = EnvironmentFingerprint(
            os_platform=platform.system(),
            os_release=platform.release(),
            python_version=sys.version.split(" ")[0],
        )

        try:
            engine = SkillEvolutionEngine(store=store, llm=llm)

            proposal = await engine.capture_skill_from_trajectory(
                trajectory=conversation_text,
                session_id=chat_id,
                env_fingerprint=env_fingerprint,
            )
        finally:
            store.close()

        if not proposal:
            logger.debug(f"No reusable skill detected or skill rejected by SandboxValidator for chat {chat_id}")
            return

        skill_name = proposal.skill_id

        from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow
        from app.services.skills.ws_hub import broadcast_proposal

        flow = ConfidenceApprovalFlow()
        await flow.process_evolution(
            proposal=proposal,
        )

        # Broadcast to the user that a new skill draft is ready for review
        await broadcast_proposal(proposal.to_dict())

        logger.info(f"✨ Successfully generated new skill proposal: '{skill_name}' (chat: {chat_id})")

    except Exception as e:
        logger.error(f"Background skill evolution failed for chat {chat_id}: {e}", exc_info=True)


def trigger_skill_evolution(
    chat_id: str,
    model_cfg: ModelConfig,
    tool_steps_count: int = 0,
    conversation_text: str | None = None,
) -> None:
    """Trigger the background skill evolution engine.

    Args:
        chat_id: The chat session ID.
        model_cfg: The ModelConfig to use for the reflection LLM.
        tool_steps_count: Number of tools used in the last turn (heuristic for complexity).
        conversation_text: Pre-built conversation text (e.g. from DW stream collector).
            When provided, skips loading from ChatService.
    """
    if tool_steps_count == 0 and not conversation_text:
        return

    asyncio.create_task(
        _run_evolution_task(chat_id, model_cfg, conversation_text=conversation_text),
        name=f"skill_evolution_{chat_id}",
    )
    logger.debug(f"Triggered background skill evolution for chat {chat_id}")
