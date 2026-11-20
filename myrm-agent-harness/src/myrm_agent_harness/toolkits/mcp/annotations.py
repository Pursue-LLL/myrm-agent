"""What an MCP server says about its own tools, and the little the host makes of it.

An MCP server attaches hints to a tool (``readOnlyHint``, ``destructiveHint``, ``idempotentHint``,
``openWorldHint``). The MCP SDK documents them as hints that need not describe the tool faithfully and tells clients
never to base tool-use decisions on those of an untrusted server: they are the server's own statement, nothing here
checks them, and a wrong one must never make the host less careful. So a claim may only tighten what the host does,
and it loosens exactly one thing: letting tools of different servers run side by side, which changes no approval
(calls to one server stay serialized by its session).

[INPUT]
- core.security.tool_registry::MCPAnnotations, SafetyMetadata (POS: the claim slot approval cards show and the safety record the schedulers read)

[OUTPUT]
- ANNOTATIONS_METADATA_KEY: the tool metadata key a converted tool carries its declarations under
- DeclaredAnnotations: the hints a server declared, each present only when the server stated it
- declared_annotations: read the declarations off an SDK ``Tool``
- recorded_annotations: read them back off a converted tool
- judge: declarations → the host's safety record and the claims worth showing

[POS]
The single place a server's self-reported hints turn into host behavior; every other consumer reads the record
``judge`` produced and never the hints themselves.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict, cast

from myrm_agent_harness.core.security.tool_registry import MCPAnnotations, SafetyMetadata

ANNOTATIONS_METADATA_KEY = "mcp_annotations"

# (wire spelling, SDK attribute): the SDK exposes snake_case attributes and keeps the wire spelling only as an alias.
_HINTS: tuple[tuple[str, str], ...] = (
    ("readOnlyHint", "read_only_hint"),
    ("destructiveHint", "destructive_hint"),
    ("idempotentHint", "idempotent_hint"),
    ("openWorldHint", "open_world_hint"),
)


class DeclaredAnnotations(TypedDict, total=False):
    """The hints a server declared for one tool; a hint it left out is absent, since "not declared" is not "false"."""

    readOnlyHint: bool
    destructiveHint: bool
    idempotentHint: bool
    openWorldHint: bool


def _hint(source: object, wire_name: str, attribute: str) -> object:
    if isinstance(source, Mapping):
        return source.get(wire_name, source.get(attribute))
    return getattr(source, attribute, getattr(source, wire_name, None))


def _booleans(source: object) -> DeclaredAnnotations:
    """The hints ``source`` states as a boolean; anything else a server sends in their place is not a declaration."""
    return cast(
        DeclaredAnnotations,
        {name: value for name, attribute in _HINTS if isinstance(value := _hint(source, name, attribute), bool)},
    )


def declared_annotations(tool: object) -> DeclaredAnnotations:
    """The declarations of an SDK ``Tool``; empty when its server declared none."""
    return _booleans(getattr(tool, "annotations", None))


def recorded_annotations(tool: object) -> DeclaredAnnotations:
    """The declarations a converted tool carries; empty when its server declared none."""
    metadata = getattr(tool, "metadata", None)
    return _booleans(metadata.get(ANNOTATIONS_METADATA_KEY)) if isinstance(metadata, Mapping) else {}


def judge(declared: DeclaredAnnotations, *, host_serial: bool) -> tuple[SafetyMetadata, MCPAnnotations]:
    """Turn a tool's declarations into the host's safety record and the claims worth showing a person.

    Only ``is_concurrent_safe`` is ever raised, and only for a tool that declares itself read-only without declaring
    itself destructive on a server the operator did not pin to one call at a time. A tool declaring both is
    contradicting itself, so it counts as destructive and does not run in parallel. ``is_read_only`` and
    ``is_idempotent`` stay false whatever a server declares: approval, the read-only sandbox, the script gates, the
    replay and cache rules all read them, and a self-report must not open any of those.

    Returns the record to register and the claim slot, which holds only claims that make a person more careful.
    """
    destructive = declared.get("destructiveHint") is True
    claims: MCPAnnotations = {}
    if destructive:
        claims["destructiveHint"] = True
    if declared.get("openWorldHint") is True:
        claims["openWorldHint"] = True
    concurrent_safe = declared.get("readOnlyHint") is True and not destructive and not host_serial
    return SafetyMetadata(is_concurrent_safe=concurrent_safe, is_destructive=destructive), claims
