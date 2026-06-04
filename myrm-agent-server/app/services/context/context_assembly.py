"""Context assembly for agent runs.

[INPUT]
- myrm_agent_harness.toolkits.context::ContextBundleFacade (POS: unified context volume facade)
- app.core.memory.adapters.setup::resolve_context_binding (POS: context binding resolver)
- app.core.memory.adapters.types::ResolvedContextBinding (POS: context runtime binding)

[OUTPUT]
- ContextAssembly: facade + optional binding for a single agent run
- ContextAssemblyService: builds facade and binding from runtime inputs

[POS]
Server-side single entry for context volume and binding before tool assembly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.context import ContextBundleFacade, ContextBundleSpec

from app.config.settings import settings
from app.core.memory.adapters.setup import resolve_context_binding
from app.core.memory.adapters.types import ResolvedContextBinding

if TYPE_CHECKING:
    from app.ai_agents.general_agent.agent import GeneralAgent


@dataclass(frozen=True, slots=True)
class ContextAssembly:
    facade: ContextBundleFacade
    binding: ResolvedContextBinding | None


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
            task_root = agent.declared_allowed_roots[0] if agent.declared_allowed_roots else None
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
