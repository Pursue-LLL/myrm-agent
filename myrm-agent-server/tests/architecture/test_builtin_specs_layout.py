"""Architecture test: built-in agent specs live in a dedicated subpackage."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_AGENT_SERVICES_ROOT = _SERVER_ROOT / "app" / "services" / "agent"
_BUILTIN_SPECS_PACKAGE = _AGENT_SERVICES_ROOT / "builtin_specs"

_REQUIRED_MODULE_FILES = (
    "__init__.py",
    "_ARCH.md",
    "types.py",
    "core.py",
    "search.py",
    "extended.py",
    "vertical.py",
)

_FORBIDDEN_LEGACY_FLAT_FILES = (
    "builtin_agent_spec_types.py",
    "builtin_agent_specs_core.py",
    "builtin_agent_specs_search.py",
    "builtin_agent_specs_extended.py",
    "builtin_agent_specs_vertical.py",
)


@pytest.mark.architecture
def test_builtin_specs_subpackage_layout() -> None:
    assert _BUILTIN_SPECS_PACKAGE.is_dir(), (
        f"Missing {_BUILTIN_SPECS_PACKAGE}. See app/services/agent/builtin_specs/_ARCH.md."
    )
    for filename in _REQUIRED_MODULE_FILES:
        path = _BUILTIN_SPECS_PACKAGE / filename
        assert path.is_file(), f"Missing required builtin_specs module file: {path}"


@pytest.mark.architecture
@pytest.mark.parametrize("legacy_filename", _FORBIDDEN_LEGACY_FLAT_FILES)
def test_builtin_specs_legacy_flat_files_removed(legacy_filename: str) -> None:
    legacy_path = _AGENT_SERVICES_ROOT / legacy_filename
    assert not legacy_path.exists(), (
        f"Legacy flat builtin specs file must not reappear: {legacy_path}. "
        "Use app/services/agent/builtin_specs/ instead."
    )


@pytest.mark.architecture
def test_builtin_specs_public_facade_at_agent_root() -> None:
    facade_path = _AGENT_SERVICES_ROOT / "builtin_agent_specs.py"
    assert facade_path.is_file(), (
        "Public aggregation facade must remain at app/services/agent/builtin_agent_specs.py"
    )


@pytest.mark.architecture
def test_builtin_agents_tuple_integrity() -> None:
    from app.services.agent.builtin_agent_specs import _BUILTIN_AGENTS

    assert len(_BUILTIN_AGENTS) == 26
    ids = [spec.id for spec in _BUILTIN_AGENTS]
    assert len(ids) == len(set(ids)), f"Duplicate builtin agent ids: {ids}"
