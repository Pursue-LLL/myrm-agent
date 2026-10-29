"""MCP verify and scan response models.

[INPUT]
- myrm_agent_harness.toolkits.mcp.security::MCPConfigScanResult, MCPRuntimeScanResult (POS: Scan results the response models are built from)

[OUTPUT]
- MCPToolDetail, MCPScanFindingData, MCPScanData, MCPVerifyData
- scan_result_to_data: maps a harness scan result onto MCPScanData

[POS]
Response models of the verify and scan endpoints in ``app.api.integrations.mcp.inspection``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.mcp.security import MCPConfigScanResult, MCPRuntimeScanResult


class MCPToolDetail(BaseModel):
    """Single MCP tool metadata returned by the verify endpoint."""

    name: str
    description: str = ""
    read_only_hint: bool = False
    destructive_hint: bool = False
    idempotent_hint: bool = False
    open_world_hint: bool = False

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class MCPScanFindingData(BaseModel):
    """Single MCP security scan finding."""

    threat_type: str
    severity: str
    description: str
    field: str = ""
    recommendation: str = ""

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class MCPScanData(BaseModel):
    """Static MCP configuration scan result."""

    server_name: str
    allow_save: bool
    requires_acknowledgement: bool
    max_severity: str | None = None
    findings: list[MCPScanFindingData] = Field(default_factory=list)

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class MCPVerifyData(BaseModel):
    """MCP verification response model."""

    tools_count: int = Field(..., description="Available tool count")
    service_name: str = Field(..., description="Service name")
    instructions: str | None = Field(default=None, description="MCP server instructions")
    tools: list[MCPToolDetail] = Field(default_factory=list, description="Tool metadata list")
    config_scan: MCPScanData | None = Field(default=None, description="Static config scan summary")
    runtime_scan: MCPScanData | None = Field(default=None, description="Runtime surface scan summary")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


def scan_result_to_data(
    result: MCPConfigScanResult | MCPRuntimeScanResult,
    *,
    allow_save: bool,
    requires_acknowledgement: bool,
) -> MCPScanData:
    return MCPScanData(
        server_name=result.server_name,
        allow_save=allow_save,
        requires_acknowledgement=requires_acknowledgement,
        max_severity=result.max_severity.value if result.max_severity else None,
        findings=[
            MCPScanFindingData(
                threat_type=finding.threat_type,
                severity=finding.severity.value,
                description=finding.description,
                field=finding.field,
                recommendation=finding.recommendation,
            )
            for finding in result.findings
        ],
    )
