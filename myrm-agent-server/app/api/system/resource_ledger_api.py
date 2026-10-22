"""
[INPUT]
- fastapi::{APIRouter, HTTPException, status}
- pydantic::{BaseModel, Field}
- myrm_agent_harness.observability.resource_metering::{
    BudgetCircuitBreaker,
    CognitiveUsage,
    HardwareUsage,
    HybridLedgerReport,
    ResourceMeteringLedger,
  }

[OUTPUT]
- router: APIRouter for hybrid compute-cognitive resource ledger and metering
- HardwareUsageDTO, CognitiveUsageDTO, HybridLedgerReportDTO, ResourceEstimateRequest

[POS]
app/api/system/resource_ledger_api.py — 物理硬件占用与认知 Token 混合开销全景对账单 HTTP 端点与预估。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, status
from myrm_agent_harness.observability.resource_metering import (
    BudgetCircuitBreaker,
    CognitiveUsage,
    HardwareUsage,
    HybridLedgerReport,
    ResourceMeteringLedger,
)
from pydantic import BaseModel, Field

router = APIRouter(tags=["system-resource-ledger"])
_ledger = ResourceMeteringLedger()


class HardwareUsageDTO(BaseModel):
    """物理硬件占用数据传输对象。"""

    execution_seconds: float
    cpu_cores: float
    memory_gb: float
    volume_read_mb: float
    volume_write_mb: float
    hardware_credits: float


class CognitiveUsageDTO(BaseModel):
    """大模型认知计算占用数据传输对象。"""

    model_name: str
    prompt_tokens: int
    completion_tokens: int
    cached_prompt_tokens: int
    cognitive_credits: float


class HybridLedgerReportDTO(BaseModel):
    """物理与认知双轨全景对账单传输对象。"""

    task_id: str
    hardware: HardwareUsageDTO
    cognitive: CognitiveUsageDTO
    total_credits: float
    estimated_cost_usd: float
    is_budget_exceeded: bool
    budget_exceeded_reason: str
    created_at: float


class ResourceEstimateRequest(BaseModel):
    """资源与预算计量预估请求参数。"""

    task_id: str = Field(..., min_length=1, description="任务标识符")
    execution_seconds: float = Field(60.0, ge=0.0, description="预估沙箱执行时间(秒)")
    cpu_cores: float = Field(2.0, ge=0.5, le=32.0, description="沙箱 CPU 核数配额")
    memory_gb: float = Field(4.0, ge=0.5, le=128.0, description="沙箱内存规格(GB)")
    volume_read_mb: float = Field(0.0, ge=0.0, description="持久卷读取 MB")
    volume_write_mb: float = Field(0.0, ge=0.0, description="持久卷写入 MB")
    model_name: str = Field("deepseek-v3", description="目标模型名称")
    prompt_tokens: int = Field(10000, ge=0, description="预估 Prompt Token 数")
    completion_tokens: int = Field(2000, ge=0, description="预估 Completion Token 数")
    cached_prompt_tokens: int = Field(0, ge=0, description="预估 Prompt Cache 命中数")
    max_execution_seconds: Optional[float] = Field(None, ge=0.0, description="最大允许执行时长阈值(秒)")
    max_total_tokens: Optional[int] = Field(None, ge=0, description="最大允许 Token 预算配额")
    max_total_credits: Optional[float] = Field(None, ge=0.0, description="最大允许总积分限额")


def _report_to_dto(report: HybridLedgerReport) -> HybridLedgerReportDTO:
    """转换为 Pydantic DTO。"""
    return HybridLedgerReportDTO(
        task_id=report.task_id,
        hardware=HardwareUsageDTO(
            execution_seconds=report.hardware.execution_seconds,
            cpu_cores=report.hardware.cpu_cores,
            memory_gb=report.hardware.memory_gb,
            volume_read_mb=report.hardware.volume_read_mb,
            volume_write_mb=report.hardware.volume_write_mb,
            hardware_credits=report.hardware.hardware_credits,
        ),
        cognitive=CognitiveUsageDTO(
            model_name=report.cognitive.model_name,
            prompt_tokens=report.cognitive.prompt_tokens,
            completion_tokens=report.cognitive.completion_tokens,
            cached_prompt_tokens=report.cognitive.cached_prompt_tokens,
            cognitive_credits=report.cognitive.cognitive_credits,
        ),
        total_credits=report.total_credits,
        estimated_cost_usd=report.estimated_cost_usd,
        is_budget_exceeded=report.is_budget_exceeded,
        budget_exceeded_reason=report.budget_exceeded_reason,
        created_at=report.created_at,
    )


@router.get(
    "/resource-ledger/{task_id}",
    response_model=HybridLedgerReportDTO,
    status_code=status.HTTP_200_OK,
    summary="查询单任务物理硬件占用与认知 Token 混合开销全景对账单",
)
async def get_task_resource_ledger(task_id: str) -> HybridLedgerReportDTO:
    """查询指定任务的多维硬件时长与认知算力统一对账明细。"""
    # 模拟构建真实长程任务对账单 (例如 11 分钟 2C/4G 沙箱 + 25k tokens)
    hw = HardwareUsage(
        execution_seconds=660.0,
        cpu_cores=2.0,
        memory_gb=4.0,
        volume_read_mb=128.0,
        volume_write_mb=64.0,
    )
    cog = CognitiveUsage(
        model_name="deepseek-v3",
        prompt_tokens=25000,
        completion_tokens=4500,
        cached_prompt_tokens=15000,
    )
    report = _ledger.generate_task_report(task_id=task_id, hardware=hw, cognitive=cog)
    return _report_to_dto(report)


@router.post(
    "/resource-ledger/estimate",
    response_model=HybridLedgerReportDTO,
    status_code=status.HTTP_200_OK,
    summary="对标火山方舟 AFP 协议：任务级混合算力消耗与成本预估及预算熔断预检",
)
async def estimate_resource_ledger(
    request: ResourceEstimateRequest,
) -> HybridLedgerReportDTO:
    """预估指定任务的硬件时长与认知 Token 综合积分、预估法币投入及预算超支熔断判定。"""
    hw = HardwareUsage(
        execution_seconds=request.execution_seconds,
        cpu_cores=request.cpu_cores,
        memory_gb=request.memory_gb,
        volume_read_mb=request.volume_read_mb,
        volume_write_mb=request.volume_write_mb,
    )
    cog = CognitiveUsage(
        model_name=request.model_name,
        prompt_tokens=request.prompt_tokens,
        completion_tokens=request.completion_tokens,
        cached_prompt_tokens=request.cached_prompt_tokens,
    )
    breaker = BudgetCircuitBreaker(
        max_execution_seconds=request.max_execution_seconds,
        max_total_tokens=request.max_total_tokens,
        max_total_credits=request.max_total_credits,
    )
    report = _ledger.generate_task_report(
        task_id=request.task_id,
        hardware=hw,
        cognitive=cog,
        circuit_breaker=breaker,
    )
    return _report_to_dto(report)
