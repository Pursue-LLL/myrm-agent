"""Permission type and safety attributes of the tools a host application defines outside the harness.

[INPUT]
- governance::DYNAMICALLY_RESOLVED_TOOL_NAMES, EXPLICIT_MCP_FALLBACK_TOOLS (POS: built-in tools whose permission is resolved by sub-action or deliberately asks)
- safety_table::SafetyMetadata (POS: tool safety attribute model)
- registry::BUILTIN_TOOL_NAMES, TOOL_PERMISSION_MAP (POS: built-in tool SSOT; imported inside the function because ``registry`` imports this module)

[OUTPUT]
- declare_external_tool: state the permission type and safety attributes of one tool defined outside the harness
- declared_permission_type / declared_safety_metadata: what a tool declared, ``None`` when it declared nothing

[POS]
An undeclared tool resolves to ``mcp_invoke`` (ask) with fail-closed safety attributes, which is right for a tool
whose effects the harness cannot know. A host that ships a tool with known effects declares it here once, at startup,
so the tool is governed like the built-in tools of that kind. A declaration reuses a permission type the built-in
tools already use, so it cannot create a type no rule covers, and it cannot take over a built-in or MCP tool name.
"""

from __future__ import annotations

import threading

from .governance import DYNAMICALLY_RESOLVED_TOOL_NAMES, EXPLICIT_MCP_FALLBACK_TOOLS
from .safety_table import SafetyMetadata

_DECLARATIONS: dict[str, tuple[str, SafetyMetadata]] = {}
_LOCK = threading.Lock()


def declare_external_tool(tool_name: str, permission_type: str, safety: SafetyMetadata) -> None:
    """Declare how ``tool_name`` is governed. Declaring the same values again is a no-op.

    Raises:
        ValueError: the name belongs to a built-in or MCP tool, the permission type is not one the built-in tools
            use, or the tool was already declared with other values.
    """
    from .registry import BUILTIN_TOOL_NAMES, TOOL_PERMISSION_MAP

    reserved = BUILTIN_TOOL_NAMES | EXPLICIT_MCP_FALLBACK_TOOLS | DYNAMICALLY_RESOLVED_TOOL_NAMES
    if not tool_name or tool_name in reserved or tool_name.startswith("mcp__"):
        raise ValueError(f"Tool name {tool_name!r} cannot be declared: it is empty, built-in or an MCP tool")
    if permission_type not in frozenset(TOOL_PERMISSION_MAP.values()):
        raise ValueError(
            f"Unknown permission type {permission_type!r}: a declaration reuses one the built-in tools use"
        )
    declaration = (permission_type, safety)
    with _LOCK:
        existing = _DECLARATIONS.setdefault(tool_name, declaration)
    if existing != declaration:
        raise ValueError(f"Tool {tool_name!r} is already declared as {existing[0]!r}")


def declared_permission_type(tool_name: str) -> str | None:
    """The permission type ``tool_name`` declared, or ``None``."""
    declaration = _DECLARATIONS.get(tool_name)
    return declaration[0] if declaration else None


def declared_safety_metadata(tool_name: str) -> SafetyMetadata | None:
    """The safety attributes ``tool_name`` declared, or ``None``."""
    declaration = _DECLARATIONS.get(tool_name)
    return declaration[1] if declaration else None
