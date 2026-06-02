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

# Prompt for the Reflection Agent to analyze the conversation and extract a skill
_REFLECTION_PROMPT = """You are an expert AI Architect and Skill Extraction Engine.
Your task is to analyze the following conversation between a User and an Assistant.
Determine if the Assistant successfully completed a complex, multi-step task that could be generalized into a reusable "Skill".

A "Skill" is a structured set of instructions that teaches an AI how to perform a specific task.

CRITERIA FOR A GOOD SKILL:
1. The task is complex enough to require multiple steps or specific tool usage.
2. The task is generalizable (not tied to a single, highly specific instance).
3. The Assistant successfully completed the task.

If the conversation DOES NOT meet the criteria, output exactly: NO_SKILL_DETECTED

If the conversation DOES meet the criteria, you must output a complete, valid SKILL.md file containing YAML frontmatter and Markdown instructions.

The SKILL.md format MUST strictly follow this structure:
```markdown
---
name: <kebab-case-short-name>
description: <A clear, concise description of what this skill does (max 100 chars)>
version: 1.0.0
category: custom
tags: [<tag1>, <tag2>]
---

# <Skill Title>

## Objective
<Brief objective>

## Instructions
<Step-by-step generalized instructions extracted from the successful interaction>
1. Step 1...
2. Step 2...

## Best Practices
- <Any best practices or edge cases observed>
```

Output ONLY the raw markdown content (including the frontmatter). Do not wrap it in markdown code blocks (` ```markdown `). Do not add any conversational text before or after.
"""


async def _run_evolution_task(
    chat_id: str,
    model_cfg: ModelConfig,
) -> None:
    """Background task to analyze chat and generate a skill."""
    logger.info(f"🧠 Starting asynchronous skill evolution for chat {chat_id}")
    try:
        from app.platform_utils import get_session_factory

        session_factory = get_session_factory()

        async with session_factory() as _db:
            # Load the full chat history
            messages = await ChatService.get_all_messages(chat_id)

            if len(messages) < 4:
                # Too short to be a complex skill
                logger.debug(
                    f"Chat {chat_id} too short for skill evolution ({len(messages)} messages)"
                )
                return

            # Format conversation for the LLM
            conversation_text = ""
            for msg in messages[-10:]:  # Look at the last 10 messages for context
                role = "User" if msg.role == "user" else "Assistant"
                conversation_text += f"[{role}]: {msg.content}\n\n"

        # Initialize the LLM (using the same model config as the main agent, or a dedicated reasoning model)
        llm = await llm_manager.get_llm_from_config(
            model_cfg, streaming=False, api_keys=getattr(model_cfg, "api_keys", None)
        )

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
            logger.debug(
                f"No reusable skill detected or skill rejected by SandboxValidator for chat {chat_id}"
            )
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

        logger.info(
            f"✨ Successfully generated new skill proposal: '{skill_name}' (chat: {chat_id})"
        )

    except Exception as e:
        logger.error(
            f"Background skill evolution failed for chat {chat_id}: {e}", exc_info=True
        )


def trigger_skill_evolution(
    chat_id: str,
    model_cfg: ModelConfig,
    tool_steps_count: int = 0,
) -> None:
    """Trigger the background skill evolution engine.

    Args:
        chat_id: The chat session ID.
        model_cfg: The ModelConfig to use for the reflection LLM.
        tool_steps_count: Number of tools used in the last turn (heuristic for complexity).
    """
    # Simple heuristic: Only trigger evolution if tools were used, implying a complex task
    if tool_steps_count == 0:
        return

    # Fire and forget
    asyncio.create_task(
        _run_evolution_task(chat_id, model_cfg), name=f"skill_evolution_{chat_id}"
    )
    logger.debug(f"Triggered background skill evolution for chat {chat_id}")
