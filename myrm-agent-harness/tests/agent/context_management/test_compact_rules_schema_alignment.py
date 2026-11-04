"""Compaction rules must name arguments the live tool schemas actually define.

A rule keyed on an argument the tool does not have silently falls back to the generic identifier priority list,
which does not know plural list arguments (``urls``, ``skill_names``) and ends in ``tool_call_<id>`` placeholders.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_repo_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import scripts.measure_turn1_token_inventory as measure
from myrm_agent_harness.agent.context_management.strategies.compactor.compact_rules import COMPACT_RULES

# Rules for tools the default Turn-1 profile mounts; the profile is the only place the live schemas are built offline.
_MIN_COVERED_TOOLS = 6


@pytest.mark.asyncio
async def test_compact_rule_arguments_exist_in_the_live_tool_schemas() -> None:
    tools = await measure._build_default_turn1_tools()

    covered = 0
    for tool in tools:
        rule = COMPACT_RULES.get(tool.name)
        if rule is None:
            continue
        covered += 1
        schema_args = set(tool.args)
        assert rule.identifier_arg in schema_args, (
            f"{tool.name}: identifier_arg {rule.identifier_arg!r} is not a schema argument {sorted(schema_args)}"
        )
        assert set(rule.keep_args) <= schema_args, (
            f"{tool.name}: keep_args {rule.keep_args} are not all schema arguments {sorted(schema_args)}"
        )

    assert covered >= _MIN_COVERED_TOOLS
