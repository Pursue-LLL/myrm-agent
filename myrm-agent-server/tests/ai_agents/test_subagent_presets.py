"""Boundary tests for the business-owned subagent preset catalog."""

from pathlib import Path
from unittest.mock import patch

import yaml
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

from app.ai_agents.subagent_presets import (
    SUBAGENT_CONFIG_DIR,
    USER_SELECTABLE_SUBAGENT_IDS,
    load_user_selectable_subagent_configs,
    register_default_subagent_configs,
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


def test_register_default_subagent_configs_registers_merged_sources():
    config = SubagentConfig(system_prompt="test")
    with (
        patch(
            "app.ai_agents.subagent_presets.load_subagent_configs_from_directory",
            side_effect=[{"core": config}, {"custom": SubagentConfig(system_prompt="custom")}],
        ),
        patch("app.ai_agents.subagent_presets.register_subagent_configs") as register,
    ):
        register_default_subagent_configs()

    register.assert_called_once()
    registered = register.call_args.args[0]
    assert set(registered) == {"core", "custom"}


def test_register_default_subagent_configs_handles_empty_catalog():
    with (
        patch(
            "app.ai_agents.subagent_presets.load_subagent_configs_from_directory",
            return_value={},
        ),
        patch("app.ai_agents.subagent_presets.register_subagent_configs") as register,
    ):
        register_default_subagent_configs()

    register.assert_called_once_with({})


def test_register_default_subagent_configs_contains_load_failure():
    with (
        patch(
            "app.ai_agents.subagent_presets.load_subagent_configs_from_directory",
            side_effect=RuntimeError("broken yaml"),
        ),
        patch("app.ai_agents.subagent_presets.register_subagent_configs") as register,
    ):
        register_default_subagent_configs()

    register.assert_not_called()
