"""Bash命令异常检测

基于规则的异常检测，用于识别可疑的命令执行模式。
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class AnomalyAlert:
    """异常告警"""

    alert_type: str  # high_frequency_failure / dangerous_command / abnormal_time
    severity: str  # LOW / MEDIUM / HIGH
    message: str
    details: dict[str, object]
    timestamp: float


class BashAnomalyDetector:
    """Bash命令异常检测器

    基于规则的异常检测，不依赖ML模型。
    """

    # 危险命令模式（来自CommandClassifier）
    DANGEROUS_PATTERNS = [
        "rm -rf",
        "dd if=",
        "mkfs.",
        "chmod 777",
        "chmod 666",
        "> /dev/sd",
    ]

    @classmethod
    async def detect_anomalies(cls, audit_logs: list[dict[str, object]]) -> list[AnomalyAlert]:
        """检测异常模式

        Args:
            audit_logs: 审计日志列表

        Returns:
            异常告警列表
        """
        alerts: list[AnomalyAlert] = []

        # 检测1：高频失败命令
        high_freq_alerts = cls._detect_high_frequency_failures(audit_logs)
        alerts.extend(high_freq_alerts)

        # 检测2：危险命令执行
        dangerous_alerts = cls._detect_dangerous_commands(audit_logs)
        alerts.extend(dangerous_alerts)

        # 检测3：异常时间执行（凌晨2-6点）
        abnormal_time_alerts = cls._detect_abnormal_time_execution(audit_logs)
        alerts.extend(abnormal_time_alerts)

        return alerts

    @classmethod
    def _detect_high_frequency_failures(cls, audit_logs: list[dict[str, object]]) -> list[AnomalyAlert]:
        """检测高频失败命令

        规则：同一命令在1小时内失败超过5次

        Args:
            audit_logs: 审计日志列表

        Returns:
            异常告警列表
        """
        import time
        from collections import defaultdict

        alerts: list[AnomalyAlert] = []

        # 按命令分组统计失败次数
        command_failures: dict[str, list[float]] = defaultdict(list)
        for log in audit_logs:
            if not log.get("success"):
                cmd_raw = log.get("command", "")
                command = cmd_raw if isinstance(cmd_raw, str) else str(cmd_raw)
                timestamp = log.get("timestamp", 0.0)
                if command and isinstance(timestamp, (int, float)):
                    command_failures[command].append(float(timestamp))

        # 检查高频失败
        current_time = time.time()
        one_hour_ago = current_time - 3600

        for command, timestamps in command_failures.items():
            # 统计1小时内的失败次数
            recent_failures = [ts for ts in timestamps if ts >= one_hour_ago]
            if len(recent_failures) >= 5:
                alerts.append(
                    AnomalyAlert(
                        alert_type="high_frequency_failure",
                        severity="MEDIUM",
                        message=f"Command failed {len(recent_failures)} times in the last hour",
                        details={
                            "command": command,
                            "failure_count": len(recent_failures),
                            "time_window": "1 hour",
                        },
                        timestamp=current_time,
                    )
                )

        return alerts

    @classmethod
    def _detect_dangerous_commands(cls, audit_logs: list[dict[str, object]]) -> list[AnomalyAlert]:
        """检测危险命令执行

        规则：执行了DANGEROUS_PATTERNS中的命令

        Args:
            audit_logs: 审计日志列表

        Returns:
            异常告警列表
        """
        import time

        alerts: list[AnomalyAlert] = []

        for log in audit_logs:
            cmd_raw = log.get("command", "")
            command = cmd_raw if isinstance(cmd_raw, str) else str(cmd_raw)
            risk_raw = log.get("risk_level", "")
            risk_level = risk_raw if isinstance(risk_raw, str) else str(risk_raw)

            if risk_level == "HIGH" or any(pattern in command for pattern in cls.DANGEROUS_PATTERNS):
                alerts.append(
                    AnomalyAlert(
                        alert_type="dangerous_command",
                        severity="HIGH",
                        message=f"Dangerous command executed: {command[:50]}",
                        details={
                            "command": command,
                            "risk_level": risk_level,
                            "timestamp": log.get("timestamp", 0),
                        },
                        timestamp=time.time(),
                    )
                )

        return alerts

    @classmethod
    def _detect_abnormal_time_execution(cls, audit_logs: list[dict[str, object]]) -> list[AnomalyAlert]:
        """检测异常时间执行

        规则：凌晨2-6点执行命令（可疑行为）

        Args:
            audit_logs: 审计日志列表

        Returns:
            异常告警列表
        """
        import time

        alerts: list[AnomalyAlert] = []

        for log in audit_logs:
            timestamp = log.get("timestamp")
            if not isinstance(timestamp, (int, float)):
                continue

            hour = datetime.fromtimestamp(float(timestamp)).hour
            if 2 <= hour < 6:  # 凌晨2-6点
                cmd_raw = log.get("command", "")
                command = cmd_raw if isinstance(cmd_raw, str) else str(cmd_raw)
                alerts.append(
                    AnomalyAlert(
                        alert_type="abnormal_time",
                        severity="LOW",
                        message=f"Command executed during abnormal hours (2-6 AM): {command[:50]}",
                        details={
                            "command": command,
                            "hour": hour,
                            "timestamp": timestamp,
                        },
                        timestamp=time.time(),
                    )
                )

        return alerts
