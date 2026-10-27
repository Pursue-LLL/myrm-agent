"""The model response the approval stage looks at, and the context it is judged in.

[INPUT]
- agent.middlewares._session_context::get_approval_session, get_security_config, get_workspace_root, resolve_security_config_from_runtime, set_security_config (POS: Middleware session context — shared ContextVars for the middleware chain.)
- agent.security.channel_presets::build_channel_security_config (POS: The fail-closed security configuration of a channel.)
- agent.security.tool_registry::compute_canonical_args_hash (POS: Canonical hash of a call's arguments, the same for any wording of the same operation.)
- ..refusal::answered_call_ids (POS: Which calls of a model response an earlier guard already answered.)

[OUTPUT]
- ApprovalTarget: the model response, the calls still to be judged, and the session they are judged in
- resolve_approval_target: find the target in the graph state, or None when no call needs a verdict

[POS]
The node that judges a batch and the node that asks the person must look at the same calls in the same context, so
both find them here.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage

from myrm_agent_harness.agent.middlewares._session_context import (
    get_approval_session,
    get_security_config,
    get_workspace_root,
    resolve_security_config_from_runtime,
    set_security_config,
)
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.tool_registry import compute_canonical_args_hash
from myrm_agent_harness.agent.security.types import SecurityConfig

from ..refusal import answered_call_ids

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ApprovalTarget:
    """The latest model response with tool calls and the context its calls are judged in.

    ``source`` is the message as the graph state holds it. ``unanswered`` is the same message without the calls an
    earlier guard already answered; only those are judged. ``answered_ids`` are the ids of the calls left out.
    """

    config: SecurityConfig
    messages: Sequence[BaseMessage]
    source: AIMessage
    unanswered: AIMessage
    answered_ids: frozenset[str]
    session_key: str
    workspace_root: str | None
    is_cron: bool
    args_hashes: dict[int, str | None]


def resolve_security_config(runtime: object | None) -> SecurityConfig:
    """The security configuration of this run, from the runtime context or the session; fail-closed web chat if neither."""
    config = get_security_config()
    runtime_config = resolve_security_config_from_runtime(runtime)
    if runtime_config is not None:
        set_security_config(runtime_config)
        return runtime_config
    if config is not None:
        return config
    run_config: SecurityConfig | None = getattr(getattr(runtime, "config", None), "security_config", None)
    if run_config is None:
        logger.error(
            "[SECURITY] security_config missing in async context — applying fail-closed web_chat defaults (session=%s)",
            get_approval_session(),
        )
        run_config = build_channel_security_config("web_chat", None, local_mode=True)
    set_security_config(run_config)
    return run_config


def resolve_approval_target(state: Mapping[str, object], runtime: object | None) -> ApprovalTarget | None:
    """The calls of the latest model response that still need a verdict, or None when there are none."""
    config = resolve_security_config(runtime)

    messages = state.get("messages")
    if not isinstance(messages, Sequence) or not messages:
        return None

    source = next((message for message in reversed(messages) if isinstance(message, AIMessage)), None)
    if source is None or not source.tool_calls:
        return None

    # A guard that ran before the approval stage may already have answered some calls; those never reach the person.
    answered_ids = frozenset(answered_call_ids(messages, source))
    unanswered = source
    if answered_ids:
        unanswered = source.model_copy(
            update={"tool_calls": [call for call in source.tool_calls if call.get("id") not in answered_ids]}
        )
        if not unanswered.tool_calls:
            return None

    session_key = get_approval_session()
    return ApprovalTarget(
        config=config,
        messages=messages,
        source=source,
        unanswered=unanswered,
        answered_ids=answered_ids,
        session_key=session_key,
        workspace_root=get_workspace_root() or None,
        is_cron=session_key.startswith("cron:"),
        args_hashes={
            index: compute_canonical_args_hash(call.get("name", "unknown"), call.get("args"))
            for index, call in enumerate(unanswered.tool_calls)
        },
    )
