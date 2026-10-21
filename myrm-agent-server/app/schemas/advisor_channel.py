"""
[INPUT]
- pydantic (BaseModel, Field)
- typing (Literal)

[OUTPUT]
- AdvisorLevelLiteral: 旁路军师干预层级字面量 (aside | concern | blocker)
- AdvisorInterventionDTO: 单项干预建议条目 DTO
- AdvisorReviewStepRequestDTO: 单步动作旁路审查请求 DTO
- AdvisorReviewResultDTO: 单步审查判定结果 DTO
- AdvisorSessionReviewsResponseDTO: 会话级历史审查记录响应 DTO

[POS]
Server 业务层双模型实时旁路军师评审通道数据契约（Topic 12 · 第 17 项）。
对齐 oh-my-pi 架构，严格定义 aside/concern/blocker 三级干预协议与审查结果，杜绝 Any 类型。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AdvisorLevelLiteral = Literal["aside", "concern", "blocker"]


class AdvisorInterventionDTO(BaseModel):
    """单项旁路军师干预建议 DTO。"""

    intervention_id: str = Field(..., description="干预唯一标识 ID")
    level: AdvisorLevelLiteral = Field(
        ...,
        description="干预层级：aside (旁白提示) | concern (担忧预警) | blocker (硬性阻断)",
    )
    title: str = Field(..., min_length=1, description="干预标题")
    message: str = Field(..., min_length=1, description="审查详尽阐述与风险成因")
    suggested_action: str | None = Field(default=None, description="建议主模型采取的纠偏动作")
    created_at: float = Field(..., description="生成时间戳")
    duration_ms: float = Field(default=0.0, description="审查耗时 (毫秒)")
    tokens_used: int = Field(default=0, description="Advisor 消耗的 Token 数")


class AdvisorReviewStepRequestDTO(BaseModel):
    """单步动作旁路审查请求 DTO。"""

    session_id: str = Field(..., min_length=1, description="关联的智能体会话 ID")
    task_goal: str = Field(..., min_length=1, description="主任务根本目标（不可篡改）")
    tool_name: str = Field(..., min_length=1, description="主模型调用的工具名称")
    tool_args: dict[str, str] = Field(default_factory=dict, description="工具入参字典")
    turn_index: int = Field(default=1, ge=1, description="当前轮次序号")


class AdvisorReviewResultDTO(BaseModel):
    """单步动作旁路审查判定结果 DTO。"""

    is_blocked: bool = Field(..., description="是否触发 blocker 硬阻断（熔断主 Agent 执行）")
    highest_level: AdvisorLevelLiteral | None = Field(
        default=None,
        description="本次动作检出的最高干预等级",
    )
    interventions: list[AdvisorInterventionDTO] = Field(
        default_factory=list,
        description="结构化干预建议列表",
    )
    summary: str = Field(default="", description="审查决策摘要")


class AdvisorSessionReviewsResponseDTO(BaseModel):
    """指定会话的全量旁路审查记录响应 DTO。"""

    session_id: str = Field(..., description="智能体会话 ID")
    total_reviews: int = Field(..., ge=0, description="审查总次数")
    blocked_count: int = Field(..., ge=0, description="触发 blocker 硬阻断的次数")
    interventions: list[AdvisorInterventionDTO] = Field(
        default_factory=list,
        description="该会话累计的所有干预建议历史",
    )
