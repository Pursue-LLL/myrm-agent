"""Base Agent — lightweight agent with streaming, token tracking, and artifacts.

Runtime helpers (middleware, tools, guards) live in ``_internals.agent_runtime``.
Recovery strategies (overflow, failover, diagnostics) live in ``_internals.agent_recovery``.
Lifecycle helpers (workspace setup, cleanup, post-processing) live in ``_internals.run_lifecycle``.
Child-agent management (spawn, observe, cancel, steer, wake up) lives in ``_internals.base_agent_children_mixin``.

[INPUT]
- utils.chat_utils::ChatHistoryReq (POS: chat history types; ChatHistoryReq is the list of [role, content] entries passed in as history)
- toolkits.code_execution.executors.base::CodeExecutor (POS: Code executor base classes.)
- utils.runtime.cancellation::CancellationToken (POS: request-level cancellation token for cooperative async cancellation)
- utils.runtime.steering::SteeringToken (POS: steering token: injects a message while the agent runs to interrupt the current tool chain)
- agent._internals.base_agent_children_mixin::BaseAgentChildrenMixin (POS: Mixin: the child-agent management methods of BaseAgent; every call delegates to the agent's SubagentManager.)
- agent._internals.base_agent_modes_mixin::BaseAgentModesMixin (POS: Mixin: run_consensus on BaseAgent.)

[OUTPUT]
- BaseAgent: Lightweight agent base class with streaming events, token tracking, and artifacts.

[POS]
Base Agent — lightweight agent with streaming, token tracking, and artifacts.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.types import Command

from myrm_agent_harness.agent.event_log.protocols import EventLogBackend
from myrm_agent_harness.agent.tool_management import ToolRegistry
from myrm_agent_harness.utils.chat_utils import ChatHistoryReq
from myrm_agent_harness.utils.logger_utils import get_agent_logger

from ._internals.base_agent_children_mixin import BaseAgentChildrenMixin
from ._internals.base_agent_modes_mixin import BaseAgentModesMixin
from .streaming.agent_core_rules import AGENT_CORE_RULES
from .streaming.channel_output_hints import resolve_channel_output_hint
from .streaming.utils import DATETIME_SYSTEM_RULES
from .sub_agents.manager import SubagentManager
from .types import AgentRunStatistics, AgentRuntimeConfig

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware
    from langchain.agents.middleware.types import AgentState, InputAgentState, OutputAgentState
    from langchain_core.messages import BaseMessage
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

    from myrm_agent_harness.agent.extensions.protocols import AgentExtension
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
    from myrm_agent_harness.utils.runtime.steering import SteeringToken
    from myrm_agent_harness.utils.token_economics.budget_guard import BudgetChecker

    _AgentGraph = CompiledStateGraph[AgentState[object], None, InputAgentState, OutputAgentState[object]]

logger = get_agent_logger(__name__)


class BaseAgent(BaseAgentModesMixin, BaseAgentChildrenMixin):
    """Lightweight agent base class with streaming events, token tracking, and artifacts.

    Template-method hooks for subclass customization:
    ``_build_middlewares``, ``_build_tools``, ``_prepare_context``.
    """

    ArtifactReadyHandler = Callable[[dict[str, object]], Awaitable[dict[str, object] | None]]

    def __init__(
        self,
        llm: BaseChatModel,
        executor: CodeExecutor | None = None,
        middlewares: list[AgentMiddleware[Any, Any]] | None = None,
        system_prompt: str | None = None,
        tools: list[BaseTool] | None = None,
        context_schema: type | None = None,
        config: AgentRuntimeConfig | None = None,
        on_artifacts_ready: ArtifactReadyHandler | None = None,
        fallback_llm: BaseChatModel | None = None,
        fallback_llms: list[BaseChatModel] | None = None,
        safety_fallback_llm: BaseChatModel | None = None,
        checkpointer: BaseCheckpointSaver[str] | None = None,
        event_log_backend: EventLogBackend | None = None,
        model_resolver: object | None = None,
    ) -> None:
        self.llm = llm
        self.fallback_llms: list[BaseChatModel] = (
            list(fallback_llms) if fallback_llms is not None else ([fallback_llm] if fallback_llm is not None else [])
        )
        self.fallback_llm = self.fallback_llms[0] if self.fallback_llms else fallback_llm
        self.safety_fallback_llm = safety_fallback_llm
        self.executor = executor
        self.user_middlewares = middlewares or []
        self.system_prompt = system_prompt
        self.user_tools = tools or []
        self.context_schema = context_schema
        self.config = config or AgentRuntimeConfig()
        self.on_artifacts_ready = on_artifacts_ready
        self.checkpointer = checkpointer
        self.event_log_backend = event_log_backend
        self.model_resolver = model_resolver
        self._agent: _AgentGraph | None = None
        self._cached_tools: list[BaseTool] | None = None
        self._cached_system_prompt: str | None = None
        self._cached_middlewares: list[AgentMiddleware[Any, Any]] | None = None
        self._failover_used = False
        self._last_run_stats: AgentRunStatistics | None = None
        self._last_context: dict[str, object] = {}
        self._subagent_manager = SubagentManager(self)
        self._is_running = False
        self._extensions: list[AgentExtension] = []
        self.budget_checker: BudgetChecker | None = None

        # Tool lifecycle management
        from myrm_agent_harness.agent.tool_management import ToolLifecycleManager

        self._lifecycle_manager = ToolLifecycleManager()
        self._tools_initialized = False
        self._tool_registry = self._create_registry()

        from myrm_agent_harness.agent.context_management.preheat import (
            CacheKeepAliveManager,
        )

        self._cache_keepalive: CacheKeepAliveManager | None = None

    def register_extension(self, ext: AgentExtension) -> None:
        """Register an AgentExtension. Must be called before the first ``run()``.

        Raises ``ValueError`` if an extension with the same name is already registered,
        or if the agent graph has already been built (``_ensure_initialized`` was called).
        """
        if self._agent is not None:
            raise ValueError(
                f"Cannot register extension '{ext.name}' after agent initialization. "
                "Call register_extension() before the first run()."
            )
        existing_names = {e.name for e in self._extensions}
        if ext.name in existing_names:
            raise ValueError(f"Extension name conflict: '{ext.name}' is already registered.")
        self._extensions.append(ext)

    async def _ensure_initialized(self) -> None:
        if self._agent is not None:
            return

        # 10/10 Scheme: If system_prompt is explicitly empty string (""), we are in FORK context mode.
        # We must NOT append DATETIME_SYSTEM_RULES to prevent creating a new SystemMessage that breaks Prefix Cache.
        if self.system_prompt == "":
            self._cached_system_prompt = None
        else:
            from myrm_agent_harness.agent.middlewares._session_context import (
                set_canary_token,
            )
            from myrm_agent_harness.agent.security.detection.canary_guard import generate_canary

            # The token reaches the model through CanaryMiddleware, behind the user's input; a per-session token
            # in this prompt would end the prefix a provider shares across sessions at the token.
            set_canary_token(generate_canary())

            self._cached_system_prompt = (
                (self.system_prompt or "")
                + DATETIME_SYSTEM_RULES
                + AGENT_CORE_RULES
                + resolve_channel_output_hint(self.config.channel_name)
            )

        self._cached_middlewares = self._build_middlewares()
        self._cached_tools = await self._build_tools()

        from myrm_agent_harness.agent.tool_management.types import ToolSource

        for ext in self._extensions:
            ext_tools = ext.get_tools()
            if ext_tools:
                for tool in ext_tools:
                    self._tool_registry.register(tool, source=ToolSource.USER)
            ext_mws = ext.get_middlewares()
            if ext_mws:
                self._cached_middlewares.extend(ext_mws)

        for ext in self._extensions:
            try:
                await ext.on_agent_init(self)
            except Exception:
                logger.exception("Extension '%s' on_agent_init failed", ext.name)

        from myrm_agent_harness.agent._internals._agent_build import (
            _weave_dynamic_schemas,
        )

        no_builtin = self.config.no_builtin_tools
        self._cached_tools = _weave_dynamic_schemas(self._tool_registry.resolve(no_builtin_tools=no_builtin))

        if self._extensions:
            from myrm_agent_harness.agent.tool_management.tool_layers import (
                get_tool_layer,
                get_tool_registry_sort_key,
            )

            self._cached_tools.sort(key=lambda t: get_tool_registry_sort_key(t.name, get_tool_layer(t.name)))

        logger.debug("BaseAgent: final tools=%s", [t.name for t in self._cached_tools])

        from myrm_agent_harness.agent.middlewares._session_context import (
            set_active_resolved_tools,
            set_active_tool_registry,
        )

        set_active_tool_registry(self._tool_registry)
        set_active_resolved_tools(self._cached_tools)

        self._agent = create_agent(
            model=self.llm,
            tools=self._cached_tools,
            system_prompt=self._cached_system_prompt,
            middleware=self._cached_middlewares,
            context_schema=self.context_schema,
            checkpointer=self.checkpointer,
        )

        # Fire-and-forget: pre-warm Anthropic/Qwen server-side prefix cache
        # while the user is still typing their first message.
        from myrm_agent_harness.agent.context_management.preheat import (
            CacheKeepAliveManager,
            needs_explicit_preheat,
            schedule_init_preheat,
        )

        model_name = getattr(self.llm, "model_name", "") or getattr(self.llm, "model", "") or ""
        schedule_init_preheat(self.llm, self._cached_system_prompt, model_name)

        if self._cached_system_prompt and needs_explicit_preheat(model_name):
            self._cache_keepalive = CacheKeepAliveManager(self.llm, self._cached_system_prompt, model_name)
            self._cache_keepalive.start()

    def _rebuild_agent_with_llm(self, new_llm: BaseChatModel) -> CompiledStateGraph[Any, Any, Any, Any]:
        """Rebuild agent graph with a different LLM for failover.

        Returns the newly compiled graph so the active stream
        (StreamContext.agent) can be re-bound to it after failover.
        """
        from ._internals.agent_recovery import rebuild_agent_with_llm

        return rebuild_agent_with_llm(self, new_llm)

    def add_tools(self, tools: list[BaseTool]) -> None:
        """Register tools on the registry and rebuild the agent graph when already initialized.

        During ``_ensure_initialized`` (before the first ``create_agent``), this only registers
        tools; the graph is built once after all extensions finish ``on_agent_init``.

        After initialization, this registers tools and rebuilds the agent graph immediately.

        Note:
            If any of the new tools are lifecycle-aware (have ainit/acleanup),
            they will be initialized on the next run() call.
        """
        from myrm_agent_harness.agent.streaming.utils import normalize_tool_names
        from myrm_agent_harness.agent.tool_management.tool_layers import (
            get_tool_layer,
            get_tool_registry_sort_key,
        )
        from myrm_agent_harness.agent.tool_management.types import ToolSource

        normalized = normalize_tool_names(tools)
        for tool in normalized:
            self._tool_registry.register(tool, source=ToolSource.USER)

        def sort_key(t: BaseTool) -> tuple[int, int, str]:
            return get_tool_registry_sort_key(t.name, get_tool_layer(t.name))

        if self._agent is None:
            if self._cached_tools is None:
                self.user_tools.extend(normalized)
                self.user_tools.sort(key=sort_key)
            else:
                self._cached_tools.extend(normalized)
                self._cached_tools.sort(key=sort_key)
            return

        assert self._cached_tools is not None  # the tool list is built before the agent graph
        self._cached_tools.extend(normalized)
        # Enforce cache tiering: sort tools by ToolLayer to protect prompt cache prefixes
        self._cached_tools.sort(key=sort_key)

        # Mark tools as needing re-initialization (lifecycle-aware tools will be init'd on next run)
        # LifecycleManager.initialize_tools() is idempotent (skips already-initialized tools)
        self._tools_initialized = False

        self._agent = create_agent(
            model=self.llm,
            tools=self._cached_tools,
            system_prompt=self._cached_system_prompt,
            middleware=cast(list["AgentMiddleware[Any, Any]"], self._cached_middlewares),
            context_schema=self.context_schema,
            checkpointer=self.checkpointer,
        )

    @staticmethod
    def _init_usage_ledger(context: dict[str, object] | None) -> None:
        """Attach a UsageLedger to the current request scope."""
        from ._internals.agent_runtime import init_usage_ledger

        init_usage_ledger(context)

    def _build_middlewares(self) -> list[Any]:
        """Build the middleware chain. Override in subclasses for customization."""
        from ._internals.agent_runtime import build_middlewares

        return build_middlewares(self._tool_registry, self.user_middlewares, self.config.engine_params)

    def _create_registry(self) -> ToolRegistry:
        """Create a fresh ToolRegistry for this build cycle."""
        from ._internals.agent_runtime import create_registry

        return create_registry()

    def _emit_tools_snapshot(self) -> list[dict[str, object]] | None:
        """Serializable snapshot of the Turn1-bound tools the model can call, for the GUI availability view."""
        from ._internals.agent_runtime import emit_tools_snapshot

        return emit_tools_snapshot(self._tool_registry, no_builtin_tools=self.config.no_builtin_tools)

    async def _build_tools(self) -> list[BaseTool]:
        """Build tool list via ToolRegistry (user + middleware sources)."""
        from ._internals.agent_runtime import build_tools

        return await build_tools(
            self._tool_registry,
            self.user_tools,
            self._cached_middlewares,
        )

    @property
    def is_initialized(self) -> bool:
        return self._agent is not None

    @property
    def last_run_stats(self) -> AgentRunStatistics | None:
        return self._last_run_stats

    async def run(
        self,
        query: str | list[dict[str, Any]] | Command[Any],
        chat_history: ChatHistoryReq | list[BaseMessage] | None = None,
        message_id: str | None = None,
        context: dict[str, Any] | None = None,
        cancel_token: CancellationToken | None = None,
        steering_token: SteeringToken | None = None,
        timezone: str | None = None,
    ) -> AsyncGenerator[dict[str, object]]:
        """Stream agent events. Supports normal query and Command(resume=...) modes."""
        from myrm_agent_harness.agent.errors.agent_errors import AgentBusyError

        if self._is_running:
            raise AgentBusyError("Agent is already running a task. Please wait for it to complete.")

        self._is_running = True

        from myrm_agent_harness.infra.tracing.gen_ai import AgentRunSpan

        try:
            agent_span = AgentRunSpan(
                agent_type=type(self).__name__,
                query=query,
                context_values=context,
                message_id=message_id,
            )
            try:
                async for event in agent_span.scope(
                    self._run_internal(
                        query=query,
                        chat_history=chat_history,
                        message_id=message_id,
                        context=context,
                        cancel_token=cancel_token,
                        steering_token=steering_token,
                        timezone=timezone,
                    )
                ):
                    yield event
            finally:
                agent_span.end()
        finally:
            self._is_running = False
            if self._cache_keepalive is not None:
                self._cache_keepalive.touch()

    async def _run_internal(
        self,
        query: str | list[dict[str, Any]] | Command[Any],
        chat_history: ChatHistoryReq | list[BaseMessage] | None = None,
        message_id: str | None = None,
        context: dict[str, Any] | None = None,
        cancel_token: CancellationToken | None = None,
        steering_token: SteeringToken | None = None,
        timezone: str | None = None,
    ) -> AsyncGenerator[dict[str, object]]:
        """Core execution loop. Delegates to ``_internals.agent_runtime.run_agent_loop``."""
        await self._ensure_initialized()

        from ._internals.agent_runtime import run_agent_loop

        async for event in run_agent_loop(
            agent_state=self,
            query=query,
            chat_history=chat_history,
            message_id=message_id or "",  # ``run_agent_loop`` mints an id for an empty one
            context=context,
            cancel_token=cancel_token,
            steering_token=steering_token,
            timezone=timezone,
        ):
            yield event

    async def _setup_workspace(self, context: dict[str, object] | None, message_id: str) -> dict[str, object]:
        """Create workspace, bind executor, and set context vars."""
        from ._internals.run_lifecycle import setup_workspace

        merged_ctx, _ = await setup_workspace(self.executor, context)
        return merged_ctx

    async def _prepare_context(self, context: dict[str, object]) -> dict[str, object]:
        """Hook for subclasses to enrich context (e.g. skill paths). No-op by default."""
        return context

    async def get_checkpoint_state(self, thread_id: str) -> dict[str, object]:
        """Extract complete execution state for checkpoint save.

        Delegates to ``sub_agents.checkpoint.state_snapshot.extract_checkpoint_state``.
        """
        from .sub_agents.checkpoint.state_snapshot import extract_checkpoint_state

        return await extract_checkpoint_state(
            checkpointer=self.checkpointer,
            last_context=self._last_context,
            last_run_stats=self._last_run_stats,
            thread_id=thread_id,
        )

    async def cleanup_tools(self) -> None:
        """Cleanup all lifecycle-aware tools.

        This method should be called when the agent is being terminated to properly
        release resources (e.g., close database connections, stop file watchers).

        Note:
            - This is best-effort: cleanup failures are logged but don't raise
            - Safe to call multiple times (idempotent)
            - Automatically called by Business/Control Plane layers on agent termination

        Usage (Business layer):
            try:
                async for event in agent.run(query, context=...):
                    yield event
            finally:
                await agent.cleanup_tools()
        """
        if self._cache_keepalive is not None:
            self._cache_keepalive.stop()
            self._cache_keepalive = None

        for ext in self._extensions:
            try:
                await ext.on_agent_shutdown(self)
            except Exception:
                logger.exception("Extension '%s' on_agent_shutdown failed", ext.name)
        if self._cached_tools:
            await self._lifecycle_manager.cleanup_tools(self._cached_tools)
