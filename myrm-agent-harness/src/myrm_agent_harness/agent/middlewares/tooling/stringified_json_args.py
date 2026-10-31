"""Parse list and object arguments a model sent as JSON strings, before the tool validates them.

[INPUT]
- utils.json_args_repair::repair_json_args (POS: one deterministic syntax-level repair of a truncated JSON object string)
- langchain.agents.middleware::wrap_tool_call (POS: public tool-call middleware hook)
- langchain.agents.middleware::ToolCallRequest (POS: tool execution request; ``override`` returns a modified copy)

[OUTPUT]
- stringified_json_args_middleware: hands the tool the arguments with every JSON string for a list or object field parsed

[POS]
Some models send ``"[\"a\", \"b\"]"`` where the schema asks for a list, and a stream cut short leaves an object string
without its closing braces. Pydantic rejects both on syntax alone, and the model then repeats the same call. The
fields to parse come from the tool's own JSON Schema: only a field that declares an array or an object is touched,
so a string argument that happens to start with ``[`` stays a string. The middleware sits innermost, behind the
middleware that resolves dynamic tools, so it sees the tool that will run; the request it passes on is a copy, and
the arguments recorded on the model's message are not changed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from weakref import WeakKeyDictionary

from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import BaseModel

from myrm_agent_harness.utils.json_args_repair import repair_json_args

logger = logging.getLogger(__name__)

# Per schema class, so two tools whose schema classes share a name never share an answer.
_CONTAINER_FIELDS: WeakKeyDictionary[type[BaseModel], frozenset[str]] = WeakKeyDictionary()
_CONTAINER_TYPES = ("array", "object")


def _declares_container(prop: dict[str, object]) -> bool:
    """Whether a JSON Schema property is an array or an object, alone or as one variant of an ``anyOf``."""
    if prop.get("type") in _CONTAINER_TYPES:
        return True
    variants = prop.get("anyOf")
    return isinstance(variants, list) and any(
        isinstance(variant, dict) and variant.get("type") in _CONTAINER_TYPES for variant in variants
    )


def _container_fields(schema: type[BaseModel]) -> frozenset[str]:
    """Names of the fields of *schema* that expect a list or an object."""
    cached = _CONTAINER_FIELDS.get(schema)
    if cached is not None:
        return cached
    try:
        properties = schema.model_json_schema().get("properties", {})
    except Exception:  # a schema that cannot render as JSON Schema has no field to parse; the tool validates it itself
        logger.debug("No JSON Schema for %s; its arguments are passed as sent", schema.__name__, exc_info=True)
        properties = {}
    fields = frozenset(name for name, prop in properties.items() if _declares_container(prop))
    _CONTAINER_FIELDS[schema] = fields
    return fields


def _loads_container(text: str) -> list[object] | dict[str, object] | None:
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, (list, dict)) else None


def _parse_container(text: str) -> list[object] | dict[str, object] | None:
    """The list or object *text* holds, repairing one truncation; ``None`` when it holds none."""
    if len(text) < 2 or text[0] not in "[{":
        return None
    parsed = _loads_container(text)
    if parsed is not None:
        return parsed
    repaired = repair_json_args(text).repaired
    return _loads_container(repaired) if repaired is not None else None


def _with_parsed_containers(args: dict[str, object], fields: frozenset[str]) -> dict[str, object] | None:
    """A copy of *args* with each JSON string for a field in *fields* parsed; ``None`` when nothing needed parsing."""
    parsed_fields: dict[str, object] = {}
    for name in fields:
        value = args.get(name)
        if isinstance(value, str) and (parsed := _parse_container(value)) is not None:
            parsed_fields[name] = parsed
            logger.info("Parsed the JSON string sent for argument '%s'", name)
    return {**args, **parsed_fields} if parsed_fields else None


@wrap_tool_call
async def stringified_json_args_middleware(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
) -> ToolMessage | Command[object]:
    """Run the tool with the JSON strings it was sent for list and object fields parsed."""
    args = request.tool_call.get("args")
    schema = getattr(request.tool, "args_schema", None)
    if isinstance(args, dict) and isinstance(schema, type) and issubclass(schema, BaseModel):
        parsed_args = _with_parsed_containers(args, _container_fields(schema))
        if parsed_args is not None:
            request = request.override(tool_call={**request.tool_call, "args": parsed_args})
    return await handler(request)
