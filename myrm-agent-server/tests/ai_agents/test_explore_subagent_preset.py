"""
[POS] tests/ai_agents/test_explore_subagent_preset.py
[INPUT] pathlib.Path, myrm_agent_harness.agent.sub_agents.config_loader, myrm_agent_harness.agent.tool_management.tool_layers
[OUTPUT] test_explore_yaml_exists_and_loads, test_explore_tool_shadowing_and_permissions, test_explore_sandbox_and_budget_constraints, test_explore_prompt_contract_and_citations, test_explore_batch_loading_discovery

Unit test suite verifying the strict read-only 'explore' subagent preset
with tool shadowing, sandbox safety, and zero context pollution.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.agent.sub_agents.budget_scaling import DEFAULT_SCALED_CONCURRENCY
from myrm_agent_harness.agent.sub_agents.config_loader import (
    SubagentConfigLoader,
    load_subagent_configs_from_directory,
)
from myrm_agent_harness.agent.sub_agents.types import (
    MemoryIsolationPolicy,
    SubagentConfig,
    WorkspacePolicy,
)
from myrm_agent_harness.agent.tool_management.tool_layers import is_registered_action_tool


def _get_explore_yaml_path() -> Path:
    """Resolve absolute path to core explore.yaml subagent preset."""
    root_dir = Path(__file__).resolve().parent.parent.parent
    return root_dir / "app" / "config" / "subagents" / "core" / "explore.yaml"


def test_explore_yaml_exists_and_loads() -> None:
    """Verify explore.yaml exists and can be validated and parsed into SubagentConfig."""
    yaml_path = _get_explore_yaml_path()
    assert yaml_path.exists(), f"Configuration file not found at: {yaml_path}"

    loader = SubagentConfigLoader()
    config = loader.load_from_yaml(yaml_path, expected_name="explore")

    assert config is not None
    assert isinstance(config, SubagentConfig)
    assert config.description != ""
    assert "read-only" in config.description.lower()
    assert config.display_name == "Codebase Explorer"
    assert config.theme_color == "cyan"


def test_explore_tool_shadowing_and_permissions() -> None:
    """Verify tool shadowing strictly enforces read-only whitelist and blocks destructive tools."""
    loader = SubagentConfigLoader()
    config = loader.load_from_yaml(_get_explore_yaml_path(), expected_name="explore")
    assert config is not None

    # 1. Whitelist of permitted tools (only read-only discovery)
    allowed_tools = set(config.tools)
    assert allowed_tools == {"file_read_tool", "grep_tool", "glob_tool"}

    # 2. Blacklist / disallowed tools (strips all writes, code execution, and ACP/skills)
    disallowed = set(config.disallowed_tools)
    must_be_disallowed = {
        "file_write_tool",
        "file_edit_tool",
        "bash_code_execute_tool",
        "bash_process_tool",
        "skill_manage_tool",
        "skill_market_tool",
        "invoke_acp_agent_tool",
    }
    assert must_be_disallowed.issubset(disallowed)

    # 3. Disjoint set: No tool in whitelist can be in blacklist
    assert allowed_tools.isdisjoint(disallowed)

    # 4. Action Tool SSOT validation: all tools must be registered in tool_layers
    for tool_name in allowed_tools | disallowed:
        assert is_registered_action_tool(tool_name), f"Tool '{tool_name}' must be registered in Action Tool SSOT"


def test_explore_sandbox_and_budget_constraints() -> None:
    """Verify workspace policy is read_only_sandbox and budget/turn limits are strictly bounded."""
    loader = SubagentConfigLoader()
    config = loader.load_from_yaml(_get_explore_yaml_path(), expected_name="explore")
    assert config is not None

    # Sandbox isolation
    assert config.workspace_policy == WorkspacePolicy.READ_ONLY_SANDBOX
    assert config.memory_isolation == MemoryIsolationPolicy.EPHEMERAL_SESSION
    assert config.context_mode == "isolated"
    assert config.max_spawn_depth == 0

    # Performance and cost constraints
    assert config.timeout_seconds == 60
    assert config.max_turns == 15
    assert config.budget_tokens == 100000
    assert config.max_result_tokens == 8000
    # ConfigUpgradeMigrator treats 3/5 as legacy defaults and lifts them to the scaled
    # default, so the preset's own 5 never reaches the runtime config.
    assert config.concurrency_limit == DEFAULT_SCALED_CONCURRENCY


def test_explore_prompt_contract_and_citations() -> None:
    """Verify system prompt enforces read-only safety, zero noise, and exact [path:line] citations."""
    loader = SubagentConfigLoader()
    config = loader.load_from_yaml(_get_explore_yaml_path(), expected_name="explore")
    assert config is not None

    prompt = config.system_prompt
    assert "READ-ONLY SAFETY" in prompt
    assert "ZERO MAIN-CHAT NOISE" in prompt
    assert "EVIDENCE-DRIVEN CITATIONS" in prompt
    assert "[path:start-end]" in prompt or "[path:line" in prompt
    assert "OUTPUT CONTRACT" in prompt
    assert "架构定位与职责概述" in prompt
    assert "关键符号与调用链图" in prompt


def test_explore_batch_loading_discovery() -> None:
    """Verify explore preset is discovered by batch directory loading."""
    core_dir = _get_explore_yaml_path().parent
    configs = load_subagent_configs_from_directory(core_dir)

    assert "explore" in configs
    explore_cfg = configs["explore"]
    assert explore_cfg.display_name == "Codebase Explorer"
    assert "file_read_tool" in explore_cfg.tools
    assert "file_write_tool" in explore_cfg.disallowed_tools
