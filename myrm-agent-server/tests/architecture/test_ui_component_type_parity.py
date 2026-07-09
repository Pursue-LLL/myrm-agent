"""Architecture test: Python UIComponentType must match frontend TS union and registry."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from myrm_agent_harness.agent.artifacts.ui_artifact import UIComponentType
from myrm_agent_harness.agent.meta_tools.interaction.a2ui_spec import allowed_component_type_names

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_MYRM_AGENT_ROOT = _SERVER_ROOT.parent
_FRONTEND_TYPES = _MYRM_AGENT_ROOT / "myrm-agent-frontend" / "src" / "store" / "chat" / "types" / "interactiveUi.ts"
_FRONTEND_REGISTRY = (
    _MYRM_AGENT_ROOT
    / "myrm-agent-frontend"
    / "src"
    / "components"
    / "features"
    / "interactive-ui"
    / "UIComponentRegistry.tsx"
)


def _parse_ts_ui_component_types(content: str) -> frozenset[str]:
    match = re.search(r"export type UIComponentType\s*=\s*(.+?);", content, re.DOTALL)
    assert match is not None, "UIComponentType union not found in interactiveUi.ts"
    return frozenset(re.findall(r"'([^']+)'", match.group(1)))


def _parse_registry_component_types(content: str) -> frozenset[str]:
    match = re.search(
        r"const componentRegistry: Record<UIComponentType, UIComponentRenderer> = \{([^}]+)\}",
        content,
        re.DOTALL,
    )
    assert match is not None, "componentRegistry block not found in UIComponentRegistry.tsx"
    return frozenset(re.findall(r"^\s*([a-z_]+):", match.group(1), re.MULTILINE))


@pytest.mark.architecture
def test_python_ui_component_type_matches_frontend_union() -> None:
    python_types = frozenset(allowed_component_type_names())
    ts_types = _parse_ts_ui_component_types(_FRONTEND_TYPES.read_text(encoding="utf-8"))

    missing_in_ts = sorted(python_types - ts_types)
    missing_in_python = sorted(ts_types - python_types)

    assert not missing_in_ts, f"Python UIComponentType missing in TS union: {missing_in_ts}"
    assert not missing_in_python, f"TS UIComponentType missing in Python enum: {missing_in_python}"
    assert len(python_types) == len(UIComponentType)


@pytest.mark.architecture
def test_frontend_registry_covers_all_ui_component_types() -> None:
    ts_types = _parse_ts_ui_component_types(_FRONTEND_TYPES.read_text(encoding="utf-8"))
    registry_types = _parse_registry_component_types(_FRONTEND_REGISTRY.read_text(encoding="utf-8"))

    missing_renderers = sorted(ts_types - registry_types)
    extra_renderers = sorted(registry_types - ts_types)

    assert not missing_renderers, f"UIComponentRegistry missing renderers: {missing_renderers}"
    assert not extra_renderers, f"UIComponentRegistry has unknown types: {extra_renderers}"
