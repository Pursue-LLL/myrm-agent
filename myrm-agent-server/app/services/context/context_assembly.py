"""Context assembly for agent runs.

[INPUT]
- myrm_agent_harness.toolkits.context_bundle::ContextBundleFacade (POS: unified context volume facade)
- app.core.memory.adapters.setup::resolve_context_binding (POS: context binding resolver)
- app.core.memory.adapters.types::ResolvedContextBinding (POS: context runtime binding)

[OUTPUT]
- ContextAssembly: facade + optional binding for a single agent run
- ContextAssemblyService: builds facade and binding from runtime inputs
- ChatMemoryBindingContext: chat-scoped memory binding for manual retry paths
- ContextAssemblyService.resolve_binding_for_chat: binding aligned with agent factory/converter

[POS]
Server-side single entry for context volume and binding before tool assembly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.context_bundle import (
    ContextBundleFacade,
    ContextBundleSpec,
)

from app.config.settings import settings
from app.core.memory.adapters.setup import resolve_context_binding
from app.core.memory.adapters.types import ResolvedContextBinding

if TYPE_CHECKING:
    from app.ai_agents.general_agent.agent import GeneralAgent


@dataclass(frozen=True, slots=True)
class ContextAssembly:
    facade: ContextBundleFacade
    binding: ResolvedContextBinding | None


@dataclass(frozen=True, slots=True)
class ChatMemoryBindingContext:
    """Memory binding resolved from chat metadata (manual extract retry SSOT)."""

    binding: ResolvedContextBinding
    agent_id: str
    memory_decay_profile: str | None = None


class ContextAssemblyService:
    """Build ContextBundle facade and binding for agent factory runs."""

    @staticmethod
    def build_facade(*, ensure_layout: bool = False) -> ContextBundleFacade:
        return ContextBundleFacade.from_state_dir(
            settings.database.state_dir,
            spec=ContextBundleSpec(),
            ensure_layout=ensure_layout,
        )

    @staticmethod
    def resolve_for_agent(
        agent: GeneralAgent,
        effective_chat_id: str,
        *,
        enable_memory: bool,
    ) -> ContextAssembly:
        facade = ContextAssemblyService.build_facade(ensure_layout=False)
        binding: ResolvedContextBinding | None = None
        if enable_memory:
            task_root = (
                agent.declared_allowed_roots[0]
                if agent.declared_allowed_roots
                else None
            )
            binding = resolve_context_binding(
                namespaces=None,
                agent_id=agent.agent_id or "default",
                channel_id=agent.memory_channel_id or agent.channel_name,
                conversation_id=agent.memory_conversation_id or effective_chat_id,
                task_id=agent.memory_task_id,
                shared_context_ids=agent.memory_shared_context_ids,
                memory_policy=agent.memory_policy,
                task_workspace_root=task_root,
            )
        return ContextAssembly(facade=facade, binding=binding)

    @staticmethod
    async def resolve_binding_for_chat(chat_id: str) -> ChatMemoryBindingContext:
        """Resolve memory binding for a chat (same contract as resolve_for_agent)."""
        from app.services.chat.chat_service import ChatService
        from app.services.memory.shared_context import resolve_shared_context_ids

        resolved_chat_id = chat_id.strip()
        if not resolved_chat_id:
            raise ValueError("Chat id is required")

        chat = await ChatService.get_chat_metadata(resolved_chat_id)
        if chat is None:
            raise ValueError("Chat not found")

        agent_id = chat.agent_id or "default"
        memory_policy = None
        memory_decay_profile: str | None = None

        if chat.agent_id:
            from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

            profile = await get_agent_profile_resolver().resolve(chat.agent_id)
            if profile is not None:
                memory_policy = profile.memory_policy
                memory_decay_profile = profile.memory_decay_profile

        shared_context_ids = await resolve_shared_context_ids(
            agent_id=chat.agent_id,
            channel_id="web_chat",
            conversation_id=chat.id,
            project_id=chat.project_id,
        )

        task_workspace_root = chat.workspace_dir or chat.sandbox_base_dir

        binding = resolve_context_binding(
            namespaces=None,
            agent_id=agent_id,
            channel_id="web_chat",
            conversation_id=chat.id,
            task_id=None,
            shared_context_ids=shared_context_ids,
            memory_policy=memory_policy,
            task_workspace_root=task_workspace_root,
        )
        return ChatMemoryBindingContext(
            binding=binding,
            agent_id=agent_id,
            memory_decay_profile=memory_decay_profile,
        )
