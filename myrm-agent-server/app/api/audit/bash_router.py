"""Bash审计日志REST API

提供bash命令执行审计日志的查询和统计功能。
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/audit/bash", tags=["audit"])


class BashAuditLog(BaseModel):
    """Bash审计日志记录"""

    sequence: int = Field(description="事件序列号")
    timestamp: float = Field(description="时间戳（UTC Unix timestamp）")
    command: str = Field(description="命令（已脱敏）")
    exit_code: int = Field(description="退出码")
    stdout: str = Field(description="标准输出（截断）")
    stderr: str = Field(description="标准错误（截断）")
    duration_ms: int = Field(description="执行时长（毫秒）")
    success: bool = Field(description="是否成功")
    command_type: str = Field(description="命令类型")
    risk_level: str = Field(description="风险级别")
    error_message: str | None = Field(default=None, description="错误消息（如果有）")


class BashExecutionStatsResponse(BaseModel):
    """Bash执行统计响应"""

    total_commands: int = Field(description="总命令数")
    success_rate: float = Field(description="成功率")
    avg_duration_ms: float = Field(description="平均执行时长（毫秒）")
    error_top10: list[tuple[str, int]] = Field(description="错误Top10")
    command_hotmap: list[tuple[str, int]] = Field(description="命令热度Top10")
    type_distribution: dict[str, int] = Field(description="命令类型分布")
    hourly_breakdown: list[tuple[int, int]] = Field(description="按小时统计")


@router.get("/logs", response_model=list[BashAuditLog])
async def get_bash_audit_logs(
    start_time: float | None = Query(None, description="开始时间（UTC timestamp）"),
    end_time: float | None = Query(None, description="结束时间（UTC timestamp）"),
    command_type: str | None = Query(None, description="命令类型"),
    risk_level: str | None = Query(None, description="风险级别"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
    truncate: bool = Query(True, description="是否截断输出（默认True，截断到500字符）"),
) -> list[BashAuditLog]:
    """查询bash审计日志

    Args:
        start_time: 开始时间（UTC timestamp）
        end_time: 结束时间（UTC timestamp）
        command_type: 命令类型过滤（READ/WRITE/DANGEROUS/etc.）
        risk_level: 风险级别过滤（LOW/MEDIUM/HIGH）
        limit: 返回数量限制（1-1000）

    Returns:
        审计日志列表
    """
    try:
        from myrm_agent_harness.api.hooks import get_event_logger

        event_logger = get_event_logger()
        if not event_logger:
            raise HTTPException(status_code=503, detail="Event logger not available")

        # 调用框架层API
        events = await event_logger.get_bash_audit_logs(
            start_time=start_time,
            end_time=end_time,
            command_type=command_type,
            risk_level=risk_level,
            limit=limit,
        )

        # 转换为API响应格式
        logs: list[BashAuditLog] = []
        for event in events:
            data = event.data
            stdout = str(data.get("stdout", ""))
            stderr = str(data.get("stderr", ""))

            # 如果需要截断，限制到500字符
            if truncate:
                stdout = stdout[:500]
                stderr = stderr[:500]

            logs.append(
                BashAuditLog(
                    sequence=event.sequence,
                    timestamp=event.timestamp,
                    command=str(data.get("command", "")),
                    exit_code=int(data.get("exit_code", 0)),
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=int(data.get("duration_ms", 0)),
                    success=bool(data.get("success", False)),
                    command_type=str(data.get("command_type", "UNKNOWN")),
                    risk_level=str(data.get("risk_level", "LOW")),
                    error_message=str(data.get("error_message", "")) if data.get("error_message") else None,
                )
            )

        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query audit logs: {e}") from e


@router.get("/stats", response_model=BashExecutionStatsResponse)
async def get_bash_execution_stats() -> BashExecutionStatsResponse:
    """获取bash执行统计

    Returns:
        bash执行统计数据
    """
    try:
        from myrm_agent_harness.api.hooks import get_event_logger

        event_logger = get_event_logger()
        if not event_logger:
            raise HTTPException(status_code=503, detail="Event logger not available")

        # 调用框架层API
        stats = await event_logger.get_bash_execution_stats()

        return BashExecutionStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get execution stats: {e}") from e


@router.get("/export")
async def export_bash_audit_logs(
    format: Literal["json", "csv"] = Query("json", description="导出格式"),
    start_time: float | None = Query(None, description="开始时间（UTC timestamp）"),
    end_time: float | None = Query(None, description="结束时间（UTC timestamp）"),
) -> Response:
    """导出bash审计日志

    Args:
        format: 导出格式（json或csv）
        start_time: 开始时间（UTC timestamp）
        end_time: 结束时间（UTC timestamp）

    Returns:
        导出的文件内容
    """
    try:
        from myrm_agent_harness.api.hooks import get_event_logger

        event_logger = get_event_logger()
        if not event_logger:
            raise HTTPException(status_code=503, detail="Event logger not available")

        # 获取审计日志
        events = await event_logger.get_bash_audit_logs(
            start_time=start_time,
            end_time=end_time,
            limit=10000,  # 导出时不限制
        )

        if format == "json":
            import json

            from fastapi.responses import Response

            data = [event.to_dict() for event in events]
            return Response(content=json.dumps(data, indent=2), media_type="application/json")
        else:  # csv
            import csv
            import io

            from fastapi.responses import Response

            output = io.StringIO()
            if events:
                fieldnames = [
                    "sequence",
                    "timestamp",
                    "command",
                    "exit_code",
                    "success",
                    "command_type",
                    "risk_level",
                    "duration_ms",
                ]
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                for event in events:
                    data = event.data
                    writer.writerow(
                        {
                            "sequence": event.sequence,
                            "timestamp": event.timestamp,
                            "command": data.get("command", ""),
                            "exit_code": data.get("exit_code", 0),
                            "success": data.get("success", False),
                            "command_type": data.get("command_type", "UNKNOWN"),
                            "risk_level": data.get("risk_level", "LOW"),
                            "duration_ms": data.get("duration_ms", 0),
                        }
                    )

            return Response(content=output.getvalue(), media_type="text/csv")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export audit logs: {e}") from e


@router.get("/anomalies")
async def detect_bash_anomalies(
    start_time: float | None = Query(None, description="开始时间（UTC timestamp）"),
    end_time: float | None = Query(None, description="结束时间（UTC timestamp）"),
    limit: int = Query(1000, ge=1, le=10000, description="日志数量限制"),
    notify: bool = Query(False, description="是否发送告警通知"),
) -> list[dict[str, object]]:
    """检测bash命令异常

    Args:
        start_time: 开始时间（UTC timestamp）
        end_time: 结束时间（UTC timestamp）
        limit: 日志数量限制

    Returns:
        异常告警列表
    """
    try:
        from myrm_agent_harness.api.hooks import get_event_logger

        from .anomaly_detector import BashAnomalyDetector

        event_logger = get_event_logger()
        if not event_logger:
            raise HTTPException(status_code=503, detail="Event logger not available")

        # 获取审计日志
        events = await event_logger.get_bash_audit_logs(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

        # 转换为dict列表
        audit_logs: list[dict[str, object]] = []
        for event in events:
            raw = event.to_dict()
            if isinstance(raw, dict):
                audit_logs.append({str(k): v for k, v in raw.items()})

        # 检测异常
        alerts = await BashAnomalyDetector.detect_anomalies(audit_logs)

        # 发送告警通知（如果启用）
        if notify and alerts:
            from app.config.settings import settings

            from .alert_notifier import AlertConfig, BashAuditAlertNotifier

            config = AlertConfig(
                webhook_url=settings.bash_audit.webhook_url or None,
                slack_webhook=settings.bash_audit.slack_webhook or None,
            )
            notifier = BashAuditAlertNotifier(config)

            # 只通知HIGH和MEDIUM严重级别的告警
            for alert in alerts:
                if alert.severity in ("HIGH", "MEDIUM"):
                    await notifier.send_alert(
                        alert_type=alert.alert_type,
                        severity=alert.severity,
                        message=alert.message,
                        details=alert.details,
                    )

        # 转换为响应格式
        return [
            {
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "details": alert.details,
                "timestamp": alert.timestamp,
            }
            for alert in alerts
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to detect anomalies: {e}") from e
