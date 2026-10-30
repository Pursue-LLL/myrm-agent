"""The agent a BaseAgent ships, built the way a run builds it, over a scripted model.

[INPUT]
- agent._internals._agent_build::build_middlewares, create_registry (POS: the middleware stack an agent runs)
- agent.middlewares._session_context (POS: the per-run session context the stack reads)

[OUTPUT]
- ScriptedModel: answers from a script and records what each call was sent
- shipped_agent: the shipped middleware stack compiled with ``create_agent`` around given tools
- shipped_session: the session context of a run that may use tools without asking, restored on exit
- yolo_config: the security config of such a run

[POS]
A test of the stack that is not about one middleware compiles the same graph a run does, so what it observes
(which tool calls run together, what the model is sent, what a hook returns) is what a user's run does. Mocks of
the framework would only show what the mock does.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import Field

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares._session_context import (
    reset_terminal_errors,
    set_canary_token,
    set_pseudonym_store,
    set_security_config,
    set_workspace_root,
)
from myrm_agent_harness.agent.security.types import PrivacyPolicy, SecurityConfig
from myrm_agent_harness.agent.types import EngineParams
from myrm_agent_harness.core.security.audit import reset_audit_log
from myrm_agent_harness.core.security.guards.privacy_tracker import reset_privacy_tracker


class ScriptedModel(BaseChatModel):
    """Answers from a script and records the messages each call was sent, as ``(type, text)`` pairs."""

    script: list[AIMessage]
    calls: list[list[tuple[str, str]]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> ScriptedModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        self.calls.append([(type(m).__name__, str(m.content)) for m in messages])
        reply = self.script[min(len(self.calls), len(self.script)) - 1]
        return ChatResult(generations=[ChatGeneration(message=reply)])


def shipped_agent(
    script: list[AIMessage],
    tools: Sequence[BaseTool],
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    without: Sequence[str] = (),
    engine: EngineParams | None = None,
) -> tuple[ScriptedModel, CompiledStateGraph]:
    """The agent's own middleware stack in a graph, minus the middlewares named in *without*."""
    model = ScriptedModel(script=script)
    middlewares = [m for m in build_middlewares(create_registry(), [], engine) if m.name not in without]
    return model, create_agent(model, tools=list(tools), middleware=middlewares, checkpointer=checkpointer)


def yolo_config(policy: PrivacyPolicy | None = None) -> SecurityConfig:
    """A run that may use tools without an approval interrupt."""
    return SecurityConfig(
        yolo_mode_enabled=True,
        yolo_mode_enabled_at=time.time(),
        privacy_policy=policy or PrivacyPolicy(enabled=False),
    )


@contextmanager
def shipped_session(workspace: Path) -> Iterator[None]:
    """The session context of a run in *workspace* that may use tools without asking; restored on exit."""
    reset_terminal_errors()
    reset_audit_log()
    reset_privacy_tracker()
    set_security_config(yolo_config())
    set_workspace_root(str(workspace))
    try:
        yield
    finally:
        set_security_config(None)
        set_canary_token("")
        set_pseudonym_store(None)
        set_workspace_root("")
        reset_terminal_errors()
