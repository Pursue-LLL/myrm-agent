"""Context Guard Service — Gateway & Ingress defense against context bomb payloads.

[INPUT]
- myrm_agent_harness.agent.context_guard::SpilloverEngine, ContextGuardConfig (POS: pure framework engine)
- app.services.chat.effective_workspace::resolve_effective_chat_workspace (POS: chat sandbox workspace resolution)
- app.services.chat.chat_service::ChatService (POS: chat metadata lookup)

[OUTPUT]
- ContextGuardService: service wrapper for protecting agent ingress and streaming pipelines
- guard_inbound_prompt: transparently spill oversized prompts to sandbox workspace
- sweep_expired_transient_spillover: housekeeping helper for periodic cleanup

[POS]
Integrates harness ContextGuard with server session workspace paths and background housekeeping.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.context_guard.spillover_engine import SpilloverEngine
from myrm_agent_harness.agent.context_guard.sweeper import EphemeralTransientSweeper
from myrm_agent_harness.agent.context_guard.types import (
    ContextGuardConfig,
    SpilloverResult,
)

if TYPE_CHECKING:
    from app.services.agent.params import AgentRequest

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
        """Evaluate raw prompt and transparently spill to chat workspace if over threshold."""
        base_dir = await cls._resolve_base_dir(chat_id)
        return cls._engine.process_content(
            raw_prompt,
            base_dir=base_dir,
            role=role,
            custom_prefix=custom_prefix,
            session_id=chat_id,
        )

    @classmethod
    async def _resolve_base_dir(cls, chat_id: str | None) -> Path:
        """Resolve sandboxed workspace directory for chat or fallback to global temp/workspace."""
        if chat_id:
            try:
                from app.services.chat.chat_service import ChatService
                from app.services.chat.effective_workspace import (
                    resolve_effective_chat_workspace,
                )

                chat_meta = await ChatService.get_chat_metadata(chat_id)
                if chat_meta:
                    workspace = await resolve_effective_chat_workspace(
                        chat_meta,
                        jit_fallback=True,
                    )
                    if workspace:
                        return Path(workspace)
            except Exception as exc:
                logger.warning("Failed resolving effective workspace for chat_id=%s: %s", chat_id, exc)

        from app.config.settings import settings

        fallback_dir = Path(getattr(settings, "workspace_base_dir", "/tmp/myrm_workspaces"))
        if chat_id:
            return fallback_dir / f"chat_{chat_id}"
        return fallback_dir / "default"

    @classmethod
    def sweep_all_workspaces(cls, root_dir: Path | str | None = None) -> int:
        """Run housekeeping sweep on workspace directories to purge expired spillover files."""
        if root_dir is None:
            from app.config.settings import settings

            root_dir = getattr(settings, "workspace_base_dir", "/tmp/myrm_workspaces")

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
