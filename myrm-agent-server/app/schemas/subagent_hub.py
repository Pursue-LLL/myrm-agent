"""
[INPUT]
- pydantic (BaseModel, Field)
- typing (Literal)

[OUTPUT]
- SubagentWorkerStatusLiteral: 子代理状态字面量
- SupervisionActionLiteral: 监管动作字面量 (steer | kill | revive)
- SubagentWorkerRosterItemDTO: 单个子代理花名册条目 DTO
- SubagentRosterOverviewResponseDTO: 会话级花名册概览响应 DTO
- SupervisionTranscriptEntryDTO: 单条实时执行轨迹 DTO
- SubagentTranscriptResponseDTO: 子代理轨迹响应 DTO
- SupervisionActionRequestDTO: 监管动作请求 DTO
- SupervisionActionResponseDTO: 监管动作响应 DTO

[POS]
Server 业务层子代理实时监管抽屉数据契约（Topic 12 · 第 18 项）。
对齐 oh-my-pi Agent Hub 架构，支持 live transcript、成本/活动聚合以及 steer/kill/revive 动作。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SubagentWorkerStatusLiteral = Literal[
    "running",
    "parked",
    "stuck",
    "done",
    "failed",
    "interrupted",
]

SupervisionActionLiteral = Literal[
    "steer",
    "kill",
    "revive",
]


class SubagentWorkerRosterItemDTO(BaseModel):
    """单个子代理花名册条目 DTO。"""

    task_id: str = Field(..., description="子代理任务唯一标识")
    agent_type: str = Field(..., description="子代理角色类型")
    status: SubagentWorkerStatusLiteral = Field(..., description="当前生命周期状态")
    current_activity: str = Field(default="", description="当前正在执行的具体行为描述")
    model: str = Field(default="default", description="运行所使用的模型标识")
    tokens_used: int = Field(default=0, ge=0, description="已消耗的 Token 数")
    elapsed_seconds: float = Field(default=0.0, ge=0.0, description="已累计运行秒数")
    last_tool: str = Field(default="", description="最近调用的工具名称")
    can_steer: bool = Field(default=True, description="是否支持注入纠偏指令")
    can_kill: bool = Field(default=True, description="是否支持终止该工作者")
    can_revive: bool = Field(default=False, description="是否支持从检查点恢复")
    description: str = Field(default="", description="任务初始描述")
    created_at: str = Field(..., description="创建时间 ISO 格式字符串")


class SubagentRosterOverviewResponseDTO(BaseModel):
    """会话级子代理花名册全景与成本概览响应 DTO。"""

    session_id: str = Field(..., description="所属主会话 ID")
    total_workers: int = Field(..., ge=0, description="子代理总数")
    active_workers: int = Field(..., ge=0, description="运行中活跃子代理数")
    parked_workers: int = Field(..., ge=0, description="已停靠休眠的子代理数")
    stuck_workers: int = Field(..., ge=0, description="挂死/可疑超时的子代理数")
    total_tokens: int = Field(..., ge=0, description="全量子代理累计 Token 消耗")
    total_duration_seconds: float = Field(..., ge=0.0, description="最长/总运行耗时秒数")
    workers: list[SubagentWorkerRosterItemDTO] = Field(
        default_factory=list, description="子代理花名册列表"
    )


class SupervisionTranscriptEntryDTO(BaseModel):
    """单条实时执行轨迹 DTO。"""

    entry_id: str = Field(..., description="轨迹记录唯一 ID")
    timestamp: str = Field(..., description="产生时间戳 ISO 字符串")
    tool_name: str = Field(..., description="执行的工具名称")
    input_summary: str = Field(..., description="工具输入参数摘要")
    output_summary: str = Field(..., description="工具执行结果摘要")
    level: Literal["info", "warn", "error"] = Field(default="info", description="日志严重度等级")
    duration_ms: int | None = Field(default=None, description="工具调用耗时毫秒数")


class SubagentTranscriptResponseDTO(BaseModel):
    """子代理实时执行轨迹响应 DTO。"""

    task_id: str = Field(..., description="子代理任务唯一标识")
    total_entries: int = Field(..., ge=0, description="轨迹记录总数")
    entries: list[SupervisionTranscriptEntryDTO] = Field(
        default_factory=list, description="有序执行轨迹列表"
    )


class SupervisionActionRequestDTO(BaseModel):
    """监管控制动作请求 DTO。"""

    action: SupervisionActionLiteral = Field(
        ..., description="监管动作：steer (纠偏) | kill (终止) | revive (恢复)"
    )
    message: str = Field(default="", description="纠偏指令消息内容 (steer 时必填)")


class SupervisionActionResponseDTO(BaseModel):
    """监管控制动作响应 DTO。"""

    task_id: str = Field(..., description="被操作的子代理任务 ID")
    action: SupervisionActionLiteral = Field(..., description="执行的监管动作")
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="操作反馈说明文案")
    new_status: SubagentWorkerStatusLiteral = Field(..., description="操作后的新状态")
