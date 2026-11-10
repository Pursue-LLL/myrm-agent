"""Raw tool call to LangChain ToolCall conversion

[INPUT]
- langchain_core.messages::ToolCall (POS: LangChain tool call type)
- adapters.tool_call_parsers::ToolCallDict, decode_html_entities_in_args (POS: tool call parser + HTML entity decoding)
- utils.tool_argument_recovery::parse_tool_call_arguments_with_recovery (POS: schema-aware JSON recovery utility)

[OUTPUT]
- resolve_tool_schema(): schema lookup that tolerates namespace-prefixed tool names
- parse_tool_call_args_result(): parse tool arguments with recovery, optionally HTML-decoding them
- convert_raw_tool_call_to_langchain(): OpenAI-format tool call to a LangChain ToolCall, or ``None`` plus recovery metadata when the call cannot be executed safely
- build_invalid_tool_call(): ``invalid_tool_call`` declaration for a call that failed safe parsing

[POS]
Inbound half of the tool call conversion: turns what a provider sent into calls the agent may dispatch. An unsafe
parse never becomes an executable call; it is surfaced as an invalid call the model can see and retry.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from uuid import uuid4

from langchain_core.messages import ToolCall

from myrm_agent_harness.toolkits.llms.adapters.tool_call_parsers import (
    ToolCallDict,
    decode_html_entities_in_args,
)
from myrm_agent_harness.toolkits.llms.utils.tool_argument_recovery import (
    ToolArgumentRecoveryResult,
    parse_tool_call_arguments_with_recovery,
)

logger = logging.getLogger(__name__)


def resolve_tool_schema(
    tool_name: str,
    tool_schemas: Mapping[str, Mapping[str, object]] | None = None,
) -> Mapping[str, object] | None:
    if not tool_schemas:
        return None
    if tool_name in tool_schemas:
        return tool_schemas[tool_name]
    if ":" in tool_name:
        stripped_name = tool_name.split(":")[-1]
        return tool_schemas.get(stripped_name)
    return None


def parse_tool_call_args_result(
    args: str | dict[str, object],
    tool_name: str,
    tool_schema: Mapping[str, object] | None = None,
    *,
    stream_complete: bool | None = None,
    decode_html_entities: bool = False,
) -> tuple[dict[str, object], ToolArgumentRecoveryResult]:
    recovery = parse_tool_call_arguments_with_recovery(args, tool_name, tool_schema, stream_complete=stream_complete)
    parsed: dict[str, object] = recovery.args if recovery.safe else {}

    if decode_html_entities and parsed:
        decoded = decode_html_entities_in_args(parsed)
        if isinstance(decoded, dict):
            parsed = decoded

    return parsed, recovery


def convert_raw_tool_call_to_langchain(
    tc: ToolCallDict,
    tool_schemas: Mapping[str, Mapping[str, object]] | None = None,
    *,
    stream_complete: bool | None = None,
    decode_html_entities: bool = False,
) -> tuple[ToolCall | None, dict[str, object] | None]:
    """Convert an OpenAI-format tool call to a LangChain ToolCall object.

    Returns ``(tool_call, recovery_metadata)``. ``tool_call`` is ``None`` when the
    call cannot be safely executed — either its args failed every repair strategy
    or the args are known to be truncated mid-stream. The caller must route such
    calls to ``invalid_tool_calls`` (with the diagnosis) and never dispatch them,
    so a missing/partial argument never becomes a silently-wrong execution.

    Args:
        tc: OpenAI-format tool call dict.
        tool_schemas: Tool schemas keyed by name, for schema-aware recovery.
        stream_complete: Whether the producing stream ended normally. ``False``
            marks truncated args as unsafe even when a close-the-JSON repair
            would otherwise succeed.
        decode_html_entities: Whether to HTML-decode argument strings. xAI Grok
            escapes them; every other model's arguments are data.
    """
    try:
        args = tc["function"]["arguments"]

        # ensure args are a JSON string
        if isinstance(args, dict):
            args = json.dumps(args, sort_keys=True)

        # Get or Generate tool_call_id
        tool_call_id = tc.get("id", "")
        if not tool_call_id:
            tool_call_id = f"call_{uuid4().hex[:24]}"
            logger.warning(f" Generate tool_call_id: {tc['function']['name']} -> {tool_call_id}")

        # Process tool name (strip namespace prefixes)
        raw_tool_name = tc["function"]["name"]
        tool_name = raw_tool_name
        if ":" in tool_name:
            tool_name = tool_name.split(":")[-1]
            logger.warning(f" Corrected tool name: {raw_tool_name} -> {tool_name}")

        # ParseParameter JSON
        parsed_args, recovery = parse_tool_call_args_result(
            args,
            tool_name,
            resolve_tool_schema(raw_tool_name, tool_schemas),
            stream_complete=stream_complete,
            decode_html_entities=decode_html_entities,
        )

        metadata = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "strategy": recovery.strategy,
            "degraded": recovery.degraded,
            "safe": recovery.safe,
        }
        if recovery.strategy != "standard_json" or recovery.degraded or not recovery.safe:
            from myrm_agent_harness.observability.metrics.registry import (
                metrics_registry,
            )

            metrics_registry.record_tool_arg_recovery(
                agent_id="base_agent",
                tool_name=tool_name,
                strategy=recovery.strategy,
                safe=recovery.safe,
            )
        if not recovery.safe:
            # Hard gate: an unsafe parse must never become an executable tool call.
            # Return no ToolCall so the caller exposes it as an invalid call the
            # model can see and retry; wrong/empty args are never dispatched.
            # The internal strategy name stays in structured metadata (below) and
            # out of the model-facing error text.
            metadata["error"] = (
                f"Tool call arguments for '{tool_name}' could not be safely parsed; the call was NOT executed."
            )
            logger.warning(
                " Unsafe tool_call args withheld from execution for %s via %s",
                tool_name,
                recovery.strategy,
            )
            return None, metadata
        if recovery.strategy != "standard_json" or recovery.degraded:
            logger.warning(" Recovered tool_call args for %s via %s", tool_name, recovery.strategy)

        return (
            ToolCall(
                name=tool_name,
                args=parsed_args,
                id=tool_call_id,
            ),
            metadata,
        )
    except (KeyError, TypeError) as e:
        logger.warning(f" ToolCallConvertFailure: {e}")
        return None, None


def build_invalid_tool_call(
    tc: ToolCallDict,
    metadata: Mapping[str, object],
) -> dict[str, object]:
    """Build an ``invalid_tool_call`` declaration for a call that failed safe parsing.

    The raw argument text is preserved so the dangling-call repair pipeline can
    quarantine it (never replaying malformed text) and so the model receives a
    structured diagnosis; a wrong/empty call is never executed.
    """
    function_obj = tc.get("function") or {}
    raw_args = function_obj.get("arguments", "")
    if isinstance(raw_args, dict):
        raw_args = json.dumps(raw_args, sort_keys=True)
    elif not isinstance(raw_args, str):
        raw_args = "" if raw_args is None else str(raw_args)
    return {
        "type": "invalid_tool_call",
        "id": str(metadata.get("tool_call_id") or tc.get("id", "")),
        "name": str(metadata.get("tool_name") or function_obj.get("name", "")),
        "args": raw_args,
        "error": str(metadata.get("error") or "Unsafe tool call arguments"),
    }
