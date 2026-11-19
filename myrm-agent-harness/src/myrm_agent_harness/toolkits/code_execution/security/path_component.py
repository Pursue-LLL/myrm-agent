"""Path-component validation for identifiers that become directory names (user_id, chat_id, workspace_id).

[INPUT]
- security.validator::ValidationResult (POS: Structured outcome shared by the execution security validators)

[OUTPUT]
- validate_path_component / is_path_component_safe: Reject components that could traverse or escape a workspace root.

[POS]
Path-component validator. Guards every identifier the workspace layer turns into a directory name.
"""

import re

from myrm_agent_harness.toolkits.code_execution.security.validator import ValidationResult


def validate_path_component(component: str, component_name: str = "path component") -> ValidationResult:
    """Validate a path component for safety (user_id, chat_id, workspace_id, etc.).

    Prevents path traversal attacks and filesystem restriction bypass.

    Args:
        component: Path component to validate.
        component_name: Component name for error messages.

    Returns:
        ValidationResult with validation outcome.

    Rules:
    - Only alphanumeric, hyphen (-), underscore (_) allowed
    - No path separators (/, \\)
    - No path traversal (..)
    - Cannot start with dot (hidden files)
    - Length: 1-255 characters
    """
    if not component:
        return ValidationResult(
            is_safe=False,
            reason=f"Invalid {component_name}: empty value",
            blocked_item=component,
        )

    if len(component) > 255:
        return ValidationResult(
            is_safe=False,
            reason=f"Invalid {component_name}: exceeds maximum length (255 characters)",
            blocked_item=component,
        )

    if component.startswith("."):
        return ValidationResult(
            is_safe=False,
            reason=f"Invalid {component_name}: cannot start with '.'",
            blocked_item=component,
        )

    if ".." in component:
        return ValidationResult(
            is_safe=False,
            reason=f"Invalid {component_name}: contains path traversal pattern '..'",
            blocked_item=component,
        )

    if "/" in component or "\\" in component:
        return ValidationResult(
            is_safe=False,
            reason=f"Invalid {component_name}: contains path separator",
            blocked_item=component,
        )

    if not re.match(r"^[a-zA-Z0-9_-]+$", component):
        return ValidationResult(
            is_safe=False,
            reason=f"Invalid {component_name}: contains invalid characters (only alphanumeric, '-', '_' allowed)",
            blocked_item=component,
        )

    return ValidationResult(is_safe=True)


def is_path_component_safe(component: str, component_name: str = "path component") -> bool:
    """Check if a path component is safe (convenience wrapper)."""
    return validate_path_component(component, component_name).is_safe


__all__ = [
    "is_path_component_safe",
    "validate_path_component",
]
