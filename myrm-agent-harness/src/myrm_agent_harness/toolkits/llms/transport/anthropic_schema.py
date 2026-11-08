"""Structured-output schema conversion for the Anthropic Messages API.

[INPUT]
- transport.json_schema (POS: reference inlining)

[OUTPUT]
- to_output_schema: a JSON Schema reduced to what Anthropic's constrained decoding accepts

[POS]
Anthropic compiles the schema into a decoding grammar and rejects keywords it cannot enforce with a 400. Those
constraints are dropped and restated in the ``description`` so the model still sees them, ``oneOf`` becomes
``anyOf``, and every object gets ``additionalProperties: false`` as the API requires.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final, cast

from myrm_agent_harness.toolkits.llms.transport.json_schema import inline_refs

# keyword -> advisory note; the order is fixed so identical schemas always serialize identically (cache-friendly).
_UNSUPPORTED: Final = {
    "minItems": "minimum number of items: {}",
    "maxItems": "maximum number of items: {}",
    "uniqueItems": "all array items must be unique",
    "contains": "array must contain an item matching: {}",
    "minContains": "minimum number of matching items: {}",
    "maxContains": "maximum number of matching items: {}",
    "prefixItems": "leading items must match, in order: {}",
    "minimum": "minimum value: {}",
    "maximum": "maximum value: {}",
    "exclusiveMinimum": "exclusive minimum value: {}",
    "exclusiveMaximum": "exclusive maximum value: {}",
    "multipleOf": "must be a multiple of {}",
    "minLength": "minimum length: {}",
    "maxLength": "maximum length: {}",
    "minProperties": "minimum number of properties: {}",
    "maxProperties": "maximum number of properties: {}",
    "patternProperties": "properties whose names match each pattern must satisfy: {}",
    "propertyNames": "property names must satisfy: {}",
    "dependentRequired": "dependent required properties: {}",
    "dependentSchemas": "dependent schemas: {}",
    "unevaluatedProperties": "unevaluated properties must satisfy: {}",
    "if": "conditional (if): {}",
    "then": "conditional (then): {}",
    "else": "conditional (else): {}",
    "not": "must not match: {}",
}
_SUBSCHEMA_LISTS: Final = ("anyOf", "allOf", "oneOf")

Schema = dict[str, object]


def _notes(node: Mapping[str, object]) -> list[str]:
    notes: list[str] = []
    for key, label in _UNSUPPORTED.items():
        if key not in node or node[key] is False:
            continue
        value = node[key]
        notes.append(label.format(json.dumps(value) if isinstance(value, (dict, list)) else value))
    return notes


def _convert(node: object) -> object:
    if not isinstance(node, Mapping):
        return node
    result: Schema = {}
    notes = _notes(node)
    if notes:
        existing = node.get("description")
        note = "Note: " + ", ".join(notes) + "."
        result["description"] = f"{existing} {note}" if existing else note
    for key, value in node.items():
        if key in _UNSUPPORTED or (key == "description" and "description" in result):
            continue
        if key in ("properties", "$defs") and isinstance(value, Mapping):
            result[key] = {k: _convert(v) for k, v in value.items()}
        elif key == "items" and isinstance(value, Mapping):
            result[key] = _convert(value)
        elif key in _SUBSCHEMA_LISTS and isinstance(value, list):
            target = "anyOf" if key == "oneOf" else key
            merged = cast("list[object]", result.get(target) or [])
            result[target] = [*merged, *(_convert(v) for v in value)]
        else:
            result[key] = value
    if result.get("type") == "object":
        result["additionalProperties"] = False
    return result


def to_output_schema(schema: Mapping[str, object]) -> Schema:
    converted = _convert(inline_refs(schema))
    return converted if isinstance(converted, dict) else {}
