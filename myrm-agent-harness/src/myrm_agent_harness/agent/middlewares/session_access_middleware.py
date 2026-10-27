"""Inject per-turn session directory access context for the agent.

[POS]
See module docstring.
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.middlewares._session_context import (
    get_security_config,
    get_workspace_root,
)
from myrm_agent_harness.agent.security.session_access import render_session_access_context

_SESSION_ACCESS_MARKER = "<session-access>"


class SessionAccessMiddleware(AgentMiddleware):
    """Append the available directory roots when the message history does not carry them yet.

    State merges what a hook returns: the new message is appended, the messages already there stay as they are.
    """

    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Sequence[BaseMessage]] | None:
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
        return {"messages": [SystemMessage(content=content)]}
