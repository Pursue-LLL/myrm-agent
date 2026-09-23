"""Asynchronous Skill Self-Evolution Engine.

[INPUT]
- app.services.chat.chat_service::ChatService
- myrm_agent_harness.toolkits.llms::llm_manager
- myrm_agent_harness.agent.skills.evolution::SkillBudgetGovernor (POS: Skill budget governor protocol and evaluator)
- myrm_agent_harness.utils.text_utils::get_token_count (POS: Token counting utility)
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

from myrm_agent_harness.agent.skills.evolution import (
    BudgetCheckResult,
    BudgetStatus,
    EvolutionType,
    SkillBudgetGovernor,
)
from myrm_agent_harness.toolkits.llms import llm_manager

from app.core.types import ModelConfig
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)

# Minimum tool steps before a plain chat turn qualifies for skill capture.
# Mirrors OpenClaw's heuristic of only scheduling a review after substantial
# work: a throwaway single-tool turn produces no reusable procedure, and
# capturing it only burns an LLM reflection call.
_MIN_TOOL_STEPS_FOR_CAPTURE = 3

# In-flight evolution tasks keyed by chat_id. Guards against concurrent
# captures of the same history when consecutive turns finalize in quick
# succession (asyncio task names do not enforce uniqueness).
_RUNNING_EVOLUTION_TASKS: dict[str, asyncio.Task[None]] = {}


async def _run_evolution_task(
    chat_id: str,
    model_cfg: ModelConfig,
    conversation_text: str | None = None,
    agent_id: str | None = None,
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
                agent_id=agent_id,
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


def check_skill_budget_before_evolution(
    agent_id: str | None = None,
    evolution_type: EvolutionType = EvolutionType.CAPTURED,
    governor: SkillBudgetGovernor | None = None,
) -> BudgetCheckResult:
    """Evaluate whether capacity permits triggering another skill evolution cycle."""
    gov = governor or SkillBudgetGovernor()
    try:
        from app.core.skills.store.evolution_store import get_evolution_skill_store

        store = get_evolution_skill_store()
        active_skills = store.get_active_skills(agent_id=agent_id)
        current_count = len(active_skills)
        from myrm_agent_harness.utils.text_utils import get_token_count

        current_tokens = sum(max(100, get_token_count(s.content)) for s in active_skills)

        return gov.check_budget(
            evolution_type=evolution_type,
            current_tokens=current_tokens,
            current_count=current_count,
        )
    except Exception as exc:
        logger.debug("Skill budget check skipped on error: %s", exc)
        return BudgetCheckResult(
            allowed=True,
            status=BudgetStatus.NORMAL,
            current_tokens=0,
            max_tokens=gov.config.max_tokens,
            current_count=0,
            max_count=gov.config.max_skill_count,
            message="Check skipped",
        )


def trigger_skill_evolution(
    chat_id: str,
    model_cfg: ModelConfig,
    tool_steps_count: int = 0,
    conversation_text: str | None = None,
    agent_id: str | None = None,
    governor: SkillBudgetGovernor | None = None,
) -> None:
    """Trigger the background skill evolution engine with capacity protection.

    Args:
        chat_id: The chat session ID.
        model_cfg: The ModelConfig to use for the reflection LLM.
        tool_steps_count: Number of tools used in the last turn (heuristic for complexity).
        conversation_text: Pre-built conversation text (e.g. from DW stream collector).
            When provided, skips loading from ChatService.
        agent_id: Originating agent profile ID for proposal attribution.
        governor: Optional custom capacity governor.
    """
    if _RUNNING_EVOLUTION_TASKS.get(chat_id) is not None:
        logger.debug(f"Skill evolution already in flight for chat {chat_id}; skipping duplicate trigger")
        return

    if not conversation_text and tool_steps_count < _MIN_TOOL_STEPS_FOR_CAPTURE:
        logger.debug(
            f"Chat {chat_id} turn too shallow for skill capture (tool_steps={tool_steps_count} < {_MIN_TOOL_STEPS_FOR_CAPTURE})"
        )
        return

    budget_check = check_skill_budget_before_evolution(
        agent_id=agent_id,
        evolution_type=EvolutionType.CAPTURED,
        governor=governor,
    )

    if not budget_check.allowed:
        logger.warning(
            "Skill evolution paused for chat %s due to capacity limit: %s",
            chat_id,
            budget_check.message,
        )
        try:
            from app.services.skills.ws_hub import broadcast_message

            asyncio.create_task(
                broadcast_message(
                    "SKILL_CAPACITY_LIMIT",
                    {
                        "chat_id": chat_id,
                        "agent_id": agent_id,
                        "status": str(budget_check.status),
                        "message": budget_check.message,
                        "current_tokens": budget_check.current_tokens,
                        "max_tokens": budget_check.max_tokens,
                        "current_count": budget_check.current_count,
                        "max_count": budget_check.max_count,
                    },
                )
            )
        except Exception as ws_err:
            logger.debug("Failed to broadcast skill capacity limit event: %s", ws_err)
        return

    if budget_check.status == BudgetStatus.SOFT_LIMIT:
        logger.info(
            "Skill capacity warning for chat %s: %s",
            chat_id,
            budget_check.message,
        )
        try:
            from app.services.skills.ws_hub import broadcast_message

            asyncio.create_task(
                broadcast_message(
                    "SKILL_CAPACITY_WARNING",
                    {
                        "chat_id": chat_id,
                        "agent_id": agent_id,
                        "status": str(budget_check.status),
                        "message": budget_check.message,
                        "current_tokens": budget_check.current_tokens,
                        "max_tokens": budget_check.max_tokens,
                    },
                )
            )
        except Exception as ws_err:
            logger.debug("Failed to broadcast skill capacity warning event: %s", ws_err)

    task = asyncio.create_task(
        _run_evolution_task(chat_id, model_cfg, conversation_text=conversation_text, agent_id=agent_id),
        name=f"skill_evolution_{chat_id}",
    )
    _RUNNING_EVOLUTION_TASKS[chat_id] = task
    # A completed task must not block a later evolution of the same chat.
    task.add_done_callback(lambda _t: _RUNNING_EVOLUTION_TASKS.pop(chat_id, None))
    logger.debug(f"Triggered background skill evolution for chat {chat_id}")
