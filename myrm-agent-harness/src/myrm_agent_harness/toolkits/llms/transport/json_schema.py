"""JSON Schema reference inlining shared by the wires that cannot accept ``$ref``.

[INPUT]
- (none) Pure dict transforms.

[OUTPUT]
- inline_refs: the schema with every local ``$ref`` replaced by the definition it points to

[POS]
Anthropic structured output and Gemini function declarations reject ``$ref`` / ``$defs``; both first flatten the
schema through this single resolver. Cyclic references cannot be flattened and become an empty schema (any value)
rather than looping.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

_MAX_DEPTH: Final = 32
_DEFINITION_KEYS: Final = ("$defs", "definitions")

Schema = dict[str, object]


def _target(ref: str, root: Mapping[str, object]) -> Mapping[str, object] | None:
    if not ref.startswith("#/"):
        return None
    node: object = root
    for part in ref[2:].split("/"):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, Mapping) else None


def _inline(node: object, root: Mapping[str, object], active: frozenset[str], depth: int) -> object:
    if depth > _MAX_DEPTH:
        return {}
    if isinstance(node, list):
        return [_inline(item, root, active, depth + 1) for item in node]
    if not isinstance(node, Mapping):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str):
        target = _target(ref, root)
        if target is None or ref in active:
            return {}
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        return _inline({**target, **siblings}, root, active | {ref}, depth + 1)
    return {
        k: _inline(v, root, active, depth + 1) for k, v in node.items() if k not in _DEFINITION_KEYS or node is not root
    }


def inline_refs(schema: Mapping[str, object]) -> Schema:
    """``schema`` with local references resolved and the root-level definition tables removed."""
    resolved = _inline(schema, schema, frozenset(), 0)
    if not isinstance(resolved, dict):
        return {}
    # A root that is itself a reference (the shape recursive models serialize to) carries the tables as siblings.
    for key in _DEFINITION_KEYS:
        resolved.pop(key, None)
    return resolved
