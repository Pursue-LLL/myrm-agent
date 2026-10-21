"""Context Guard Service — Gateway & Ingress defense against context bomb payloads.

[INPUT]
- myrm_agent_harness.agent.context_guard::SpilloverEngine, ContextGuardConfig (POS: pure framework engine)
- app.services.chat.effective_workspace::resolve_effective_chat_workspace (POS: chat sandbox workspace resolution)
- app.services.agent.params.workspace_resolve::default_chat_workspace_path, default_workspaces_root
  (POS: JIT chat workspace locations)
- app.services.chat.chat_service::ChatService (POS: chat metadata lookup)
- app.core.utils.skill_invocation::decorate_behind_skill_tag (POS: keeps a leading ``[use skill]`` tag first)

[OUTPUT]
- ContextGuardService: service wrapper for protecting agent ingress and streaming pipelines
- guard_inbound_prompt: transparently spill oversized prompts into the workspace the agent runs in,
  leaving an explicit skill invocation in front of the reference
- sweep_all_workspaces: housekeeping that purges expired spillover files from the chat workspaces

[POS]
Integrates harness ContextGuard with server session workspace paths and background housekeeping.
The spill target is always the directory the agent's file tools resolve relative paths against;
a file anywhere else would hide the user's prompt from the model.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from myrm_agent_harness.agent.context_guard.spillover_engine import SpilloverEngine
from myrm_agent_harness.agent.context_guard.sweeper import EphemeralTransientSweeper
from myrm_agent_harness.agent.context_guard.types import (
    SpilloverResult,
    estimate_token_pressure,
)

from app.core.utils.skill_invocation import decorate_behind_skill_tag

logger = logging.getLogger(__name__)


class ContextGuardService:
    """Server-side coordinator for Context Guard and transparent file spillover."""

    _engine: SpilloverEngine = SpilloverEngine()
    _sweeper: EphemeralTransientSweeper = EphemeralTransientSweeper()

    @classmethod
    def get_engine(cls) -> SpilloverEngine:
        return cls._engine

    @classmethod
    def get_sweeper(cls) -> EphemeralTransientSweeper:
        return cls._sweeper

    @classmethod
    async def guard_inbound_prompt(
        cls,
        *,
        chat_id: str | None,
        raw_prompt: str,
        role: str = "user",
        custom_prefix: str = "payload",
    ) -> SpilloverResult:
        """Evaluate raw prompt and transparently spill to the chat workspace if over threshold.

        Without a workspace the agent can read, nothing is written: the prompt stays intact and the
        gateway size backstop applies, rather than replacing it with a reference the model cannot follow.
        A leading ``[use skill]`` tag stays in front of the reference so the invocation still counts.
        """
        base_dir = await cls._resolve_base_dir(chat_id)
        if base_dir is None:
            return SpilloverResult(
                spilled=False,
                sanitized_content=raw_prompt,
                original_char_count=len(raw_prompt),
                estimated_tokens=estimate_token_pressure(raw_prompt),
            )
        result = cls._engine.process_content(
            raw_prompt,
            base_dir=base_dir,
            role=role,
            custom_prefix=custom_prefix,
            session_id=chat_id,
        )
        if not result.spilled:
            return result
        reference = result.sanitized_content
        return replace(
            result,
            sanitized_content=decorate_behind_skill_tag(raw_prompt, lambda _user_text: reference),
        )

    @classmethod
    async def _resolve_base_dir(cls, chat_id: str | None) -> Path | None:
        """Workspace directory the agent runs in for this chat, or None when there is none to use."""
        if not chat_id:
            return None
        try:
            from app.services.agent.params.workspace_resolve import default_chat_workspace_path
            from app.services.chat.chat_service import ChatService
            from app.services.chat.effective_workspace import resolve_effective_chat_workspace

            chat_meta = await ChatService.get_chat_metadata(chat_id)
            if chat_meta is None:
                # A new chat has no row until its first assistant output (lazy session gate);
                # the agent will run in its JIT sandbox workspace.
                return default_chat_workspace_path(chat_id)
            workspace = await resolve_effective_chat_workspace(chat_meta, jit_fallback=True)
            return Path(workspace) if workspace else None
        except Exception as exc:
            logger.warning("Failed resolving workspace for chat_id=%r: %s", chat_id, exc)
            return None

    @classmethod
    def sweep_all_workspaces(cls, root_dir: Path | str | None = None) -> int:
        """Run housekeeping sweep on workspace directories to purge expired spillover files."""
        if root_dir is None:
            from app.services.agent.params.workspace_resolve import default_workspaces_root

            root_dir = default_workspaces_root()

        root_path = Path(root_dir).expanduser().resolve()
        if not root_path.exists() or not root_path.is_dir():
            return 0

        total_cleaned = 0
        try:
            # Sweep root itself
            total_cleaned += cls._sweeper.sweep_directory(root_path)

            # Sweep immediate subdirectories (e.g. chat_* or project workspaces)
            for sub in root_path.iterdir():
                if sub.is_dir() and not sub.is_symlink():
                    total_cleaned += cls._sweeper.sweep_directory(sub)
        except OSError as err:
            logger.warning("Error during ContextGuard workspace sweep: %s", err)

        if total_cleaned > 0:
            logger.info("ContextGuard housekeeping completed: cleaned %d expired spillover files", total_cleaned)
        return total_cleaned
