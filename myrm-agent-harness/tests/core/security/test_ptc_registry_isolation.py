"""The autouse conftest fixture hands every test an empty dynamic MCP safety registry.

The two tests are order dependent on purpose: the second one only passes when the registration made
by the first one was cleared between tests.
"""

from myrm_agent_harness.core.security.tool_registry import (
    SafetyMetadata,
    get_ptc_safety_metadata,
    register_ptc_safety_metadata,
    resolve_safety_metadata,
)

_SKILL = "isolation_probe_skill"
_TOOL = "isolation_probe_tool"


def test_registration_is_visible_inside_the_registering_test() -> None:
    register_ptc_safety_metadata(
        _SKILL,
        _TOOL,
        SafetyMetadata(is_read_only=True, is_concurrent_safe=True),
        {"readOnlyHint": True},
    )

    assert get_ptc_safety_metadata(_SKILL, _TOOL) is not None
    assert resolve_safety_metadata(_TOOL).is_read_only is True


def test_registration_from_the_previous_test_is_gone() -> None:
    assert get_ptc_safety_metadata(_SKILL, _TOOL) is None
    assert resolve_safety_metadata(_TOOL).is_read_only is False
