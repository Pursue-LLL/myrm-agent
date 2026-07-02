"""Pydantic helpers for enabled_builtin_tools validation.

[INPUT]
- .builtin_tool_ids::normalize_enabled_builtin_tools (POS: canonical tool ID validation)

[OUTPUT]
- OptionalBuiltinTools / RequiredBuiltinTools: Annotated Pydantic field types

[POS]
Reusable Pydantic BeforeValidator hooks for enabled_builtin_tools fields.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from pydantic import BeforeValidator

from app.services.agent.builtin_tool_ids import (
    DEFAULT_ENABLED_BUILTIN_TOOLS,
    normalize_enabled_builtin_tools,
)


def _validate_optional_builtin_tools(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        msg = "enabled_builtin_tools must be a list of tool IDs"
        raise TypeError(msg)
    return normalize_enabled_builtin_tools([str(item) for item in value])


def _validate_required_builtin_tools(value: object) -> list[str]:
    if value is None:
        return list(DEFAULT_ENABLED_BUILTIN_TOOLS)
    if not isinstance(value, (list, tuple)):
        msg = "enabled_builtin_tools must be a list of tool IDs"
        raise TypeError(msg)
    return normalize_enabled_builtin_tools([str(item) for item in value])


OptionalBuiltinTools = Annotated[
    list[str] | None,
    BeforeValidator(_validate_optional_builtin_tools),
]

RequiredBuiltinTools = Annotated[
    list[str],
    BeforeValidator(_validate_required_builtin_tools),
]
