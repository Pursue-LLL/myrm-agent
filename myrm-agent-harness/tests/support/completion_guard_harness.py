"""Drive the completion guard the way a run does: one hook call, the built middleware chain, the whole agent.

[INPUT]
- myrm_agent_harness.agent.middlewares.completion.completion_guard::CompletionGuard (POS: the guard under test)
- myrm_agent_harness.agent._internals._agent_build::build_middlewares (POS: where the guard's capability probes are wired from the mounted tools)
- myrm_agent_harness.agent._factory.builder::create_skill_agent (POS: the real tool assembly and run loop)

[OUTPUT]
- CHECK_MARK: the text every guard rejection starts with in the request the model reads
- state / runtime / verdict: one ``aafter_model`` call for a request and a scripted answer
- stamped: the messages as the graph state holds them, each with the id the state reducer gives every stored message
- GUARD_DECISIONS: the reasons of every answer the guard held back since the current test began (filled by the middleware conftest)
- pending / reasons_of / directive_of: the instruction a rejecting verdict leaves for the model, the reasons it answers, and its text
- registry_of / named_tool / built_guard: the guard of the chain ``build_middlewares`` assembles over a registry of mounted tools
- writes_allowed / writes_denied: a policy that lets a run write files, and one with the Read Only profile's deny set on top
- CountingModel: scripted model that counts its calls, keeps what each call was shown, and can answer differently once the guard has spoken
- run_agent / tool_names: a ``create_skill_agent`` run over a scripted model (optionally collecting its events, keeping the chat across turns), and the tools it mounted

[POS]
Harness pytest-only helper shared by the completion-guard capability tests, so each one states its case
and not the plumbing around it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.runtime import Runtime
from pydantic import Field

from myrm_agent_harness.agent._factory.builder import create_skill_agent
from myrm_agent_harness.agent._internals._agent_build import build_middlewares
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.middlewares._session_context import EFFECTIVE_SECURITY_CONFIG_CONTEXT_KEY
from myrm_agent_harness.agent.middlewares.completion.completion_directive import BlockReasons
from myrm_agent_harness.agent.middlewares.completion.completion_guard import CompletionGuard
from myrm_agent_harness.agent.middlewares.completion.completion_guard_state import PendingDirective, current_run_state
from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.agent.tool_management import ToolRegistry, ToolSource
from myrm_agent_harness.agent.types import WorkspaceBinding
from myrm_agent_harness.api import AgentRuntimeSpec
from myrm_agent_harness.core.security.types import PermissionAction, PermissionRule, SecurityConfig
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

LOOP_GUARD_PATCH = "myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware.get_loop_guard"
CHECK_MARK = "CRITICAL COMPLETION CHECK"

_READ_ONLY_DENIALS = tuple(
    PermissionRule(permission, "*", PermissionAction.DENY)
    for permission in ("file_write", "file_edit", "file_delete", "shell_exec", "code_interpreter")
)


def writes_allowed(workspace: Path) -> SecurityConfig:
    base = SecurityConfig.workspace(allowed_roots=(str(workspace),))
    return replace(base, ruleset=(*base.ruleset, PermissionRule("*", "*", PermissionAction.ALLOW)))


def writes_denied(workspace: Path) -> SecurityConfig:
    """The deny set of the server's built-in Read Only profile on top of an otherwise permissive policy."""
    allowed = writes_allowed(workspace)
    return replace(allowed, ruleset=(*allowed.ruleset, *_READ_ONLY_DENIALS))


GUARD_DECISIONS: list[BlockReasons] = []


def stamped(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """The messages as the graph state holds them: its reducer gives every stored message an id."""
    return [m if m.id is not None else m.model_copy(update={"id": f"message-{i}"}) for i, m in enumerate(messages)]


def state(request: str, reply: str) -> dict[str, object]:
    return {"messages": stamped([HumanMessage(content=request), AIMessage(content=reply)])}


def runtime(workspace: Path, security: SecurityConfig | None = None) -> Runtime:
    context: dict[str, object] = {"workspace_path": str(workspace)}
    if security is not None:
        context[EFFECTIVE_SECURITY_CONFIG_CONTEXT_KEY] = security
    return Runtime(context=context)  # type: ignore[arg-type]


async def verdict(guard: CompletionGuard, messages: dict[str, object], at: Runtime) -> dict[str, object] | None:
    """What the guard does with one completion attempt, over a run that has called no tool yet."""
    with patch(LOOP_GUARD_PATCH) as loop_guard:
        loop_guard.return_value._window = []
        return await guard.aafter_model(messages, at)


def pending(result: dict[str, object] | None) -> PendingDirective:
    """The instruction a rejecting verdict leaves for the model: the verdict routes the run back to the model."""
    assert result is not None
    assert result.get("jump_to") == "model"
    owed = current_run_state().pending_directive
    assert owed is not None
    return owed


def reasons_of(result: dict[str, object] | None) -> BlockReasons:
    """The reasons the guard gave for the answer a rejecting verdict held back."""
    pending(result)
    return GUARD_DECISIONS[-1]


def directive_of(result: dict[str, object] | None) -> str:
    return pending(result).text


def named_tool(name: str) -> BaseTool:
    return StructuredTool.from_function(lambda: "ok", name=name, description=name)


def registry_of(mounted: Sequence[BaseTool]) -> ToolRegistry:
    registry = ToolRegistry()
    for mounted_tool in mounted:
        registry.register(mounted_tool, source=ToolSource.META)
    return registry


def built_guard(registry: ToolRegistry) -> CompletionGuard:
    """The CompletionGuard of the chain ``build_middlewares`` assembles over ``registry``."""
    for middleware in build_middlewares(registry, []):
        # The chain may hand a middleware over inside a sync-parity wrapper that keeps it as ``_inner``.
        inner = vars(middleware).get("_inner", middleware)
        if isinstance(inner, CompletionGuard):
            return inner
    raise AssertionError("no CompletionGuard in the chain")


class CountingModel(FakeMessagesListChatModel):
    """Repeats one scripted answer and counts the calls it serves.

    With ``answer_after_check`` it answers that instead once the request carries a guard rejection, which is
    what a model that does as the guard asks does. ``transcripts`` keeps the messages of every request.
    """

    requests: list[int] = Field(default_factory=list)
    transcripts: list[list[BaseMessage]] = Field(default_factory=list)
    answer_after_check: str | None = None

    def bind_tools(self, tools: object, **kwargs: object) -> CountingModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        self.requests.append(len(messages))
        self.transcripts.append(list(messages))
        if self.answer_after_check is not None and any(CHECK_MARK in str(m.content) for m in messages):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.answer_after_check))])
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


async def run_agent(
    tmp_path: Path,
    security: SecurityConfig,
    model: CountingModel,
    *,
    request: str,
    file_access_mode: FileAccessMode,
    enable_shell_tools: bool,
    events: list[dict[str, object]] | None = None,
    checkpointer: BaseCheckpointSaver | bool = False,
    then: Sequence[str] = (),
) -> tuple[SkillAgent, Path]:
    """Run ``request`` through a real agent whose only scripted part is the model; returns it and its workspace.

    The events the run streams are appended to ``events`` when given. Each request in ``then`` is a further turn of
    the same chat, which sees what the checkpointer kept of the turns before it.
    """
    workspace = (tmp_path / "project").resolve()
    workspace.mkdir()
    chat = "chat_completion_capability"
    binding = WorkspaceBinding(mode="chat", root_path=str(workspace), chat_id=chat)
    agent = await create_skill_agent(
        spec=AgentRuntimeSpec(
            agent_id="capability",
            name="capability",
            system_prompt="You answer requests.",
            skill_ids=[],
            workspace_binding=binding,
            security_config=security,
        ),
        llm=model,
        tools=[],
        storage_backend=LocalStorageBackend(str(tmp_path / "storage")),
        checkpointer=checkpointer,
        file_access_mode=file_access_mode,
        enable_shell_tools=enable_shell_tools,
    )
    context: dict[str, object] = {
        "workspace_path": str(workspace),
        "workspace_binding": binding,
        "workspaces_storage_root": str(tmp_path / "workspaces"),
        "session_id": chat,
    }
    for query in (request, *then):
        async for event in agent.run(query=query, context=context):
            if events is not None:
                events.append(event)
    return agent, workspace


def tool_names(agent: SkillAgent) -> set[str]:
    assert agent._cached_tools is not None
    return {mounted.name for mounted in agent._cached_tools}
