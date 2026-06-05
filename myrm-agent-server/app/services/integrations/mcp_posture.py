"""MCP integration security posture orchestration.

[INPUT]
- myrm_agent_harness.toolkits.mcp.security (POS: static/runtime MCP scanners)

[OUTPUT]
- mcp_config_to_snapshot(): MCPServerConfig → MCPConfigSnapshot
- resolve_mcp_config_scan(): static scan + OSV advisory
- enforce_mcp_config_posture(): static scan gate (critical block + high acknowledgement)
- enforce_mcp_runtime_posture(): runtime surface scan gate
- mcp_findings_to_error_details(): findings → API ErrorDetail JSON for GUI i18n
- raise_mcp_posture_validation_error(): posture block with structured error details
- with_osv_malware_finding(): append OSV malware advisory to scan result

[POS]
Business-layer MCP security orchestration. Converts server DTOs to harness
snapshots and raises validation errors when posture checks fail.
"""

from __future__ import annotations

import json
import logging

from myrm_agent_harness.toolkits.mcp.security import (
    MCPConfigScanResult,
    MCPConfigSnapshot,
    MCPRuntimeScanResult,
    MCPRuntimeToolSurface,
    MCPScanFinding,
    MCPScanSeverity,
    check_osv_malware,
    format_mcp_scan_block_message,
    scan_mcp_config,
    scan_mcp_runtime_surface,
)

from app.core.types import MCPServerConfig
from app.core.utils.errors import validation_error
from app.database.standard_responses import ErrorDetail

logger = logging.getLogger(__name__)

_MCP_FINDING_DETAIL_LIMIT = 8


def mcp_findings_to_error_details(
    findings: tuple[MCPScanFinding, ...],
) -> list[ErrorDetail]:
    """Serialize scan findings into API error details for frontend i18n mapping."""
    return [
        ErrorDetail(
            field=finding.field or finding.threat_type,
            issue=json.dumps(
                {
                    "threatType": finding.threat_type,
                    "severity": finding.severity.value,
                    "description": finding.description,
                    "recommendation": finding.recommendation,
                }
            ),
        )
        for finding in findings[:_MCP_FINDING_DETAIL_LIMIT]
    ]


def raise_mcp_posture_validation_error(
    result: MCPConfigScanResult | MCPRuntimeScanResult,
) -> None:
    """Raise validation_error with structured findings for GUI i18n."""
    raise validation_error(
        format_mcp_scan_block_message(result),
        details=mcp_findings_to_error_details(result.findings),
    )


def mcp_config_to_snapshot(config: MCPServerConfig) -> MCPConfigSnapshot:
    """Convert business MCP config to harness scan snapshot."""
    return MCPConfigSnapshot(
        name=config.name,
        type=config.type,
        url=config.url,
        command=config.command,
        args=tuple(config.args or ()),
        description=config.description,
        headers=dict(config.headers) if config.headers else None,
        extra_params=dict(config.extra_params) if config.extra_params else None,
    )


def run_mcp_config_scan(config: MCPServerConfig) -> MCPConfigScanResult:
    """Run static MCP configuration scan without raising."""
    return scan_mcp_config(mcp_config_to_snapshot(config))


async def resolve_mcp_config_scan(config: MCPServerConfig) -> MCPConfigScanResult:
    """Run static scan and append OSV malware advisory for stdio commands."""
    result = run_mcp_config_scan(config)
    if config.command:
        advisory = await check_osv_malware(config.command, config.args)
        result = with_osv_malware_finding(result, advisory)
    return result


def enforce_mcp_config_posture(
    config: MCPServerConfig,
    *,
    acknowledged_high_risks: bool = False,
    result: MCPConfigScanResult | None = None,
) -> MCPConfigScanResult:
    """Static pre-flight scan. Blocks critical findings and unacknowledged high risks."""
    scan_result = result if result is not None else run_mcp_config_scan(config)
    if not scan_result.allow_save:
        logger.warning(
            "MCP config posture blocked: %s (%d findings)",
            config.name,
            len(scan_result.findings),
        )
        raise_mcp_posture_validation_error(scan_result)
    has_high = any(f.severity == MCPScanSeverity.HIGH for f in scan_result.findings)
    if has_high and not acknowledged_high_risks:
        logger.warning(
            "MCP config posture requires acknowledgement: %s (%d findings)",
            config.name,
            len(scan_result.findings),
        )
        raise validation_error(f"MCP security scan requires acknowledgement for high-risk findings on '{config.name}'")
    return scan_result


def run_mcp_runtime_scan(
    config: MCPServerConfig,
    *,
    instructions: str | None,
    tools: list[tuple[str, str]],
) -> MCPRuntimeScanResult:
    """Scan MCP instructions, tool names, and tool descriptions."""
    surfaces = tuple(MCPRuntimeToolSurface(name=name, description=description) for name, description in tools)
    return scan_mcp_runtime_surface(config.name, instructions=instructions, tools=surfaces)


def enforce_mcp_runtime_posture(
    config: MCPServerConfig,
    *,
    instructions: str | None,
    tools: list[tuple[str, str]],
) -> MCPRuntimeScanResult:
    """Runtime surface scan. Raises validation_error on high/critical findings."""
    result = run_mcp_runtime_scan(config, instructions=instructions, tools=tools)
    if not result.allow_use:
        logger.warning(
            "MCP runtime posture blocked: %s (%d findings)",
            config.name,
            len(result.findings),
        )
        raise_mcp_posture_validation_error(result)
    return result


def with_osv_malware_finding(
    result: MCPConfigScanResult,
    advisory: str | None,
) -> MCPConfigScanResult:
    """Append OSV malware advisory as a critical finding when present."""
    if not advisory:
        return result
    finding = MCPScanFinding(
        threat_type="supply_chain_malware",
        severity=MCPScanSeverity.CRITICAL,
        description=advisory,
        field="command",
        recommendation="Remove the flagged package and use a pinned, verified dependency",
    )
    return MCPConfigScanResult(
        server_name=result.server_name,
        findings=result.findings + (finding,),
    )
