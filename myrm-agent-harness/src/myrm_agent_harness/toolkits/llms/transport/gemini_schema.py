"""Tool-parameter schema conversion for the Gemini API.

[INPUT]
- (none) Pure dict transforms.

[OUTPUT]
- to_gemini_schema: a JSON Schema reduced to the OpenAPI subset the Gemini API accepts

[POS]
Gemini rejects JSON Schema keywords outside its OpenAPI subset (``additionalProperties``, ``$schema``, ``$ref``,
``const``, type unions, ...) with a 400, so tool schemas written for other providers are rewritten here: references are
inlined (``json_schema.inline_refs``), nullable unions become ``nullable``, ``const`` becomes a single-value
``enum``, non-string enums become string enums, and unknown keywords are dropped.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from myrm_agent_harness.toolkits.llms.transport.json_schema import inline_refs

_ALLOWED: Final = frozenset(
    {
        "type",
        "format",
        "title",
        "description",
        "nullable",
        "items",
        "enum",
        "properties",
        "required",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "minProperties",
        "maxProperties",
        "pattern",
    }
)
_ALLOWED_STRING_FORMATS: Final = frozenset({"enum", "date-time"})
_MAX_DEPTH: Final = 12

Schema = dict[str, object]


def _convert(node: object, depth: int) -> Schema:
    if not isinstance(node, Mapping) or depth > _MAX_DEPTH:
        return {}
    schema: Schema = {k: v for k, v in node.items() if k in _ALLOWED}
    nullable = bool(node.get("nullable"))

    declared = node.get("type")
    if isinstance(declared, list):
        kinds = [t for t in declared if t != "null"]
        nullable = nullable or len(kinds) != len(declared)
        schema["type"] = kinds[0] if kinds else "string"

    variants = node.get("anyOf") or node.get("oneOf")
    if isinstance(variants, list):
        live = [v for v in variants if not (isinstance(v, Mapping) and v.get("type") == "null")]
        nullable = nullable or len(live) != len(variants)
        if len(live) == 1:
            schema.update(_convert(live[0], depth + 1))
        elif live:
            schema["anyOf"] = [_convert(v, depth + 1) for v in live]

    if "const" in node and "enum" not in schema:
        schema["enum"] = [node["const"]]
    enum = schema.get("enum")
    if isinstance(enum, list) and any(not isinstance(v, str) for v in enum):
        schema["enum"] = [str(v) for v in enum]
        schema["type"] = "string"

    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        schema["properties"] = {str(k): _convert(v, depth + 1) for k, v in properties.items()}
    if "items" in schema:
        schema["items"] = _convert(schema["items"], depth + 1)

    if schema.get("format") not in (None, *_ALLOWED_STRING_FORMATS):
        del schema["format"]
    if schema.get("type") == "object" and "properties" not in schema:
        schema["properties"] = {}
    if nullable:
        schema["nullable"] = True
    return schema


def to_gemini_schema(parameters: Mapping[str, object]) -> Schema:
    """The Gemini-acceptable form of a tool's JSON-Schema ``parameters``."""
    schema = _convert(inline_refs(parameters), 0)
    if "type" not in schema and "anyOf" not in schema:
        schema["type"] = "object"
        schema.setdefault("properties", {})
    return schema
