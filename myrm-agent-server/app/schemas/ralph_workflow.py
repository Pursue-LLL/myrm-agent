"""
[INPUT]
- pydantic (BaseModel, Field)
- typing (Literal)

[OUTPUT]
- RalphHandoffStatusLiteral: 轮次交接状态字面量类型
- RalphHandoffReportDTO: 结构化五字段交接报告 DTO
- RalphRoundRecordDTO: 单轮历史记录凭据 DTO
- CreateRalphSessionRequestDTO: 创建 Ralph 循环会话请求 DTO
- AdvanceRalphRoundRequestDTO: 提交本轮交接并推进轮次请求 DTO
- RalphSessionResponseDTO: Ralph 会话全量状态响应 DTO

[POS]
Server 业务层 Ralph 式 Fresh-Agent 多轮循环 REST API 数据契约（Topic 12 · 第 15 项）。
严格对齐 DSH Ralph 模式五字段强契约与 Min-3-Round 阻断防御规范，零 Any 类型。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RalphHandoffStatusLiteral = Literal["in_progress", "blocked", "completed"]


class RalphHandoffReportDTO(BaseModel):
    """Ralph 模式结构化五字段交接报告 DTO。"""

    status: RalphHandoffStatusLiteral = Field(
        ...,
        description="本轮执行结果状态：in_progress | blocked | completed",
    )
    summary: str = Field(..., min_length=1, description="本轮工作极简执行摘要")
    evidence: str = Field(..., description="产物凭据或测试输出 (路径或日志)")
    next_steps: str = Field(..., description="指引下一轮 Fresh 子 Agent 的具体操作要求")
    blocker: str = Field(default="", description="若声称 blocked 时的阻塞原因描述")


class RalphRoundRecordDTO(BaseModel):
    """单个 Fresh Agent 轮次的历史记录 DTO。"""

    round_index: int = Field(..., ge=1, description="轮次序号 (从 1 起始)")
    child_session_id: str = Field(..., description="本轮 Fresh 子 Agent 的独立会话 ID")
    handoff: RalphHandoffReportDTO = Field(..., description="本轮提交的五字段交接报告")
    created_at: float = Field(..., description="轮次完成时间戳")
    duration_seconds: float = Field(default=0.0, description="本轮耗时 (秒)")
    tokens_consumed: int = Field(default=0, description="本轮消耗 Token 数")
    was_blocked_downgraded: bool = Field(
        default=False,
        description="是否因未满 3 轮门槛而触发 blocked -> in_progress 防御降级",
    )


class CreateRalphSessionRequestDTO(BaseModel):
    """创建 Ralph 多轮循环工作流请求 DTO。"""

    human_goal: str = Field(..., min_length=1, description="人类锁定的根本任务目标（不可篡改）")
    workspace_root: str = Field(default="/workspace", description="共享工作区物理绝对路径")
    max_rounds: int = Field(default=10, ge=1, le=50, description="最大允许执行轮次")
    min_rounds_before_blocked: int = Field(
        default=3,
        ge=1,
        le=10,
        description="允许声称 blocked 的最小轮次门槛",
    )


class AdvanceRalphRoundRequestDTO(BaseModel):
    """提交轮次产物并推进下一轮 Fresh Agent 启动请求 DTO。"""

    child_session_id: str = Field(..., description="当前轮次子 Agent 会话 ID")
    handoff: RalphHandoffReportDTO = Field(..., description="本轮产生的五字段交接报告")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="执行耗时 (秒)")
    tokens_consumed: int = Field(default=0, ge=0, description="消耗 Token 数")


class RalphSessionResponseDTO(BaseModel):
    """Ralph 多轮循环会话全量状态响应 DTO。"""

    session_id: str = Field(..., description="Ralph 循环主会话 ID")
    human_goal: str = Field(..., description="人类根本任务目标")
    workspace_root: str = Field(..., description="跨轮共享工作区路径")
    current_round: int = Field(..., ge=1, description="当前或下一待执行轮次序号")
    max_rounds: int = Field(..., description="最大轮次上限")
    min_rounds_before_blocked: int = Field(..., description="最小尝试阻断门槛")
    status: RalphHandoffStatusLiteral = Field(..., description="全局聚合状态")
    rounds: list[RalphRoundRecordDTO] = Field(default_factory=list, description="历次轮次记录列表")
    next_directive: str | None = Field(default=None, description="为下一轮 Fresh Agent 装配的全新启动指令")
