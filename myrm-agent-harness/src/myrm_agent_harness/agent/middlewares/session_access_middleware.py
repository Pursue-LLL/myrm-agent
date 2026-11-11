"""Tell the model which directories its path tools may use, once per thread.

The block is a SystemMessage that lands behind the latest user message on the first model call and stays in the
history, so the prompt prefix before it is the same from turn to turn.

Only a run that holds a tool taking paths gets it. The fast-search mount carries ``file_read_tool`` alone, over
spill files and uploads whose paths the messages already state in full; the block would name a primary workspace
that run cannot touch and mark it ``[read-write]``.

[INPUT]
- agent.middlewares._session_context::get_security_config, get_workspace_root (POS: the policy and the workspace of the turn)
- agent.security.session_access::render_session_access_context (POS: the directory list, with the grants of the session)
- agent.tool_management::ToolRegistry (POS: the tools the run holds)
- core.message_origin::runtime_system_message (POS: marks the block as the runtime's, so models that only advise are not shown the paths)

[OUTPUT]
- SessionAccessMiddleware: appends the ``<session-access>`` block once per thread to a run that holds a tool taking paths

[POS]
Directory-access context of the middleware chain: the text is built in agent.security.session_access, this
middleware decides whether the run needs it and where it lands.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.middlewares._session_context import (
    get_security_config,
    get_workspace_root,
)
from myrm_agent_harness.agent.security.session_access import render_session_access_context
from myrm_agent_harness.core.message_origin import runtime_system_message

if TYPE_CHECKING:
    from myrm_agent_harness.agent.tool_management import ToolRegistry

_SESSION_ACCESS_MARKER = "<session-access>"

# A run holds one of these exactly when its file tools reach the workspace (the full and the workspace-read-only
# mounts both carry glob and grep) or it has a shell. The spill-and-uploads mount carries ``file_read_tool`` alone,
# so that tool does not count.
_PATH_TOOLS = frozenset({"glob_tool", "grep_tool", "file_write_tool", "file_edit_tool", "bash_code_execute_tool"})


class SessionAccessMiddleware(AgentMiddleware):
    """Append the available directory roots when the message history does not carry them yet.

    State merges what a hook returns: the new message is appended, the messages already there stay as they are.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Sequence[BaseMessage]] | None:
        # Read per call: the registry is filled after the middleware chain is built.
        if self._registry.tool_names().isdisjoint(_PATH_TOOLS):
            return None

        config = get_security_config()
        if config is None:
            return None

        workspace_root = get_workspace_root() or None
        block = render_session_access_context(config.path_policy, workspace_root)
        if not block:
            return None

        messages = state.get("messages", [])
        if not isinstance(messages, list):
            return None

        for msg in messages:
            if (
                isinstance(msg, SystemMessage)
                and isinstance(msg.content, str)
                and _SESSION_ACCESS_MARKER in msg.content
            ):
                return None

        content = f"{_SESSION_ACCESS_MARKER}\n{block}\n</session-access>"
        return {"messages": [runtime_system_message(content)]}
