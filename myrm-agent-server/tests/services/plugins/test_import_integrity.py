"""Tests for plugin packaging integrity enforcement in the Server business layer."""

from __future__ import annotations

from unittest.mock import MagicMock

from myrm_agent_harness.agent.plugins.models import PluginMcpServer

from app.services.plugins._mcp_persist import _collect_server_configs
from app.services.plugins._models import PluginConfirmItem, PluginImportSession


def test_collect_server_configs_skips_server_with_missing_build_artifacts() -> None:
    broken_server = PluginMcpServer(
        name="broken-server",
        server_type="stdio",
        command="node",
        args=["./dist/index.js"],
        url=None,
        headers=None,
        cwd=None,
        is_runnable=False,
        missing_artifact="dist/index.js",
    )
    valid_server = PluginMcpServer(
        name="valid-server",
        server_type="stdio",
        command="./server.py",
        args=None,
        url=None,
        headers=None,
        cwd=None,
        is_runnable=True,
        missing_artifact=None,
    )

    session = PluginImportSession(
        plugin_result=MagicMock(),
        servers_by_key={
            "mcp:0": broken_server,
            "mcp:1": valid_server,
        },
    )

    decisions = [
        PluginConfirmItem(component="mcp:broken-server", virtual_id="mcp:0", resolution="install", name="broken-server"),
        PluginConfirmItem(component="mcp:valid-server", virtual_id="mcp:1", resolution="install", name="valid-server"),
    ]

    configs, skipped = _collect_server_configs(
        session,
        decisions,
        plugin_name="test-plugin",
    )

    # Broken server must be skipped, only valid server is allowed
    assert skipped == 1
    assert len(configs) == 1
    assert configs[0]["name"] == "valid-server"


def test_build_preview_result_includes_runnability_and_missing_artifacts() -> None:
    from myrm_agent_harness.agent.plugins.models import (
        PluginDiagnostic,
        PluginDiagnosticLevel,
        PluginParseResult,
    )

    from app.services.plugins._preview import build_preview_result

    broken = PluginMcpServer(
        name="broken-node",
        server_type="stdio",
        command="node",
        args=["./dist/index.js"],
        url=None,
        headers=None,
        cwd=None,
        is_runnable=False,
        missing_artifact="dist/index.js",
        missing_artifacts=("./dist/index.js",),
    )
    result = PluginParseResult(
        servers=[broken],
        diagnostics=[
            PluginDiagnostic(
                component="mcp:broken-node",
                code="mcp_missing_artifact",
                message="Missing dist/index.js",
                level=PluginDiagnosticLevel.WARNING,
            )
        ],
    )
    preview = build_preview_result(result)
    assert len(preview["servers"]) == 1
    server_preview = preview["servers"][0]
    assert server_preview["is_runnable"] is False
    assert server_preview["missing_artifact"] == "dist/index.js"
    assert server_preview["missing_artifacts"] == ["./dist/index.js"]


def test_build_preview_result_capability_diff_and_tiers() -> None:
    from myrm_agent_harness.agent.plugins.models import (
        AgentPluginManifestMeta,
        PluginCapabilityTier,
        PluginParseResult,
    )

    from app.services.plugins._preview import build_preview_result, compute_capability_diff

    # Test pure compute_capability_diff
    diff_res = compute_capability_diff({"read_only"}, {"read_only", "shell_exec"})
    assert diff_res["added"] == ["shell_exec"]
    assert diff_res["has_escalation"] is True

    diff_safe = compute_capability_diff({"read_only", "fs_read"}, {"read_only"})
    assert diff_safe["removed"] == ["fs_read"]
    assert diff_safe["has_escalation"] is False

    # Test build_preview_result with installed capabilities
    manifest_meta = AgentPluginManifestMeta(
        name="test-escalation",
        declared_capabilities=(PluginCapabilityTier.SHELL_EXEC,),
    )
    result = PluginParseResult(meta=manifest_meta)
    preview = build_preview_result(
        result,
        installed_capabilities={"read_only"},
    )
    assert preview["plugin"]["effective_tier"] == "shell_exec"
    assert preview["plugin"]["risk_level"] == "high"
    diff = preview["plugin"]["capability_diff"]
    assert diff is not None
    assert diff["has_escalation"] is True
    assert "shell_exec" in diff["added"]


