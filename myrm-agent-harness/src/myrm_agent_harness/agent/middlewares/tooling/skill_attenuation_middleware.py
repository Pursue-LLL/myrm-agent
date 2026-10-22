"""Skill attenuation and dynamic tool resolution middleware.

[INPUT]
- agent.tool_management.registry::ToolRegistry (POS: Tool registry)
- agent.middlewares.tooling._skill_tool_choice (POS: Skill attenuation request metadata builder)
- agent.middlewares.tooling._runtime_tool_governance::compute_turn_allowed_names (POS: merged allowlist for model hint + execution enforcement)
- toolkits.llms.allowed_tools_capability::model_supports_allowed_tools_tool_choice (POS: provider capability gate for cache-safe skill attenuation)
- langchain.agents.middleware::AgentMiddleware (POS: Middleware base)
- langgraph.prebuilt.tool_node::ToolCallRequest (POS: Tool execution request for interceptors)

[OUTPUT]
- SkillAttenuationMiddleware: applies skill attenuation via ``tool_choice.allowed_tools``
  when supported, and resolves dynamic tools at ToolNode execution time.

[POS]
Skill attenuation uses per-turn ``tool_choice`` (OpenAI ``allowed_tools`` mode) so the
bound tools prefix stays cache-stable when the provider supports it. Execution-layer
enforcement uses the same turn allowlist via ``check_trust_attenuation``.
``awrap_tool_call`` resolves tools for ToolNode when ``request.tool is None``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares._session_context import (
    set_turn_allowed_tool_names,
)
from myrm_agent_harness.agent.middlewares.tooling._runtime_tool_governance import (
    compute_turn_allowed_names,
)
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry

logger = logging.getLogger(__name__)


class SkillAttenuationMiddleware(AgentMiddleware[AgentState[object], object, object]):
    """Apply skill attenuation and resolve dynamic tools without mutating ``bind_tools``."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def wrap_model_call(
        self,
        request: ModelRequest[object],
        handler: Callable[[ModelRequest[object]], ModelResponse[object]],
    ) -> ModelResponse[object]:
        request = self._apply_turn_tool_policy(request)
        return self._repair_tool_call_names(handler(request), request)

    async def awrap_model_call(
        self,
        request: ModelRequest[object],
        handler: Callable[[ModelRequest[object]], Awaitable[ModelResponse[object]]],
    ) -> ModelResponse[object]:
        request = self._apply_turn_tool_policy(request)
        return self._repair_tool_call_names(await handler(request), request)

    @staticmethod
    def _repair_tool_call_names(
        response: ModelResponse[object],
        request: ModelRequest[object],
    ) -> ModelResponse[object]:
        """Repair a hallucinated tool name before the graph dispatches it.

        The model sometimes guesses the implementation-ish name of a registered tool
        ("a2a_call_tool" for "a2a_call"). LangGraph resolves names against its own map and
        returns "not a valid tool" for anything else, so a turn can burn its whole retry
        budget and end with an empty answer. Repairing names here — while the bound tool
        list is still in hand — keeps the dispatch path untouched.
        """
        from myrm_agent_harness.agent.middlewares.tooling._skill_tool_choice import (
            extract_bound_tool_names,
        )
        from myrm_agent_harness.agent.tool_validation.fuzzy_repair import (
            ToolNameFuzzyRepairer,
        )

        if not request.tools:
            return response
        valid_names = set(extract_bound_tool_names(list(request.tools)))
        if not valid_names:
            return response

        repairer = ToolNameFuzzyRepairer()
        changed = False
        repaired_messages: list[object] = []
        for message in response.result:
            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                repaired_messages.append(message)
                continue
            updated_calls: list[object] = []
            message_changed = False
            for call in tool_calls:
                name = call.get("name") if isinstance(call, dict) else None
                if isinstance(name, str) and name not in valid_names:
                    repaired = repairer.repair_name(name, valid_names)
                    if repaired and repaired != name:
                        call = {**call, "name": repaired}
                        message_changed = True
                        logger.warning("Repaired hallucinated tool name %s -> %s", name, repaired)
                updated_calls.append(call)
            if message_changed:
                changed = True
                repaired_messages.append(message.model_copy(update={"tool_calls": updated_calls}))
            else:
                repaired_messages.append(message)
        if not changed:
            return response
        return response.model_copy(update={"result": repaired_messages})

    def _apply_turn_tool_policy(self, request: ModelRequest[object]) -> ModelRequest[object]:
        from myrm_agent_harness.agent.middlewares.tooling._skill_tool_choice import (
            build_allowed_tools_tool_choice,
            extract_bound_tool_names,
        )
        from myrm_agent_harness.agent.skill_agent.context import get_loaded_skills
        from myrm_agent_harness.toolkits.llms.allowed_tools_capability import (
            model_supports_allowed_tools_tool_choice,
        )

        if not request.tools:
            set_turn_allowed_tool_names(None)
            return request

        tool_names = extract_bound_tool_names(list(request.tools))
        loaded_skills = get_loaded_skills()
        final_allowed = compute_turn_allowed_names(
            tool_names,
            list(request.messages),
            loaded_skills or None,
        )
        set_turn_allowed_tool_names(final_allowed)

        if final_allowed is None:
            return request

        if not final_allowed:
            logger.info(" SkillAttenuationMiddleware block-all turn policy active (execution-layer enforcement only)")
            return request

        llm = getattr(request, "model", None)
        model_name = getattr(llm, "model", None) or getattr(llm, "model_name", None)
        api_base = getattr(llm, "api_base", None)
        model_id = str(model_name) if model_name else None

        if not model_supports_allowed_tools_tool_choice(model_id, api_base=str(api_base or "")):
            logger.info(
                " SkillAttenuationMiddleware skipped allowed_tools model-layer hint "
                "(model=%s); execution-layer policy remains active",
                model_id or "unknown",
            )
            return request

        logger.info(
            " SkillAttenuationMiddleware allowed_tools restricted %d tool(s): %s",
            len(tool_names) - len(final_allowed),
            sorted(set(tool_names) - set(final_allowed)),
        )
        return request.override(
            tool_choice=build_allowed_tools_tool_choice(final_allowed),
        )

    def _resolve_dynamic_tool_request(self, request: ToolCallRequest) -> ToolCallRequest:
        """Resolve dynamic BaseTool instances for ToolNode when not pre-bound."""
        if request.tool is not None:
            return request

        from myrm_agent_harness.agent.middlewares._session_context import (
            get_active_resolved_tools,
            get_active_tool_registry,
        )

        registry = get_active_tool_registry() or self.registry
        resolved_tools = get_active_resolved_tools()

        call_name = str(request.tool_call.get("name", ""))
        candidate_names = {call_name}
        if not call_name.endswith("_tool"):
            candidate_names.add(f"{call_name}_tool")
        else:
            candidate_names.add(call_name.removesuffix("_tool"))

        search_pool: list[object] = []
        if resolved_tools:
            search_pool.extend(resolved_tools)
        search_pool.extend(registry.resolve())
        search_pool.extend(registry.get_runtime_tools())

        seen: set[str] = set()
        for resolved_tool in search_pool:
            name = getattr(resolved_tool, "name", None)
            if not isinstance(name, str) or name in seen:
                continue
            seen.add(name)
            if name in candidate_names:
                return request.override(tool=resolved_tool)

        return request

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[object]],
    ) -> ToolMessage | Command[object]:
        return handler(self._resolve_dynamic_tool_request(request))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
    ) -> ToolMessage | Command[object]:
        """Resolve dynamic BaseTool instances for ToolNode when not pre-bound."""
        return await handler(self._resolve_dynamic_tool_request(request))
