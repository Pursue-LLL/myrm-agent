"""Context Guard Service — Gateway & Ingress defense against context bomb payloads.

[INPUT]
- myrm_agent_harness.agent.context_guard::EphemeralTransientSweeper (POS: TTL sweeper of transient spill files)
- app.services.chat.context_bomb_guard::ContextBombDefenseService (POS: parks an oversized text in a workspace file)
- app.services.chat.effective_workspace::resolve_effective_chat_workspace (POS: chat sandbox workspace resolution)
- app.services.agent.params.workspace_resolve::default_chat_workspace_path, default_workspaces_root
  (POS: JIT chat workspace locations)
- app.services.chat.chat_service::ChatService (POS: chat metadata lookup)

[OUTPUT]
- ContextGuardService: service wrapper for protecting agent ingress and streaming pipelines
- guard_inbound_prompt: park an oversized prompt in the workspace the agent runs in (kept with the workspace, the
  same file and stub the stored message gets), leaving an explicit skill invocation in front of the stub
- sweep_all_workspaces: housekeeping that purges expired transient spill files from the chat workspaces

[POS]
Integrates the context guard with server session workspace paths and background housekeeping.
The spill target is always the directory the agent's file tools resolve relative paths against;
a file anywhere else would hide the user's prompt from the model. The prompt a run starts from is
kept in the agent's thread and replayed on later turns, so its file must outlive the turn: only
transient files (a channel document) are ever swept.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from myrm_agent_harness.agent.context_guard import EphemeralTransientSweeper

from app.services.chat.context_bomb_guard import ContextBombDefenseService, SpilloverPayloadResult

logger = logging.getLogger(__name__)


class ContextGuardService:
    """Server-side coordinator for Context Guard and transparent file spillover."""

    _sweeper: EphemeralTransientSweeper = EphemeralTransientSweeper()

    @classmethod
    async def guard_inbound_prompt(cls, *, chat_id: str | None, raw_prompt: str) -> SpilloverPayloadResult:
        """Park the raw prompt in the chat workspace if it is over the threshold.

        Without a workspace the agent can read, nothing is written: the prompt stays intact and the
        gateway size backstop applies, rather than replacing it with a reference the model cannot follow.
        A leading ``[use skill]`` tag stays in front of the reference so the invocation still counts.
        """
        if not ContextBombDefenseService.is_oversized(raw_prompt):
            return SpilloverPayloadResult.intact(raw_prompt)
        base_dir = await cls._resolve_base_dir(chat_id)
        # The guard writes the file; keep that I/O off the event loop.
        return await asyncio.to_thread(
            ContextBombDefenseService.process_incoming_content, raw_prompt, workspace_root=base_dir, kept=True
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
