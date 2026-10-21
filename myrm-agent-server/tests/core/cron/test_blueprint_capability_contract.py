"""Contract: a blueprint's declared capabilities cover every tool its prompt tells the agent to use.

An unattended job is fenced to its declared capabilities, so a prompt that names a tool the declaration
does not grant fails on its first call instead of doing its work.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.engine import evaluate_tool_call
from myrm_agent_harness.agent.security.types import PermissionAction
from myrm_agent_harness.core.security.tool_registry import resolve_permission_type

from app.core.cron.blueprints import BUILTIN_BLUEPRINTS, CronBlueprint, get_blueprint

_TOOL_NAME_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)*_tool)\b")


@pytest.mark.parametrize("blueprint", BUILTIN_BLUEPRINTS, ids=lambda bp: bp.id)
def test_declared_capabilities_cover_tools_named_in_prompts(blueprint: CronBlueprint) -> None:
    declared = set(blueprint.default_required_capabilities)
    for locale, prompt in blueprint.prompt_template.items():
        uncovered = {
            name: permission
            for name in sorted(set(_TOOL_NAME_RE.findall(prompt)))
            if (permission := resolve_permission_type(name, {})) not in declared
        }
        assert not uncovered, f"{blueprint.id}[{locale}] names tools its capabilities do not grant: {uncovered}"


def test_wiki_morning_delta_declares_knowledge_and_raw_scan_capabilities() -> None:
    blueprint = next(bp for bp in BUILTIN_BLUEPRINTS if bp.id == "wiki_morning_delta")
    assert set(blueprint.default_required_capabilities) == {"file_read", "knowledge_read", "knowledge_write"}


@pytest.mark.parametrize(
    ("blueprint_id", "target"),
    [
        ("seo_weekly_audit", "artifacts/SEO-OPTIMIZATION-ROADMAP.md"),
        ("viral_quote_discovery", "docs/marketing/viral_quotes_AI Agent.md"),
    ],
)
def test_blueprints_that_save_a_file_can_write_it_unattended(blueprint_id: str, target: str, tmp_path: Path) -> None:
    """Their last step saves a file, which an unattended job can do only when its declaration names file_write."""
    blueprint = get_blueprint(blueprint_id)
    assert blueprint is not None
    config = build_channel_security_config("cron", declared_capabilities=blueprint.default_required_capabilities)

    action, reason = evaluate_tool_call(
        "file_write", {"path": target}, config, workspace_root=str(tmp_path), tool_name="file_write_tool"
    )

    assert action == PermissionAction.ALLOW, reason
