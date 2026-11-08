"""Structured output on the Bedrock Converse wire: the model's native output format, or a synthetic tool.

[INPUT]
- transport.bedrock_content (POS: Block)
- transport.json_schema (POS: reference inlining of tool schemas)
- catalog::model_facts (POS: whether a model has a native structured output)

[OUTPUT]
- JSON_TOOL: the name of the synthetic tool that carries a structured answer
- Structured / structured: the schema a response format asks the answer to follow
- supports_native_output: whether the model takes the schema as an output format
- output_config: the ``outputConfig`` that asks for the schema natively
- json_tool: the synthetic tool whose call carries the answer

[POS]
Converse has no ``response_format``. A model that lists a native structured output (newer Claude, Qwen3, DeepSeek V3,
Mistral Large 3 and others) is given the schema as ``outputConfig.textFormat`` and answers in plain text that already
follows it, with reasoning and tools unaffected. Every other model is given the schema as the input of one synthetic
tool, which ``bedrock_response`` turns back into the answer text.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final, NamedTuple

from myrm_agent_harness.toolkits.llms.catalog import model_facts
from myrm_agent_harness.toolkits.llms.transport.bedrock_content import Block
from myrm_agent_harness.toolkits.llms.transport.json_schema import inline_refs

JSON_TOOL: Final = "json_tool_call"
# A ``json_object`` that has a schema attached is read like a ``json_schema``; a bare one names no schema to follow.
_SCHEMA_FORMATS: Final = frozenset({"json_schema", "json_object"})
# Schema keywords whose values are schemas by name, one schema, or a list of schemas.
_SCHEMA_MAPS: Final = ("properties", "$defs", "definitions")
_SCHEMA_LISTS: Final = ("anyOf", "allOf", "oneOf")


class Structured(NamedTuple):
    schema: Mapping[str, object]
    name: str | None
    description: str | None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def structured(response_format: object) -> Structured | None:
    """The schema a response format carries; one that names none (plain text, a bare ``json_object``) asks for none."""
    if not isinstance(response_format, Mapping) or response_format.get("type") not in _SCHEMA_FORMATS:
        return None
    holder = response_format.get("json_schema")
    schema = holder.get("schema") if isinstance(holder, Mapping) else response_format.get("response_schema")
    if not isinstance(schema, Mapping):
        return None
    if isinstance(holder, Mapping):
        return Structured(schema, _text(holder.get("name")), _text(holder.get("description")))
    return Structured(schema, None, None)


def supports_native_output(model: str) -> bool:
    return (model_facts(model, "bedrock_converse") or {}).get("supports_native_structured_output") is True


def _closed(schema: object) -> object:
    """``schema`` with ``additionalProperties: false`` on every object that states none: the API demands it."""
    if not isinstance(schema, Mapping):
        return schema
    node = dict(schema)
    if node.get("type") == "object" and "additionalProperties" not in node:
        node["additionalProperties"] = False
    for key in _SCHEMA_MAPS:
        if isinstance(node.get(key), Mapping):
            node[key] = {name: _closed(child) for name, child in node[key].items()}
    if isinstance(node.get("items"), Mapping):
        node["items"] = _closed(node["items"])
    for key in _SCHEMA_LISTS:
        if isinstance(node.get(key), list):
            node[key] = [_closed(item) for item in node[key]]
    return node


def output_config(asked: Structured) -> Block:
    definition: dict[str, object] = {"schema": json.dumps(_closed(asked.schema))}
    if asked.name:
        definition["name"] = asked.name
    if asked.description:
        definition["description"] = asked.description
    return {"textFormat": {"type": "json_schema", "structure": {"jsonSchema": definition}}}


def json_tool(asked: Structured) -> Block:
    """The tool whose forced call carries the answer; the API rejects a blank description, so the name stands in."""
    spec = {
        "name": JSON_TOOL,
        "description": asked.description or JSON_TOOL,
        "inputSchema": {"json": inline_refs(asked.schema)},
    }
    return {"toolSpec": spec}
