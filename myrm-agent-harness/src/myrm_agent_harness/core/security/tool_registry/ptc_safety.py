"""Dynamic safety metadata of MCP tools reached through the PTC proxy.

[INPUT]
- safety_table::SafetyMetadata (POS: tool safety attribute model)

[OUTPUT]
- MCPAnnotations: native MCP tool annotations (hint flags)
- register_ptc_safety_metadata / get_ptc_safety_metadata / unregister_ptc_safety_metadata / evict_skill_safety_metadata: thread-safe per-skill registration, lookup and eviction
- _PTC_SAFETY_METADATA / _PTC_TOOL_FLAT_INDEX / _PTC_LOCK: the per-skill tree, the flat name index read by ``resolve_safety_metadata``, and the lock guarding both

[POS]
Process-wide store filled when an MCP server's tools are discovered and read when a tool call is scheduled or
approved. It is split out of ``registry.py`` to keep that file under the line limit; ``registry.py`` re-exports
every symbol so the flat import surface is unchanged.
"""

from __future__ import annotations

import threading
from typing import TypedDict

from .safety_table import SafetyMetadata


class MCPAnnotations(TypedDict, total=False):
    """Native MCP tool annotations."""

    readOnlyHint: bool
    idempotentHint: bool
    destructiveHint: bool
    thirdPartyVisibleHint: bool
    openWorldHint: bool


_PTC_SAFETY_METADATA: dict[str, dict[str, tuple[SafetyMetadata, MCPAnnotations]]] = {}

# Flat index for O(1) lookup by tool_name, consumed by resolve_safety_metadata.
_PTC_TOOL_FLAT_INDEX: dict[str, SafetyMetadata] = {}

# Thread lock protecting dynamic PTC safety registry mutations
_PTC_LOCK = threading.RLock()


def register_ptc_safety_metadata(
    skill_name: str,
    tool_name: str,
    safety_meta: SafetyMetadata,
    annotations: MCPAnnotations,
) -> None:
    """Register dynamically extracted safety metadata for an MCP tool."""
    with _PTC_LOCK:
        if skill_name not in _PTC_SAFETY_METADATA:
            _PTC_SAFETY_METADATA[skill_name] = {}
        _PTC_SAFETY_METADATA[skill_name][tool_name] = (safety_meta, annotations)
        _PTC_TOOL_FLAT_INDEX[tool_name] = safety_meta


def get_ptc_safety_metadata(skill_name: str, tool_name: str) -> tuple[SafetyMetadata, MCPAnnotations] | None:
    """Retrieve dynamic safety metadata for an MCP tool."""
    with _PTC_LOCK:
        return _PTC_SAFETY_METADATA.get(skill_name, {}).get(tool_name)


def unregister_ptc_safety_metadata(skill_name: str, tool_name: str) -> bool:
    """Unregister dynamic safety metadata for a single tool under a skill.

    Returns True if the tool was found and removed, False otherwise.
    """
    with _PTC_LOCK:
        skill_tools = _PTC_SAFETY_METADATA.get(skill_name)
        if not skill_tools or tool_name not in skill_tools:
            return False
        del skill_tools[tool_name]
        if not skill_tools:
            _PTC_SAFETY_METADATA.pop(skill_name, None)
        _PTC_TOOL_FLAT_INDEX.pop(tool_name, None)
        return True


def evict_skill_safety_metadata(skill_name: str) -> int:
    """Evict all dynamic safety metadata registered under the given skill.

    Returns the number of tools evicted.
    """
    with _PTC_LOCK:
        skill_tools = _PTC_SAFETY_METADATA.pop(skill_name, None)
        if not skill_tools:
            return 0
        for tool_name in skill_tools:
            _PTC_TOOL_FLAT_INDEX.pop(tool_name, None)
        return len(skill_tools)
