"""Tests for plugin sandbox capability tiers, risk levels, and capability diff in preview."""

from __future__ import annotations

from myrm_agent_harness.agent.plugins.models import (
    AgentPluginManifestMeta,
    PluginCapabilityTier,
    PluginMcpServer,
    PluginParseResult,
)

from app.services.plugins._preview import (
    build_preview_result,
    compute_capability_diff,
)


def test_compute_capability_diff_escalation_detection() -> None:
    # Adding shell_exec is an escalation
    diff = compute_capability_diff(
        old_capabilities={"read_only", "fs_read"},
        new_capabilities={"read_only", "fs_read", "shell_exec"},
    )
    assert diff["added"] == ["shell_exec"]
    assert diff["removed"] == []
    assert diff["has_escalation"] is True

    # Adding destructive is an escalation
    diff_destr = compute_capability_diff(
        old_capabilities={"shell_exec", "network"},
        new_capabilities={"shell_exec", "network", "destructive"},
    )
    assert diff_destr["added"] == ["destructive"]
    assert diff_destr["has_escalation"] is True

    # Removing permissions or keeping safe is NOT an escalation
    diff_safe = compute_capability_diff(
        old_capabilities={"shell_exec", "network"},
        new_capabilities={"network"},
    )
    assert diff_safe["added"] == []
    assert diff_safe["removed"] == ["shell_exec"]
    assert diff_safe["has_escalation"] is False


def test_build_preview_result_includes_capabilities_and_risk_levels() -> None:
    meta = AgentPluginManifestMeta(
        name="test-plugin",
        version="1.0.0",
        declared_capabilities=(PluginCapabilityTier.NETWORK,),
    )
    server_remote = PluginMcpServer(
        name="remote-srv",
        server_type="streamable_http",
        command=None,
        args=None,
        url="https://api.example.com",
        headers=None,
        cwd=None,
        capabilities=(PluginCapabilityTier.NETWORK,),
    )
    server_stdio = PluginMcpServer(
        name="local-srv",
        server_type="stdio",
        command="./runner.sh",
        args=None,
        url=None,
        headers=None,
        cwd=None,
        capabilities=(
            PluginCapabilityTier.SHELL_EXEC,
            PluginCapabilityTier.FS_WRITE,
        ),
    )

    parse_result = PluginParseResult(
        meta=meta,
        servers=[server_remote, server_stdio],
    )

    preview = build_preview_result(
        parse_result,
        installed_capabilities={"read_only"},
    )

    plugin_info = preview["plugin"]
    assert isinstance(plugin_info, dict)
    assert plugin_info["declared_capabilities"] == ["network"]
    assert "network" in plugin_info["capabilities"]
    assert "shell_exec" in plugin_info["capabilities"]
    assert plugin_info["effective_tier"] == "shell_exec"
    assert plugin_info["risk_level"] == "high"

    # Verify capability_diff is populated and flagged escalation
    diff = plugin_info["capability_diff"]
    assert isinstance(diff, dict)
    assert diff["has_escalation"] is True
    assert "shell_exec" in diff["added"]

    # Verify servers list has capabilities
    servers = preview["servers"]
    assert len(servers) == 2
    assert servers[0]["capabilities"] == ["network"]
    assert "shell_exec" in servers[1]["capabilities"]
