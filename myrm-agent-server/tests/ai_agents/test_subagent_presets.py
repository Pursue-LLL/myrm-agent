"""Boundary tests for the business-owned subagent preset catalog."""

from pathlib import Path

import pytest
import yaml

from app.ai_agents import subagent_presets
from app.ai_agents.subagent_presets import (
    SUBAGENT_CONFIG_DIR,
    USER_SELECTABLE_SUBAGENT_IDS,
    load_subagent_presets,
    load_user_selectable_subagent_configs,
    required_builtin_tools,
)

_OFFICE_TEMPLATE = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_agents" / "office_delivery_blueprint.yaml"


def test_user_selectable_catalog_is_explicit_and_metadata_complete():
    configs = load_user_selectable_subagent_configs()

    assert list(configs) == list(USER_SELECTABLE_SUBAGENT_IDS)
    assert "adversarial-reviewer" not in configs
    for config in configs.values():
        assert config.description
        assert config.tools


def test_office_structure_and_layout_presets_are_read_only():
    configs = load_user_selectable_subagent_configs()

    structure = configs["structure-planner"]
    assert structure.theme_color == "blue"
    assert "file_read_tool" in structure.tools
    assert {"file_write_tool", "file_edit_tool"}.issubset(structure.disallowed_tools)

    layout = configs["layout-designer"]
    assert layout.theme_color == "purple"
    assert "file_read_tool" in layout.tools
    assert {"file_write_tool", "file_edit_tool"}.issubset(layout.disallowed_tools)


def test_format_verifier_is_read_only_without_native_shell():
    config = load_user_selectable_subagent_configs()["format-verifier"]

    assert "bash_code_execute_tool" not in config.tools
    assert "bash_process_tool" not in config.tools
    assert "bash_code_execute_tool" in config.disallowed_tools


def test_browser_preset_declares_its_parent_builtin_dependency():
    configs = load_user_selectable_subagent_configs()

    assert required_builtin_tools(configs["browser"]) == ("browser",)
    assert required_builtin_tools(configs["explore"]) == ()


def test_office_template_subagents_are_resolvable_presets():
    template = yaml.safe_load(_OFFICE_TEMPLATE.read_text(encoding="utf-8"))
    configs = load_user_selectable_subagent_configs()

    assert template["subagent_ids"] == ["structure-planner", "layout-designer", "format-verifier"]
    assert set(template["subagent_ids"]).issubset(configs)


def test_user_selectable_ids_are_loaded_from_core_not_duplicated():
    core_files = {path.stem for path in (SUBAGENT_CONFIG_DIR / "core").glob("*.yaml")}

    assert set(USER_SELECTABLE_SUBAGENT_IDS).issubset(core_files)


def _write_preset(directory: Path, name: str, description: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "description": description,
                "tools": [],
                "system_prompt": f"You are the {name} preset agent.",
                "config": {},
            }
        ),
        encoding="utf-8",
    )


def test_shipped_core_presets_all_load():
    presets = load_subagent_presets()

    assert {path.stem for path in (SUBAGENT_CONFIG_DIR / "core").glob("*.yaml")}.issubset(presets)


def test_custom_preset_overrides_core_preset_of_the_same_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _write_preset(tmp_path / "core", "shared", "from core")
    _write_preset(tmp_path / "core", "core-only", "from core")
    _write_preset(tmp_path / "custom", "shared", "from custom")
    monkeypatch.setattr(subagent_presets, "SUBAGENT_CONFIG_DIR", tmp_path)

    presets = load_subagent_presets()

    assert set(presets) == {"shared", "core-only"}
    assert presets["shared"].description == "from custom"


def test_missing_custom_directory_leaves_the_core_presets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _write_preset(tmp_path / "core", "core-only", "from core")
    monkeypatch.setattr(subagent_presets, "SUBAGENT_CONFIG_DIR", tmp_path)

    assert set(load_subagent_presets()) == {"core-only"}
