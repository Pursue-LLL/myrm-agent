"""What the model is shown of a ``bash_process_tool`` result once the real guardrail middleware has screened it."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.middlewares.security.security_guardrail_middleware import SecurityGuardrailMiddleware


def shown_to_model(content: object) -> str:
    """The tool result as the model gets it: after ``before_model`` of the real guardrail middleware has rewritten it."""
    call = AIMessage(content="", tool_calls=[{"name": "bash_process_tool", "args": {}, "id": "call-1"}])
    result = ToolMessage(content=json.dumps(content), tool_call_id="call-1", name="bash_process_tool")
    update = SecurityGuardrailMiddleware().before_model(
        {"messages": [HumanMessage(content="run it"), call, result]}, None
    )
    rewritten = [m for m in (update or {}).get("messages", []) if isinstance(m, ToolMessage)]
    return str((rewritten or [result])[-1].content)
