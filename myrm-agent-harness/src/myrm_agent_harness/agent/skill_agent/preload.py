"""SkillAgent explicit [use skill] preload mixin.

[OUTPUT]
- SkillAgentPreloadMixin._preload_explicit_skill(): (query, primary_skill, preloaded_skills)
- SkillAgentPreloadMixin._preload_explicit_skill_in_blocks(): the same for a multimodal query (message with attachments)
- SkillAgentPreloadMixin._resolve_resumed_turn_skills(): the skills an interrupted turn was invoked with, for a resume that carries no query

[POS]
Detects the leading [use skill] tag (grammar: skill_reference.parse_use_tag) and pre-injects bundled SOP
content before run(). A skill the user named whose SOP the message cannot carry (unknown name, unreadable
SOP, past the size budget) is named with its reason in a NOTE after the header, so the model knows the SOP
is missing and can load the skill itself or tell the user.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skill_agent.skill_reference import parse_use_tag, resolve_skill_reference
from myrm_agent_harness.backends.skills.types import SkillInstance, SkillMetadata
from myrm_agent_harness.utils.logger_utils import get_agent_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.messages import BaseMessage

    from myrm_agent_harness.agent.types import AgentRuntimeConfig
    from myrm_agent_harness.backends.skills.protocols import SkillBackend
    from myrm_agent_harness.utils.chat_utils import ChatHistoryReq

logger = get_agent_logger(__name__)


def _last_human_text(chat_history: ChatHistoryReq | list[BaseMessage] | None) -> str:
    """Text of the user's most recent message in a chat history ('' when there is none).

    Extension custom messages travel as human messages too; they are not something the user typed.
    """
    from langchain_core.messages import HumanMessage

    from myrm_agent_harness.utils.chat_utils import convert_chat_history_simple, extract_text_content

    for message in reversed(convert_chat_history_simple(chat_history)):
        if isinstance(message, HumanMessage) and not message.additional_kwargs.get("is_custom_message"):
            return extract_text_content(message.content)
    return ""


class SkillAgentPreloadMixin:
    _TOKEN_BUDGET_MAX = 12000
    """Soft cap (in estimated characters) for combined SOP injection to prevent token explosion."""

    config: AgentRuntimeConfig
    skill_backend: SkillBackend | None

    if TYPE_CHECKING:

        async def _get_cached_skills(self) -> list[SkillMetadata]: ...

    async def _resolve_resumed_turn_skills(
        self, chat_history: ChatHistoryReq | list[BaseMessage] | None
    ) -> list[SkillMetadata]:
        """Skills the interrupted turn was explicitly invoked with, for a HITL resume.

        A resume carries no query, so the ``[use ...]`` tag is no longer in front of the agent. It
        is still on the user message that opened the interrupted turn: the last human message of
        the history.
        """
        invocation = parse_use_tag(_last_human_text(chat_history))
        if invocation is None or not self.skill_backend:
            return []
        resolved, _ = self._resolve_referenced_skills(invocation.references, await self._get_cached_skills())
        return resolved

    @staticmethod
    def _resolve_referenced_skills(
        references: Sequence[str], skills: list[SkillMetadata]
    ) -> tuple[list[SkillMetadata], list[str]]:
        """Resolve the ``[use ...]`` references.

        Returns the skills they name, each at most once and in the order typed, and the references that
        name no skill.
        """
        resolved: dict[str, SkillMetadata] = {}
        unresolved: list[str] = []
        for reference in references:
            skill = resolve_skill_reference(reference, skills)
            if skill is None:
                logger.info("Explicit skill '%s' not found in %d skills — skipped", reference, len(skills))
                unresolved.append(reference)
            else:
                resolved.setdefault(skill.name, skill)
        return list(resolved.values()), unresolved

    async def _preload_explicit_skill_in_blocks(
        self, blocks: list[dict[str, object]]
    ) -> tuple[list[dict[str, object]], SkillMetadata | None, list[SkillMetadata]]:
        """``_preload_explicit_skill`` for a multimodal query (a message with attachments).

        The user's own words are the first block; text that comes from attachments follows it. Only the
        first block may carry the tag, so the content of an attachment can never invoke a skill. The
        blocks are never modified in place.
        """
        first = blocks[0] if blocks else None
        if not isinstance(first, dict) or first.get("type") != "text":
            return blocks, None, []
        text = first.get("text")
        if not isinstance(text, str):
            return blocks, None, []
        expanded, primary, preloaded = await self._preload_explicit_skill(text)
        if primary is None:
            return blocks, None, []
        return [{**first, "text": expanded}, *blocks[1:]], primary, preloaded

    async def _preload_explicit_skill(self, query: str) -> tuple[str, SkillMetadata | None, list[SkillMetadata]]:
        """Detect ``[use skill_name]`` or ``[use s1,s2,s3]`` prefix and pre-inject SOP(s).

        Supports both single-skill and multi-skill (bundle) invocation. When multiple
        skill names are comma-separated, all SOPs are merged into a single injection,
        respecting ``_TOKEN_BUDGET_MAX`` to prevent token explosion.

        The ``[instruction: ...]`` suffix in the ``[use ...]`` tag is also supported
        for ephemeral bundle guidance.

        A skill the user named whose SOP the message does not carry (unknown name, unreadable SOP, past
        the budget) is listed with its reason in a NOTE after the header, so the model can load it itself
        or tell the user.

        Returns:
            (modified_query, primary_skill_meta, preloaded_skills) — when no named skill can deliver an
            SOP the query is unchanged and both skill slots are empty.
        """
        invocation = parse_use_tag(query)
        if invocation is None:
            return query, None, []
        skill_names, user_args = invocation.references, invocation.text

        if not self.skill_backend:
            logger.debug("Explicit skill(s) %s requested but no skill_backend", skill_names)
            return query, None, []

        matched, unresolved = self._resolve_referenced_skills(skill_names, await self._get_cached_skills())
        if not matched:
            return query, None, []

        from myrm_agent_harness.agent.meta_tools.skills.select import (
            get_skill_document,
        )

        delivered: list[tuple[SkillMetadata, str]] = []
        skipped = [f"{reference} (not found)" for reference in unresolved]
        total_chars = 0

        for index, skill_meta in enumerate(matched):
            try:
                skill_instance = await self._resolve_skill_instance_for_l1(skill_meta.name)
                sop_doc = await get_skill_document(
                    skill_meta,
                    self.skill_backend,
                    skill_instance=skill_instance,
                )
            except Exception:
                logger.warning("Failed to preload SOP for skill '%s' — skipped", skill_meta.name, exc_info=True)
                skipped.append(f"{skill_meta.name} (could not be read)")
                continue

            if not sop_doc:
                logger.info("No SOP delivered for skill '%s' — skipped", skill_meta.name)
                skipped.append(f"{skill_meta.name} (could not be read)")
                continue

            section_parts = [f"--- Skill: {skill_meta.name} ---", sop_doc]

            if not skill_meta.available:
                reason = skill_meta.unavailable_reason or "dependency requirements not met"
                section_parts.append(f"WARNING: Skill '{skill_meta.name}' is UNAVAILABLE ({reason}).")

            section_text = "\n".join(section_parts)
            if total_chars + len(section_text) > self._TOKEN_BUDGET_MAX and delivered:
                over_budget = [later.name for later in matched[index:]]
                logger.warning(
                    "Token budget exceeded after %d skills (%d chars), skipping %s",
                    len(delivered),
                    total_chars,
                    over_budget,
                )
                skipped.extend(f"{name} (preload size budget reached)" for name in over_budget)
                break

            delivered.append((skill_meta, section_text))
            total_chars += len(section_text)

        if not delivered:
            return query, None, []

        preloaded_skills = [skill_meta for skill_meta, _ in delivered]
        loaded_names = [skill_meta.name for skill_meta in preloaded_skills]
        names_str = ", ".join(loaded_names)

        if len(delivered) > 1:
            header = (
                f"[IMPORTANT: The following {len(delivered)} skills have been preloaded as a bundle: "
                f"{names_str}. Follow ALL their SOP instructions. Do NOT call skill_select_tool "
                f"for these skills — their content is already provided below.]"
            )
        else:
            header = (
                f'[IMPORTANT: The skill "{loaded_names[0]}" has been preloaded by the user. '
                f"Follow its SOP instructions immediately. Do NOT call skill_select_tool "
                f"for this skill — its content is already provided below.]"
            )

        parts = [header]
        if skipped:
            parts.append(self._skipped_skills_note(skipped))
        parts.extend(["", *(section for _, section in delivered)])

        if user_args:
            parts.append("")
            parts.append(user_args)

        logger.info(
            "Preloaded %d skill(s) %s — SOP injected (%d chars), user_args='%s'",
            len(delivered),
            loaded_names,
            total_chars,
            user_args[:80],
        )
        from myrm_agent_harness.backends.skills.usage_recorder import record_skill_selection

        for skill_meta in preloaded_skills:
            record_skill_selection(skill_meta)

        return "\n".join(parts), preloaded_skills[0], preloaded_skills

    def _skipped_skills_note(self, skipped: Sequence[str]) -> str:
        """Tell the model which skills the user named that this message carries no SOP for, and what to do.

        Without the built-in skill tools (``no_builtin_tools``) there is nothing to load a skill with, so the
        note points at the user instead of ``skill_select_tool``.
        """
        what_now = (
            "If the task depends on them, tell the user they were not loaded."
            if self.config.no_builtin_tools
            else "If the task needs one of them, load it with skill_select_tool; if it cannot be loaded, tell the user."
        )
        return (
            f"[NOTE: The user also requested: {', '.join(skipped)}. No SOP was preloaded for these skills. {what_now}]"
        )

    async def _resolve_skill_instance_for_l1(self, skill_name: str) -> SkillInstance | None:
        """Resolve bound SkillInstance for L1 config footer (matches select tool SSOT)."""
        from myrm_agent_harness.backends.skills.types import SkillInstance

        state_manager = getattr(self, "state_manager", None)
        default_instances = getattr(self, "_default_skill_instances", None) or {}
        skill_backend = getattr(self, "skill_backend", None)
        if state_manager is None or not default_instances or skill_backend is None:
            return None
        instance_name = default_instances.get(skill_name)
        if not instance_name:
            return None
        try:
            instance = await state_manager.load_instance(
                backend=skill_backend,
                skill_name=skill_name,
                instance_name=instance_name,
            )
        except Exception:
            logger.debug(
                "Failed to load skill instance %s.%s for L1 footer",
                skill_name,
                instance_name,
                exc_info=True,
            )
            return None
        return instance if isinstance(instance, SkillInstance) else None
