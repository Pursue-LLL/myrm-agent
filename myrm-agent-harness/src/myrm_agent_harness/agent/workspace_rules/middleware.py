"""Workspace context injection middleware.

Injects workspace-level rule files (AGENTS.md, CLAUDE.md, SOUL.md,
MEMORY.md, .cursorrules, .clinerules, .myrm.md, .hermes.md, HERMES.md,
.windsurfrules, .myrm/rules/*.md, .cursor/rules/*.mdc,
.claude/CLAUDE.md, .github/copilot-instructions.md) and a sandbox snapshot
as a SystemMessage into every model request.

Injection position: after user_instructions, before memory_context.
This preserves the KV Cache prefix hierarchy:

    [0] System Prompt                    ← cross-user cache ✅
    [1] <user_instructions>              ← per-user stable ✅
    [2] <workspace_context> (this)       ← stable per chat thread; changes only when a rule file does ✅
    [3] <user_memory_context>            ← per-user stable ✅
    [4+] Messages                        ← per-turn

The injection is a per-request override and never reaches the graph state, so it is rebuilt on every
model call. The rules are cheap to read and are read live. The snapshot probes git and the file system
and describes a workspace the agent edits while it works, so rebuilding it per call would run the probes
on the event loop each time and move the text at [2], which drops the cached prefix behind it. It is
therefore taken once per chat thread (again when the thread's workspace changes) by ``before_model`` and
kept in a private, checkpointed state key that every later call reads back.

⚠️ Self-update reminder: if this file changes, update:
1. agent/context_management/PROMPT_CACHE_PRACTICE.md §2

[INPUT]
- agent.workspace_rules.scanner::scan_workspace_rules, RuleFile (POS: workspace rule file scanner)
- agent.middlewares._session_context::get_workspace_root (POS: shared ContextVars for the middleware chain)
- agent.security.workspace_trust.gate::blocks_workspace_side_channels (POS: pure predicate layer of the workspace_trust gate; unknown trust is restricted)
- agent.security.workspace_trust.context::get_workspace_trust_level (POS: run-scoped state holder of the workspace_trust gate)
- toolkits.code_execution.sandbox_snapshot::generate_sandbox_bootstrap_snapshot, format_bootstrap_snapshot_xml (POS: sandbox snapshot generator)

[OUTPUT]
- WorkspaceContextState: the private state keys that hold the snapshot of a chat thread and the workspace it describes
- workspace_rules_middleware: singleton middleware instance

[POS]
Workspace context injection middleware. Reads project-level rule files live and serves the per-thread
sandbox snapshot as a stable SystemMessage prefix (after user_instructions, before memory_context)
for KV Cache optimization.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Annotated, NotRequired

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import AgentState, PrivateStateAttr
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

SNAPSHOT_KEY = "workspace_snapshot"
SNAPSHOT_ROOT_KEY = "workspace_snapshot_root"


class WorkspaceContextState(AgentState[object]):
    """The agent state plus the sandbox snapshot of this chat thread and the workspace it describes. Private: not part of the graph's input or output."""

    workspace_snapshot: NotRequired[Annotated[str, PrivateStateAttr]]
    workspace_snapshot_root: NotRequired[Annotated[str, PrivateStateAttr]]


def _trust_gate_blocks() -> bool:
    """Whether the workspace trust level keeps repo-local side channels, this injection included, closed."""
    from myrm_agent_harness.agent.security.workspace_trust.context import (
        get_workspace_trust_level,
    )
    from myrm_agent_harness.agent.security.workspace_trust.gate import (
        blocks_workspace_side_channels,
    )

    return blocks_workspace_side_channels(get_workspace_trust_level())


def _take_snapshot(workspace_root: str) -> str | None:
    """Probe the workspace and render the snapshot; ``None`` when the probe failed."""
    try:
        from myrm_agent_harness.toolkits.code_execution.sandbox_snapshot import (
            format_bootstrap_snapshot_xml,
            generate_sandbox_bootstrap_snapshot,
        )

        return format_bootstrap_snapshot_xml(generate_sandbox_bootstrap_snapshot(workspace_root))
    except Exception:
        logger.debug("Failed to generate sandbox bootstrap snapshot", exc_info=True)
        return None


def _snapshot_of(state: Mapping[str, object], workspace_root: str) -> str | None:
    """The snapshot the thread holds, provided it describes ``workspace_root``."""
    snapshot = state.get(SNAPSHOT_KEY)
    if isinstance(snapshot, str) and state.get(SNAPSHOT_ROOT_KEY) == workspace_root:
        return snapshot
    return None


def _find_workspace_insert_idx(messages: Sequence[object]) -> int:
    """Find insertion point: after all leading SystemMessages.

    This places workspace_context after system_prompt and user_instructions
    but before HumanMessage/memory learned advisory.
    """
    idx = 0
    for i, msg in enumerate(messages):
        if isinstance(msg, SystemMessage):
            idx = i + 1
        else:
            break
    return idx


def _format_rules_content(rules: Sequence[object]) -> str:
    """Format loaded rule files into a single SystemMessage content."""
    import os

    from myrm_agent_harness.agent.workspace_rules.scanner import RuleFile

    sections: list[str] = []
    for rule in rules:
        if not isinstance(rule, RuleFile):
            continue
        filename = os.path.basename(rule.path)
        sections.append(f"### {filename}\n{rule.content}")

    body = "\n\n".join(sections)
    return (
        '<workspace_context source="project_rules">\n'
        "[Project-level rules discovered in workspace. "
        "Follow these instructions for project-specific behavior.]\n\n"
        f"{body}\n"
        "</workspace_context>"
    )


class WorkspaceRulesMiddleware(AgentMiddleware[WorkspaceContextState, None, object]):
    """Workspace context injection middleware.

    Every model call is sent the project rules, read live, and the sandbox snapshot. The snapshot is taken once
    per chat thread and kept in the graph state, so the text at this position of the prefix does not move while
    the agent edits the workspace.
    """

    name = "workspace_rules_middleware"
    state_schema = WorkspaceContextState

    def before_model(self, state: WorkspaceContextState, runtime: Runtime[None]) -> dict[str, str] | None:
        """Take the snapshot when this thread has none for its workspace; a trust-gated workspace is never probed."""
        workspace_root = self._resolve_workspace_root(runtime)
        if not workspace_root or _snapshot_of(state, workspace_root) is not None:
            return None
        if _trust_gate_blocks():
            return None
        snapshot = _take_snapshot(workspace_root)
        if snapshot is None:
            return None
        return {SNAPSHOT_KEY: snapshot, SNAPSHOT_ROOT_KEY: workspace_root}

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        workspace_root = self._resolve_workspace_root(request.runtime)
        if not workspace_root:
            return await handler(request)

        if _trust_gate_blocks():
            logger.info(
                "Workspace trust gate: skipping workspace rules injection for %s",
                workspace_root,
            )
            return await handler(request)

        from myrm_agent_harness.agent.workspace_rules.scanner import (
            scan_workspace_rules,
        )

        rules = scan_workspace_rules(workspace_root)

        content_parts: list[str] = []
        if rules:
            content_parts.append(_format_rules_content(rules))

        snapshot = _snapshot_of(request.state, workspace_root)
        if snapshot is not None:
            content_parts.append(snapshot)

        if not content_parts:
            return await handler(request)

        combined_content = "\n\n".join(content_parts)
        rules_msg = SystemMessage(content=combined_content)

        new_messages = list(request.messages)
        insert_idx = _find_workspace_insert_idx(new_messages)
        new_messages.insert(insert_idx, rules_msg)

        request = request.override(messages=new_messages)

        logger.info(
            "Injected workspace context (%d rule files, %d chars, snapshot=%s) at position %d",
            len(rules),
            len(combined_content),
            snapshot is not None,
            insert_idx,
        )

        return await handler(request)

    @staticmethod
    def _resolve_workspace_root(runtime: object | None) -> str:
        """Extract workspace_root from the run's context or the session context."""
        if runtime is not None:
            context = getattr(runtime, "context", None)
            if isinstance(context, dict):
                raw = context.get("workspace_path")
                if isinstance(raw, str) and raw:
                    return raw

        from myrm_agent_harness.agent.middlewares._session_context import (
            get_workspace_root,
        )

        return get_workspace_root()


workspace_rules_middleware = WorkspaceRulesMiddleware()
