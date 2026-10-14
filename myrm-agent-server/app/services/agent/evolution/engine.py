"""Asynchronous Skill Self-Evolution Engine.

[INPUT]
- app.services.chat.chat_service::ChatService
- myrm_agent_harness.toolkits.llms::llm_manager
- myrm_agent_harness.agent.skills.evolution::SkillBudgetGovernor (POS: Core capacity governor for skill self-evolution)
- app.services.skills.evolution_events::publish_skill_capacity_reached_event (POS: 技能进化事件发布：services 层事件唯一出口)
- app.core.skills.curator.service::describe_skill_lifecycle (POS: Curator business service for skill lifecycle management)
- app.core.skills.store.evolution_store::get_evolution_skill_store (POS: core/skills/store 进化 SQLite 入口)
- app.core.types::ModelConfig

[OUTPUT]
- trigger_skill_evolution: async function to trigger background evolution

[POS]
Business-layer implementation of the Skill Self-Evolution Engine.
Runs asynchronously in the background after a successful agent interaction.
Analyzes the chat history to detect successful complex patterns and automatically
generates reusable SKILL.md definitions, saving them to the local persistent volume.
A full skill library pauses capture and tells the user once per fill-up; only skills the user
can still see (installed, not archived) count toward the limit.
"""

import asyncio
import logging
from collections.abc import Sequence

from myrm_agent_harness.agent.skills.evolution import (
    BudgetCheckResult,
    BudgetStatus,
    EvolutionType,
    SkillBudgetGovernor,
    SkillRecord,
)
from myrm_agent_harness.toolkits.llms import llm_manager

from app.core.types import ModelConfig
from app.services.chat.chat_service import ChatService
from app.services.skills.evolution_events import publish_skill_capacity_reached_event

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

# Agent scopes (``None`` = unscoped) already told that their skill library is full.
# Cleared once capacity frees up, so a library that fills up again is announced again
# instead of repeating the notice on every qualifying turn.
_LIBRARY_FULL_NOTIFIED: set[str | None] = set()


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

        # Auto-merged proposals publish SKILL_EVOLVED; the rest wait in the review queue.
        await ConfidenceApprovalFlow().process_evolution(proposal=proposal)

        logger.info(f"✨ Successfully generated new skill proposal: '{skill_name}' (chat: {chat_id})")

    except Exception as e:
        logger.error(f"Background skill evolution failed for chat {chat_id}: {e}", exc_info=True)


def _count_live_skills(records: Sequence[SkillRecord]) -> int:
    """Count the records whose skill is still installed and not archived."""
    from app.core.skills.curator.service import describe_skill_lifecycle

    live = 0
    for record in records:
        lifecycle = describe_skill_lifecycle(record.name)
        if lifecycle is not None and not lifecycle[0]:
            live += 1
    return live


def check_skill_budget_before_evolution(
    agent_id: str | None = None,
    evolution_type: EvolutionType = EvolutionType.CAPTURED,
    governor: SkillBudgetGovernor | None = None,
) -> BudgetCheckResult:
    """Evaluate whether capacity permits triggering another skill evolution cycle.

    Fails open: when the skill store cannot be read, evolution proceeds rather than stalling.
    """
    gov = governor or SkillBudgetGovernor()
    try:
        from app.core.skills.store.evolution_store import get_evolution_skill_store

        store = get_evolution_skill_store()
        current_count = store.count_active_skills(agent_id=agent_id)
        if current_count >= gov.config.max_skill_count:
            # Deleting or archiving a skill never touches the evolution store, so its record
            # keeps counting. Before declaring the library full, count only skills the user
            # can still see; otherwise freeing space would never resume learning.
            current_count = _count_live_skills(store.get_active_skills(agent_id=agent_id))
        return gov.check_budget(evolution_type=evolution_type, current_count=current_count)
    except Exception as exc:
        logger.warning("Skill capacity check skipped (fail-open): %s", exc)
        return BudgetCheckResult(
            allowed=True,
            status=BudgetStatus.NORMAL,
            current_count=0,
            max_count=gov.config.max_skill_count,
            message="Check skipped",
        )


def _notify_library_full_once(agent_id: str | None, budget_check: BudgetCheckResult) -> None:
    """Tell the user their skill library is full, at most once per fill-up of an agent scope."""
    if agent_id in _LIBRARY_FULL_NOTIFIED:
        return
    _LIBRARY_FULL_NOTIFIED.add(agent_id)
    publish_skill_capacity_reached_event(
        agent_id=agent_id,
        current_count=budget_check.current_count,
        max_count=budget_check.max_count,
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
        _notify_library_full_once(agent_id, budget_check)
        return
    _LIBRARY_FULL_NOTIFIED.discard(agent_id)

    task = asyncio.create_task(
        _run_evolution_task(chat_id, model_cfg, conversation_text=conversation_text, agent_id=agent_id),
        name=f"skill_evolution_{chat_id}",
    )
    _RUNNING_EVOLUTION_TASKS[chat_id] = task
    # A completed task must not block a later evolution of the same chat.
    task.add_done_callback(lambda _t: _RUNNING_EVOLUTION_TASKS.pop(chat_id, None))
    logger.debug(f"Triggered background skill evolution for chat {chat_id}")
