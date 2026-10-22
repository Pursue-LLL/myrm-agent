"""
[INPUT]
- pydantic (BaseModel, Field)

[OUTPUT]
- McpToolCandidateDTO, EmployeeToolScopePolicyDTO, McpDiscoveryCheckResultDTO
- ScopedMcpFilterRequestDTO, ScopedMcpFilterVerdictDTO
- VerifyToolCallRequestDTO, VerifyToolCallResponseDTO

[POS]
Server 业务层 MCP 发现工具按数字员工/Agent 作用域严格隔离门禁数据契约（Topic 12 · 第 20 项）。
定义数字员工 MCP 白名单策略、动态发现候选集过滤请求/响应与单次调用鉴权 DTO，杜绝 Any 类型。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class McpToolCandidateDTO(BaseModel):
    """待判定的 MCP 工具候选条目 DTO。"""

    server_name: str = Field(..., description="所属 MCP 服务器名称")
    tool_name: str = Field(..., description="候选工具名称")
    description: str = Field(default="", description="工具功能描述文本")


class EmployeeToolScopePolicyDTO(BaseModel):
    """数字员工/Agent 的 MCP 工具作用域策略 DTO。"""

    agent_id: str = Field(..., description="关联的智能体/数字员工 ID")
    allowed_mcp_servers: list[str] = Field(
        default_factory=list, description="允许访问的 MCP 服务器名称白名单"
    )
    tool_allowlist_map: dict[str, list[str]] = Field(
        default_factory=dict,
        description="针对特定 Server 的工具级细粒度白名单映射 (server_name -> [tool_name, ...])",
    )
    strict_mode: bool = Field(
        default=True, description="是否启用严格模式 (未授权即默认 Fail-Closed 阻断)"
    )
    updated_at: str = Field(default="", description="策略更新时间 ISO 格式")


class McpDiscoveryCheckResultDTO(BaseModel):
    """单个工具的作用域校验结果 DTO。"""

    server_name: str = Field(..., description="MCP 服务器名称")
    tool_name: str = Field(..., description="工具名称")
    is_allowed: bool = Field(..., description="是否允许该 Agent 发现/调用")
    reason: str = Field(..., description="放行或阻断判定的具体策略原因")
    description: str = Field(default="", description="工具功能描述")


class ScopedMcpFilterRequestDTO(BaseModel):
    """动态发现工具批量过滤请求 DTO。"""

    candidates: list[McpToolCandidateDTO] = Field(
        ..., description="动态发现的全部候选 MCP 工具清单"
    )


class ScopedMcpFilterVerdictDTO(BaseModel):
    """数字员工作用域过滤门禁裁决响应 DTO。"""

    agent_id: str = Field(..., description="智能体 ID")
    total_discovered: int = Field(..., ge=0, description="发现的候选工具总数")
    allowed_count: int = Field(..., ge=0, description="授权放行的工具数")
    blocked_count: int = Field(..., ge=0, description="物理裁剪拦截的未授权工具数")
    allowed_tools: list[McpDiscoveryCheckResultDTO] = Field(
        default_factory=list, description="授权工具白名单清单"
    )
    blocked_tools: list[McpDiscoveryCheckResultDTO] = Field(
        default_factory=list, description="拦截遮蔽工具清单"
    )


class VerifyToolCallRequestDTO(BaseModel):
    """单次 MCP 工具调用鉴权请求 DTO。"""

    server_name: str = Field(..., description="目标 MCP 服务器名称")
    tool_name: str = Field(..., description="调用的目标工具名称")


class VerifyToolCallResponseDTO(BaseModel):
    """单次 MCP 工具调用鉴权响应 DTO。"""

    agent_id: str = Field(..., description="调用方智能体 ID")
    server_name: str = Field(..., description="目标 MCP 服务器名称")
    tool_name: str = Field(..., description="调用的目标工具名称")
    is_allowed: bool = Field(..., description="是否允许调用")
    reason: str = Field(..., description="放行或拦截说明")
